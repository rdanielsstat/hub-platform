"""Gate on pip-audit findings by severity: fail on HIGH or CRITICAL, warn
on MODERATE or LOW. Run by the dependency-scan job in ci.yml.

pip-audit reports vulnerability ids but no severity, so each finding is
looked up in OSV (https://osv.dev), using the GitHub advisory (GHSA) among
its id and aliases, whose database_specific.severity is CRITICAL, HIGH,
MODERATE or LOW. A finding whose severity can't be determined (no GHSA
alias, or OSV unreachable) fails the gate: unknown is treated as HIGH, so a
lookup problem can never wave a real vulnerability through.

Usage: python pip_audit_gate.py <pip-audit --format json output>
Standard library only. Exit 0: nothing HIGH or above. Exit 1: at least one.
"""

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

OSV_URL = "https://api.osv.dev/v1/vulns/{}"
BLOCKING = {"CRITICAL", "HIGH", "UNKNOWN"}


def osv_severity(vuln_id: str) -> str | None:
    """The GitHub advisory severity OSV records for vuln_id, or None."""
    try:
        with urllib.request.urlopen(OSV_URL.format(vuln_id), timeout=15) as res:
            record = json.load(res)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    severity = (record.get("database_specific") or {}).get("severity")
    return severity.upper() if isinstance(severity, str) else None


def severity_of(vuln: dict, lookup: Callable[[str], str | None]) -> str:
    ids = [vuln.get("id", "")] + list(vuln.get("aliases") or [])
    for vuln_id in sorted(ids, key=lambda i: not i.startswith("GHSA-")):
        if vuln_id.startswith("GHSA-"):
            found = lookup(vuln_id)
            if found:
                return found
    return "UNKNOWN"


def gate(report: dict, lookup: Callable[[str], str | None] = osv_severity) -> int:
    blocking = 0
    total = 0
    seen: set[tuple[str, str, str]] = set()
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            # pip-audit can list the same package twice; report each finding once.
            key = (dep["name"], dep.get("version", "?"), vuln["id"])
            if key in seen:
                continue
            seen.add(key)
            total += 1
            severity = severity_of(vuln, lookup)
            fix = ", ".join(vuln.get("fix_versions") or []) or "no fix yet"
            text = f"{dep['name']} {dep.get('version', '?')}: {vuln['id']} [{severity}] (fixed in: {fix})"
            if severity in BLOCKING:
                blocking += 1
                print(f"::error title=pip-audit {severity}::{text}")
            else:
                print(f"::warning title=pip-audit {severity}::{text}")
    print(f"pip-audit: {total} finding(s), {blocking} HIGH or above (unknown counts as HIGH).")
    return 1 if blocking else 0


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        return gate(json.load(f))


if __name__ == "__main__":
    sys.exit(main())
