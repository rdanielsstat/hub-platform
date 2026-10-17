# Alerting on user impact, as code: the project creation 5xx alert for dev
# and prod, the webhook contact point that wakes the on-call agent, and
# the notification policy that routes one to the other.
#
# Dev and prod share one Grafana Cloud stack, which has exactly one
# notification policy tree. So the shared pieces, the folder, the contact
# point and the policy, belong to the dev workspace (applied by ci.yml on
# every merge to main). Each environment's alert rule belongs to its own
# workspace: the dev rule group is created and changed only by the dev
# apply, the prod rule group only by the prod apply in promote.yml, so a
# change to the prod rule reaches prod with the promotion, like code. Each
# rule filters its own environment with the hub_environment label
# (backend/observability/metrics.py).
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

# The stack's existing contact point that gets every alert the on-call
# route below doesn't take (the policy tree's default). It isn't managed
# here, and the Grafana provider has no data source for contact points, so
# its name comes in from CI: the GRAFANA_DEFAULT_CONTACT_POINT repo
# variable. Required, with no default, so the name never lives in the
# code; Grafana refuses the policy at apply if no contact point has it.
variable "grafana_default_contact_point" {
  description = "Name of the existing Grafana contact point the notification policy defaults to. Set by CI."
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.grafana_default_contact_point) != ""
    error_message = "grafana_default_contact_point must name an existing Grafana contact point (the GRAFANA_DEFAULT_CONTACT_POINT repo variable)."
  }
}

# UID of Grafana Cloud's Prometheus (Mimir) data source, which the alert
# queries. Grafana Cloud gives it the UID grafanacloud-prom (its display
# name is grafanacloud-<stack>-prom).
variable "grafana_prometheus_data_source_uid" {
  description = "UID of the Grafana Cloud Prometheus data source the alert queries."
  type        = string
  default     = "grafanacloud-prom"
}

locals {
  # The folder, contact point and notification policy: dev only.
  manage_grafana = local.environment == "dev"
  # This workspace's own rule group, in dev and in prod.
  manage_rule = local.is_valid_env

  # The alert: more than 2% of POST /projects requests answer 5xx over a
  # 5 minute window, counted only once there were at least 10 requests
  # in that window, so a single failure at night can't page anyone.
  alert_window      = "5m"
  alert_ratio       = 0.02
  alert_min_traffic = 10
}

resource "grafana_folder" "hub" {
  count = local.manage_grafana ? 1 : 0
  title = "Hub alerts"
}

# Prod puts its rule group in the folder the dev workspace owns. Dev is
# always deployed before a promotion, so the folder exists by then.
data "grafana_folder" "hub" {
  count = local.manage_rule && !local.manage_grafana ? 1 : 0
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

# The stack's whole policy tree. Alerts labeled hub_oncall="true" go to
# the dispatch contact point and wake the on-call agent; everything else
# (alerts made by hand in the UI, say) goes to the existing default
# contact point, so it reaches a person and never starts the agent.
resource "grafana_notification_policy" "hub" {
  count         = local.manage_grafana ? 1 : 0
  contact_point = var.grafana_default_contact_point
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

# One group per workspace, holding only that environment's rule.
resource "grafana_rule_group" "project_creation" {
  count            = local.manage_rule ? 1 : 0
  name             = "Project creation (${local.environment})"
  folder_uid       = local.manage_grafana ? grafana_folder.hub[0].uid : data.grafana_folder.hub[0].uid
  interval_seconds = 60

  rule {
    name      = "Project creation 5xx rate above 2% (${local.environment})"
    condition = "C"
    # Fires on the first evaluation over the threshold: the 5 minute
    # window already smooths it.
    for            = "0s"
    no_data_state  = "OK"
    exec_err_state = "Error"

    labels = {
      hub_oncall      = "true"
      hub_environment = local.environment
      severity        = "page"
      journey         = "project_create"
    }
    annotations = {
      summary     = "POST /projects 5xx rate above 2% over 5 minutes on ${local.environment} (at least 10 requests)"
      description = "Users can't create projects on ${local.environment}. The on-call agent ${local.environment == "dev" ? "rolls dev back to the previous image" : "diagnoses it; prod is never rolled back automatically"}."
      runbook_url = "https://github.com/${var.github_repo}/blob/main/ops/MONITORING.md#alerts"
    }

    # A: 5xx responses in the window (0 when there were none).
    data {
      ref_id         = "A"
      datasource_uid = var.grafana_prometheus_data_source_uid
      relative_time_range {
        from = 300
        to   = 0
      }
      model = jsonencode({
        refId   = "A"
        expr    = "sum(increase(projects_create_errors_total{hub_environment=\"${local.environment}\", http_status_code=~\"5..\"}[${local.alert_window}])) or vector(0)"
        instant = true
        range   = false
      })
    }

    # B: all requests in the window.
    data {
      ref_id         = "B"
      datasource_uid = var.grafana_prometheus_data_source_uid
      relative_time_range {
        from = 300
        to   = 0
      }
      model = jsonencode({
        refId   = "B"
        expr    = "sum(increase(projects_create_total{hub_environment=\"${local.environment}\"}[${local.alert_window}])) or vector(0)"
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
