"""Claude Code PreToolUse hook: enforces the AGENTS.md boundaries an
agent could otherwise cross by accident.

Registered in .claude/settings.json for Bash, Read, Edit, Write,
MultiEdit, NotebookEdit and Grep. Claude Code sends the tool call as JSON on
stdin; this prints a permission decision as JSON on stdout:

  deny  real secrets (.env files, .secrets, *.tfvars), `git commit`, and
        deploys (tofu/terraform apply or destroy, gh workflow run, direct
        AWS deploy calls). AGENTS.md: the human commits and deploys.
  ask   `git push` and `git tag` (the release skill pushes a tag and main,
        with the human confirming each), and commands that delete data
        (`docker compose down -v`, `docker volume rm`, `alembic
        downgrade`).

Anything else prints nothing, and Claude Code's normal permission rules
apply. Standard library only, and Python 3.9+, so it runs under whatever
`python3` the machine has. Tests: agent-hooks/tests/.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"}

# Real secrets and local configuration. The tracked templates
# (.env.example, *.tfvars.example) are fine to read and edit.
SECRET_PATTERNS = (".env", ".env.*", "*.env", ".secrets", "*.tfvars")
SECRET_EXCEPTIONS = (".env.example", "*.tfvars.example")

# Splits a command line into simple commands at ;, &, |, &&, || and
# newlines. Quoting is handled afterwards by shlex, per command.
SEPARATORS = re.compile(r"\s*(?:&&|\|\||[;&|\n])\s*")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A word with any of these is a pattern (grep, find -name), not a path.
# Not $ or {}: "$HOME/.env" and ${VAR}/.env are paths.
PATTERN_CHARS = set("\\|*?[]()^")
# Subcommands that change deployed infrastructure.
INFRA_WRITES = {"apply", "destroy", "import", "taint"}
GH_WORKFLOW_STARTS = (["workflow", "run"], ["workflow", "enable"])
GH_PUBLISHES = (["pr", "merge"], ["release", "create"])
ALEMBIC_DOWNGRADE = "`alembic downgrade` drops schema and the data in it. Confirm."
# Wrappers that run the command after them.
WRAPPERS = {"sudo", "env", "command", "exec", "nohup", "time", "xargs"}
# Options whose value names a path to leave out (tfsec --exclude-path,
# checkov --skip-path, grep --exclude=...): naming a secrets file there
# keeps a tool away from it.
EXCLUDE_OPTIONS = {
    "--exclude",
    "--exclude-dir",
    "--exclude-path",
    "--ignore",
    "--ignore-path",
    "--skip-path",
}
# A heredoc operator (<<EOF, <<-'EOF', <<"EOF"), not a here-string (<<<).
HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def is_secret_path(path: str) -> bool:
    name = os.path.basename(path.rstrip("/"))
    if any(fnmatch.fnmatch(name, p) for p in SECRET_EXCEPTIONS):
        return False
    return any(fnmatch.fnmatch(name, p) for p in SECRET_PATTERNS)


def _mentions_secret(word: str) -> bool:
    """A command-line word naming a secrets file: a plain path, a
    redirection (<.env, >>backend/.env.local), or an option value
    (--env-file=.env)."""
    if word.startswith("-") and "=" in word:
        word = word.split("=", 1)[1]
    word = word.lstrip("<>0123456789&")
    if not word or PATTERN_CHARS & set(word):
        return False
    return is_secret_path(word)


def _without_heredoc_bodies(command: str) -> str:
    """The command with heredoc bodies removed: they're input data (a
    file being written, a script for python), not words of the command.
    The operator's own line stays, so `cat <<EOF > backend/.env` is still
    checked."""
    kept: list[str] = []
    delimiter = None
    for line in command.split("\n"):
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        kept.append(line)
        match = HEREDOC.search(line)
        if match:
            delimiter = match.group(2)
    return "\n".join(kept)


def _secret_word(words: list[str]) -> str | None:
    """The first word that names a secrets file, skipping the values of
    exclusion options."""
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
            continue
        option = word.split("=", 1)[0]
        if option in EXCLUDE_OPTIONS:
            skip_next = "=" not in word
            continue
        if _mentions_secret(word):
            return word
    return None


def _words(command: str) -> list[str]:
    try:
        return shlex.split(command, comments=True)
    except ValueError:
        # Unbalanced quotes: fall back to whitespace, which still catches
        # the plain cases.
        return command.split()


def _strip_prefix(words: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrappers like sudo/env."""
    i = 0
    while i < len(words) and (ENV_ASSIGNMENT.match(words[i]) or words[i] in WRAPPERS):
        i += 1
    return words[i:]


def _git_subcommand(words: list[str]) -> tuple[str, list[str]]:
    """git's subcommand and its arguments, skipping global options
    (-C dir, -c key=value, --no-pager, ...)."""
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in ("-C", "-c") else 1
    if i >= len(words):
        return "", []
    return words[i], words[i + 1 :]


def check_command(command: str) -> tuple[str, str] | None:
    """(decision, reason) for a Bash command line, or None."""
    asks: list[str] = []
    for part in SEPARATORS.split(_without_heredoc_bodies(command)):
        words = _strip_prefix(_words(part))
        if not words:
            continue
        secret = _secret_word(words)
        if secret is not None:
            return (
                "deny",
                f"{secret} holds local secrets or configuration; AGENTS.md: "
                "never read, edit or print real .env files or secrets. "
                "The .env.example templates are fine.",
            )
        program = os.path.basename(words[0])
        args = words[1:]

        if program == "git":
            sub, sub_args = _git_subcommand(words)
            if sub == "commit":
                return (
                    "deny",
                    "AGENTS.md: agents never commit. Summarize the changes and "
                    "suggest a commit message; the human reviews and commits.",
                )
            if sub in ("push", "tag") and not (
                sub == "tag" and _is_tag_listing(sub_args)
            ):
                asks.append(
                    f"`git {sub}` publishes to the remote (a push to main deploys "
                    "to dev). Confirm this is intended, e.g. for the release skill."
                )
        elif program in ("tofu", "terraform") and args[:1] and args[0] in INFRA_WRITES:
            return (
                "deny",
                f"`{program} {args[0]}` changes deployed infrastructure; "
                "AGENTS.md: agents never deploy. `plan` and `validate` are fine.",
            )
        elif program == "gh" and args[:2] in GH_WORKFLOW_STARTS:
            return (
                "deny",
                "Starting a GitHub Actions workflow (deploy, promote) is a human "
                "action; AGENTS.md: agents never deploy.",
            )
        elif program == "gh" and args[:2] in GH_PUBLISHES:
            asks.append(
                f"`gh {' '.join(args[:2])}` publishes to the repository (a merge "
                "to main deploys to dev). Confirm this is intended."
            )
        elif program == "aws" and _is_aws_deploy(args):
            return (
                "deny",
                "This AWS call changes deployed resources; AGENTS.md: agents "
                "never deploy. Read-only calls (describe, list, get) are fine.",
            )
        elif program == "docker" and _deletes_docker_data(args):
            asks.append(
                "This deletes Docker volumes, including the local Postgres data. "
                "Confirm the data can go."
            )
        elif "downgrade" in args and (program == "alembic" or "alembic" in args):
            # `alembic downgrade`, or through `uv run` / `python -m`.
            asks.append(ALEMBIC_DOWNGRADE)
    if asks:
        return "ask", " ".join(dict.fromkeys(asks))
    return None


def _is_tag_listing(args: list[str]) -> bool:
    """`git tag`, `git tag -l ...`, `git tag --list`: read-only."""
    return not args or args[0] in ("-l", "--list", "-n") or args[0].startswith("-n")


def _is_aws_deploy(args: list[str]) -> bool:
    words = [a for a in args if not a.startswith("-")]
    if len(words) < 2:
        return False
    service, operation = words[0], words[1]
    if service == "s3":
        # Uploads and deletions; downloading from S3 is read-only.
        if operation in ("rm", "rb"):
            return True
        return operation in ("sync", "cp", "mv") and words[-1].startswith("s3://")
    return operation.startswith(
        ("update-", "delete-", "put-", "create-", "invoke", "publish-")
    )


def _deletes_docker_data(args: list[str]) -> bool:
    if args[:2] == ["volume", "rm"] or args[:2] == ["volume", "prune"]:
        return True
    if args[:1] == ["compose"] and "down" in args:
        return "-v" in args or "--volumes" in args
    return args[:2] == ["system", "prune"] and "--volumes" in args


def check_file(tool_input: dict) -> tuple[str, str] | None:
    path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")  # Grep
        or ""
    )
    if path and is_secret_path(path):
        return (
            "deny",
            f"{path} holds local secrets or configuration; AGENTS.md: never "
            "read or edit real .env files or secrets. Update the .env.example "
            "template instead, and flag any real value the human must set.",
        )
    return None


def decide(event: dict) -> tuple[str, str] | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool == "Bash":
        return check_command(tool_input.get("command", ""))
    if tool in FILE_TOOLS:
        return check_file(tool_input)
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        # Not a hook payload; never block on our own parsing failure.
        return 0
    result = decide(event)
    if result is not None:
        decision, reason = result
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": f"agent-hooks/guard.py: {reason}",
                }
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
