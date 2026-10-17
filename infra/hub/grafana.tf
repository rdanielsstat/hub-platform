# Alerting on user impact, as code: the project creation 5xx alert for dev
# and prod, the webhook contact point that wakes the on-call agent, and
# the notification policy that routes one to the other.
#
# Dev and prod share one Grafana Cloud stack, and a stack has exactly one
# notification policy tree. So the dev workspace owns all of it (count
# below), including the prod rule: an alerting change applies on the next
# dev deploy (merge to main), and the prod workspace manages nothing in
# Grafana. Each rule filters its own environment with the hub_environment
# label (backend/observability/metrics.py).
#
# Flow: the rule fires -> the policy routes it (label hub_oncall="true")
# to the contact point -> the contact point POSTs to GitHub's
# repository_dispatch API with event_type "grafana-alert" ->
# .github/workflows/observability-alert-handler.yml runs, with no human.

# Required, with no default. CI passes it from the GRAFANA_URL repo
# variable (the stack URL, https://<stack>.grafana.net).
variable "grafana_url" {
  description = "Grafana Cloud stack URL. Set by CI from the GRAFANA_URL repo variable."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^https://[a-z0-9-]+\\.grafana\\.net/?$", var.grafana_url))
    error_message = "grafana_url must be a Grafana Cloud stack URL, https://<stack>.grafana.net."
  }
}

# Fine-grained GitHub token that may create repository_dispatch events on
# this repository (Contents: read and write, this repository only). CI
# passes it from the GH_DISPATCH_TOKEN secret. Grafana stores it in the
# contact point; it never appears in the repo.
variable "github_dispatch_token" {
  description = "GitHub token Grafana uses to call the repository_dispatch API. Set by CI."
  type        = string
  sensitive   = true
  nullable    = false
}

variable "github_repo" {
  description = "owner/name of the repository the alert dispatches to."
  type        = string
  default     = "rdanielsstat/hub-platform"
}

# Grafana Cloud's Prometheus (Mimir) data source, named
# grafanacloud-<stack>-prom by Grafana Cloud.
variable "grafana_prometheus_data_source" {
  description = "Name of the Grafana Cloud Prometheus data source the alert queries."
  type        = string
  default     = "grafanacloud-blackpoplar56-prom"
}

locals {
  manage_grafana = local.environment == "dev"

  # The alert: more than 2% of POST /projects requests answer 5xx over a
  # 5 minute window, counted only once there were at least 10 requests
  # in that window, so a single failure at night can't page anyone.
  alert_window       = "5m"
  alert_ratio        = 0.02
  alert_min_traffic  = 10
  alert_environments = toset(["dev", "prod"])
}

data "grafana_data_source" "prometheus" {
  count = local.manage_grafana ? 1 : 0
  name  = var.grafana_prometheus_data_source
}

resource "grafana_folder" "hub" {
  count = local.manage_grafana ? 1 : 0
  title = "Hub alerts"
}

resource "grafana_contact_point" "oncall_dispatch" {
  count = local.manage_grafana ? 1 : 0
  name  = "hub-oncall-github-dispatch"

  webhook {
    # https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event
    url                       = "https://api.github.com/repos/${var.github_repo}/dispatches"
    http_method               = "POST"
    authorization_scheme      = "Bearer"
    authorization_credentials = var.github_dispatch_token
    headers = {
      "Accept"               = "application/vnd.github+json"
      "X-GitHub-Api-Version" = "2022-11-28"
    }
    # GitHub needs {"event_type": ..., "client_payload": {...}}, not
    # Grafana's default webhook body.
    payload {
      template = file("${path.module}/grafana/dispatch-payload.tmpl")
    }
    # Resolved notifications go too: the agent records them on the issue.
    disable_resolve_message = false
  }
}

# The stack's whole policy tree. Everything goes to the dispatch contact
# point; the agent ignores any alert without hub_oncall="true"
# (backend/oncall/alert.py), so an alert made by hand in the UI can't
# make it act.
resource "grafana_notification_policy" "hub" {
  count         = local.manage_grafana ? 1 : 0
  contact_point = grafana_contact_point.oncall_dispatch[0].name
  group_by      = ["alertname", "hub_environment"]

  policy {
    matcher {
      label = "hub_oncall"
      match = "="
      value = "true"
    }
    contact_point   = grafana_contact_point.oncall_dispatch[0].name
    group_by        = ["alertname", "hub_environment"]
    group_wait      = "30s"
    group_interval  = "5m"
    repeat_interval = "4h"
  }
}

resource "grafana_rule_group" "project_creation" {
  count            = local.manage_grafana ? 1 : 0
  name             = "Project creation"
  folder_uid       = grafana_folder.hub[0].uid
  interval_seconds = 60

  dynamic "rule" {
    for_each = local.alert_environments
    content {
      name      = "Project creation 5xx rate above 2% (${rule.value})"
      condition = "C"
      # Fires on the first evaluation over the threshold: the 5 minute
      # window already smooths it.
      for            = "0s"
      no_data_state  = "OK"
      exec_err_state = "Error"

      labels = {
        hub_oncall      = "true"
        hub_environment = rule.value
        severity        = "page"
        journey         = "project_create"
      }
      annotations = {
        summary     = "POST /projects 5xx rate above 2% over 5 minutes on ${rule.value} (at least 10 requests)"
        description = "Users can't create projects on ${rule.value}. The on-call agent ${rule.value == "dev" ? "rolls dev back to the previous image" : "diagnoses it; prod is never rolled back automatically"}."
        runbook_url = "https://github.com/${var.github_repo}/blob/main/ops/MONITORING.md#alerts"
      }

      # A: 5xx responses in the window (0 when there were none).
      data {
        ref_id         = "A"
        datasource_uid = data.grafana_data_source.prometheus[0].uid
        relative_time_range {
          from = 300
          to   = 0
        }
        model = jsonencode({
          refId   = "A"
          expr    = "sum(increase(projects_create_errors_total{hub_environment=\"${rule.value}\", http_status_code=~\"5..\"}[${local.alert_window}])) or vector(0)"
          instant = true
          range   = false
        })
      }

      # B: all requests in the window.
      data {
        ref_id         = "B"
        datasource_uid = data.grafana_data_source.prometheus[0].uid
        relative_time_range {
          from = 300
          to   = 0
        }
        model = jsonencode({
          refId   = "B"
          expr    = "sum(increase(projects_create_total{hub_environment=\"${rule.value}\"}[${local.alert_window}])) or vector(0)"
          instant = true
          range   = false
        })
      }

      # C: firing when there was enough traffic and the 5xx share is over 2%.
      data {
        ref_id         = "C"
        datasource_uid = "__expr__"
        relative_time_range {
          from = 0
          to   = 0
        }
        model = jsonencode({
          refId      = "C"
          type       = "math"
          expression = "$B >= ${local.alert_min_traffic} && ($A / $B) > ${local.alert_ratio}"
          datasource = { type = "__expr__", uid = "__expr__" }
        })
      }
    }
  }
}
