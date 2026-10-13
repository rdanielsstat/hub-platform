"""Claude Code PreToolUse hook: enforces the AGENTS.md boundaries an
agent could otherwise cross by accident.

Registered in .claude/settings.json (through run-guard.sh, which fails
closed when python3 is missing or this script crashes) for Bash, Read,
Edit, Write, MultiEdit, NotebookEdit and Grep. Claude Code sends the
tool call as JSON on stdin; this prints a permission decision as JSON on
stdout:

  deny  real secrets (.env files, .secrets, *.tfvars) and commands that
        print the environment or read secrets from AWS; anything that
        creates a commit (`git commit`, merge, cherry-pick, revert, am,
        rebase, aliases); deploys (tofu/terraform apply, destroy and
        state changes, starting workflows, AWS writes); publishing
        packages. AGENTS.md: the human commits and deploys.
  ask   `git push`, `git tag`, `git pull`, `gh pr merge`, `gh release
        create`, other GitHub API writes, `aws ecr get-login-password`,
        and commands that delete local data (`docker compose down -v`,
        `docker volume rm`, `alembic downgrade`).

Commands wrapped in `bash -c`/`sh -c`/`eval`, `env`, `sudo`, `xargs`,
`nohup`, `nice` or `timeout` are checked as the command they run.
Anything else prints nothing, and Claude Code's normal permission rules
apply. Input it can't read, and its own crashes, are denied (fail
closed). Standard library only, and Python 3.9+, so it runs under
whatever `python3` the machine has. Tests: agent-hooks/tests/.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from typing import Optional

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"}

# Real secrets and local configuration. The tracked templates
# (.env.example, *.tfvars.example) are fine to read and edit.
SECRET_PATTERNS = (".env", ".env.*", "*.env", ".secrets", "*.tfvars")
SECRET_EXCEPTIONS = (".env.example", "*.tfvars.example")

# Characters that end a simple command (;, &, |, and so &&, ||) when
# they're outside quotes; see _split_commands.
SEPARATOR_CHARS = set(";&|\n")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A word with any of these is a pattern (grep, find -name), not a path.
# Not $ or {}: "$HOME/.env" and ${VAR}/.env are paths.
PATTERN_CHARS = set("\\|*?[]()^")
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
# The MCP server's password, if it ever is in an environment.
PASSWORD_EXPANSION = re.compile(r"\$\{?HUB_PASSWORD\b")

# Programs that run the command after them, and which of their options
# take a value (so the value isn't mistaken for the command).
WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {"-u", "-g", "-h", "-p", "-U", "-C", "-D", "-r", "-t", "-T"},
    "xargs": {"-I", "-i", "-n", "-L", "-l", "-P", "-s", "-d", "-E", "-e", "-a"},
    "nice": {"-n"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nohup": set(),
    "time": set(),
    "command": set(),
    "exec": {"-a"},
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
MAX_NESTING = 5

# git subcommands that create commits on the current branch.
COMMIT_CREATORS = {
    "commit",
    "commit-tree",
    "merge",
    "cherry-pick",
    "revert",
    "am",
    "rebase",
}
# tofu/terraform: subcommands that change deployed infrastructure or state.
INFRA_WRITES = {"apply", "destroy", "import", "taint", "untaint", "force-unlock"}
STATE_WRITES = {"rm", "mv", "push", "replace-provider"}
GH_WORKFLOW_STARTS = (["workflow", "run"], ["workflow", "enable"], ["run", "rerun"])
GH_PUBLISHES = (["pr", "merge"], ["release", "create"])
GH_API_FIELD_OPTIONS = {"-f", "-F", "--field", "--raw-field", "--input"}
# AWS CLI options that take no value; every other `--option` does.
AWS_FLAGS = {
    "--recursive",
    "--dryrun",
    "--delete",
    "--quiet",
    "--no-progress",
    "--only-show-errors",
    "--follow-symlinks",
    "--no-follow-symlinks",
    "--exact-timestamps",
    "--size-only",
    "--with-decryption",
    "--no-with-decryption",
    "--debug",
    "--no-paginate",
    "--no-verify-ssl",
    "--no-sign-request",
    "--no-cli-pager",
    "--force",
}
# AWS reads that return secrets: SSM SecureStrings decrypted, Secrets
# Manager, KMS, and Lambda configurations (their environment variables
# hold the OTLP token), plus temporary credentials.
AWS_SECRET_READS = {
    ("secretsmanager", "get-secret-value"),
    ("secretsmanager", "batch-get-secret-value"),
    ("kms", "decrypt"),
    ("lambda", "get-function"),
    ("lambda", "get-function-configuration"),
    ("lambda", "list-functions"),
    ("configure", "export-credentials"),
    ("sts", "get-session-token"),
    ("sts", "get-federation-token"),
    ("sts", "assume-role"),
    ("sts", "assume-role-with-web-identity"),
    ("sts", "assume-role-with-saml"),
}
SSM_PARAMETER_READS = {"get-parameter", "get-parameters", "get-parameters-by-path"}
PUBLISHERS = {
    ("pnpm", "publish"),
    ("npm", "publish"),
    ("yarn", "publish"),
    ("uv", "publish"),
    ("poetry", "publish"),
    ("twine", "upload"),
}

ALEMBIC_DOWNGRADE = "`alembic downgrade` drops schema and the data in it. Confirm."
NEVER_COMMIT = (
    "AGENTS.md: agents never commit. Summarize the changes and suggest a "
    "commit message; the human reviews and commits."
)
NEVER_DEPLOY = "AGENTS.md: agents never deploy."
ENVIRONMENT_DUMP = (
    "This prints the environment, where credentials can sit (the MCP "
    "server's, for one); AGENTS.md: never print secrets. Read a specific, "
    "non-secret variable instead."
)

# (decision, reason), or None for "no opinion".
Decision = Optional[tuple[str, str]]


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


def _split_commands(command: str) -> list[str]:
    """Split a command line into simple commands at ;, &, |, &&, || and
    newlines, but only outside quotes: `bash -c 'cd x && tofu apply'`
    stays one command, whose script is checked on its own."""
    parts: list[str] = []
    current: list[str] = []
    quote = None
    escaped = False
    for char in command:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\" and quote != "'":
            current.append(char)
            escaped = True
        elif quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            current.append(char)
            quote = char
        elif char in SEPARATOR_CHARS:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


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


def _unwrap(words: list[str]) -> tuple[list[str], bool]:
    """The command a line actually runs: leading VAR=value assignments
    and wrappers (env, sudo, xargs, ...) with their options removed.
    Also whether it was a bare `env` (which prints the environment)."""
    i = 0
    bare_env = False
    while i < len(words):
        if ENV_ASSIGNMENT.match(words[i]):
            i += 1
            continue
        program = os.path.basename(words[i])
        if program not in WRAPPERS:
            break
        takes_value = WRAPPERS[program]
        i += 1
        while i < len(words) and (
            words[i].startswith("-") or (program == "env" and "=" in words[i])
        ):
            option = words[i].split("=", 1)[0]
            i += 2 if option in takes_value and "=" not in words[i] else 1
        if program == "timeout" and i < len(words):
            i += 1  # the duration
        bare_env = program == "env" and i >= len(words)
    return words[i:], bare_env


def _git_parts(words: list[str]) -> tuple[str, list[str], list[str]]:
    """git's subcommand, its arguments, and the values of global `-c`
    options, skipping global options (-C dir, -c key=value, ...)."""
    i = 1
    configs: list[str] = []
    while i < len(words) and words[i].startswith("-"):
        if words[i] in ("-C", "-c"):
            if words[i] == "-c" and i + 1 < len(words):
                configs.append(words[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(words):
        return "", [], configs
    return words[i], words[i + 1 :], configs


def _subcommand(args: list[str]) -> tuple[str, list[str]]:
    """The first non-option argument and what follows it (tofu and
    terraform take global options like -chdir=dir before it)."""
    for i, word in enumerate(args):
        if not word.startswith("-"):
            return word, args[i + 1 :]
    return "", []


def _shell_script(args: list[str]) -> str | None:
    """The script of `bash -c '...'` (also -lc, -ec, ...)."""
    expect_script = False
    for word in args:
        if expect_script:
            return word
        if word.startswith("-") and not word.startswith("--") and "c" in word[1:]:
            expect_script = True
    return None


def _environment_dump(program: str, args: list[str]) -> bool:
    if program == "printenv":
        return True
    if program == "set":
        return not args
    if program == "export":
        return not args or args == ["-p"]
    if program in ("declare", "typeset"):
        return "-p" in args or all(a.startswith("-") for a in args)
    if program == "ps":
        if any(w.startswith("-") and not w.startswith("--") and "E" in w for w in args):
            return True  # ps -E
        first = args[0] if args else ""
        return first.isalpha() and "e" in first  # BSD style: ps eww, ps auxe
    return False


def _check_git(words: list[str]) -> Decision:
    sub, sub_args, configs = _git_parts(words)
    if any(value.startswith("alias.") for value in configs):
        return "deny", "A git alias can hide a commit or a push. " + NEVER_COMMIT
    if sub in COMMIT_CREATORS:
        return "deny", f"`git {sub}` creates commits. " + NEVER_COMMIT
    if sub == "config" and any(a.startswith("alias.") for a in sub_args):
        return "deny", "A git alias can hide a commit or a push. " + NEVER_COMMIT
    if sub == "push" or (sub == "tag" and not _is_tag_listing(sub_args)):
        return (
            "ask",
            f"`git {sub}` publishes to the remote (a push to main deploys "
            "to dev). Confirm this is intended, e.g. for the release skill.",
        )
    if sub == "pull":
        return "ask", "`git pull` can create a merge commit. Confirm."
    return None


def _check_infra(program: str, args: list[str]) -> Decision:
    sub, rest = _subcommand(args)
    if sub in INFRA_WRITES or (sub == "state" and rest[:1] and rest[0] in STATE_WRITES):
        return (
            "deny",
            f"`{program} {sub}` changes deployed infrastructure or its state; "
            f"{NEVER_DEPLOY} `plan`, `validate` and `state list` are fine.",
        )
    if sub == "workspace" and rest[:1] == ["delete"]:
        return "deny", f"`{program} workspace delete` drops a state. {NEVER_DEPLOY}"
    return None


def _check_gh(args: list[str]) -> Decision:
    if args[:2] in GH_WORKFLOW_STARTS:
        return (
            "deny",
            "Starting a GitHub Actions workflow (deploy, promote) is a human "
            f"action; {NEVER_DEPLOY}",
        )
    if args[:2] in GH_PUBLISHES:
        return (
            "ask",
            f"`gh {' '.join(args[:2])}` publishes to the repository (a merge "
            "to main deploys to dev). Confirm this is intended.",
        )
    if args[:1] == ["api"]:
        method = None
        sends_fields = False
        i = 1
        while i < len(args):
            option, has_value, value = args[i].partition("=")
            if option in ("-X", "--method"):
                if not has_value:
                    value = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
                method = value.upper()
            elif option.startswith("-X") and len(option) > 2:
                method = option[2:].upper()  # -XPOST
            elif option in GH_API_FIELD_OPTIONS:
                sends_fields = True  # gh api defaults to POST with fields
            i += 1
        if method is None:
            method = "POST" if sends_fields else "GET"
        if method == "GET":
            return None
        if any("/dispatches" in word for word in args):
            return (
                "deny",
                "This GitHub API call starts a workflow (a dispatch); " + NEVER_DEPLOY,
            )
        return "ask", f"`gh api` {method} changes the repository. Confirm."
    return None


def _aws_positionals(args: list[str]) -> list[str]:
    """service, operation and other positional words, with options and
    their values left out."""
    positionals: list[str] = []
    skip_next = False
    for word in args:
        if skip_next:
            skip_next = False
            continue
        if word.startswith("--"):
            skip_next = "=" not in word and word not in AWS_FLAGS
            continue
        positionals.append(word)
    return positionals


def _query_avoids_environment(args: list[str]) -> bool:
    """A Lambda read narrowed by --query to fields that can't include
    environment variables (--query Code.ResolvedImageUri, Runtime,
    'Functions[].FunctionName'), not to a whole configuration."""
    query = None
    for i, word in enumerate(args):
        option, has_value, value = word.partition("=")
        if option == "--query":
            query = value if has_value else (args[i + 1] if i + 1 < len(args) else "")
    if not query:
        return False
    whole = {"@", "*", "Configuration", "Functions", "Functions[]", "Functions[*]"}
    return "environment" not in query.lower() and query.strip() not in whole


def _check_aws(args: list[str]) -> Decision:
    words = _aws_positionals(args)
    if len(words) < 2:
        return None
    service, operation = words[0], words[1]
    if service == "s3":
        # Uploads and deletions; downloading from S3 is read-only.
        if operation in ("rm", "rb") or (
            operation in ("sync", "cp", "mv") and words[-1].startswith("s3://")
        ):
            return "deny", f"This S3 call changes deployed files. {NEVER_DEPLOY}"
        return None
    if service == "lambda" and _query_avoids_environment(args):
        return None
    if (service, operation) in AWS_SECRET_READS or (
        service == "ssm"
        and operation in SSM_PARAMETER_READS
        and "--with-decryption" in args
    ):
        return (
            "deny",
            "This AWS call returns secrets or credentials; AGENTS.md: never "
            "read secrets into output.",
        )
    if (service, operation) == ("ecr", "get-login-password"):
        return "ask", "`aws ecr get-login-password` prints a registry token. Confirm."
    if operation.startswith(
        ("update-", "delete-", "put-", "create-", "invoke", "publish-")
    ):
        return (
            "deny",
            "This AWS call changes deployed resources; "
            f"{NEVER_DEPLOY} Read-only calls (describe, list, get) are fine.",
        )
    return None


def _check_words(raw: list[str], depth: int) -> Decision:
    """The decision for one simple command, already split into words."""
    if any(PASSWORD_EXPANSION.search(word) for word in raw) or any(
        "/proc/" in word and "environ" in word for word in raw
    ):
        return "deny", ENVIRONMENT_DUMP
    secret = _secret_word(raw)
    if secret is not None:
        return (
            "deny",
            f"{secret} holds local secrets or configuration; AGENTS.md: "
            "never read, edit or print real .env files or secrets. "
            "The .env.example templates are fine.",
        )
    words, bare_env = _unwrap(raw)
    if bare_env:
        return "deny", ENVIRONMENT_DUMP
    if not words:
        return None
    program = os.path.basename(words[0])
    args = words[1:]

    if program in SHELLS or program == "eval":
        script = _shell_script(args) if program in SHELLS else " ".join(args)
        if script is not None:
            if depth >= MAX_NESTING:
                return "deny", "Too deeply nested to check; run the command directly."
            return check_command(script, depth + 1)
    if _environment_dump(program, args):
        return "deny", ENVIRONMENT_DUMP
    if program == "git":
        return _check_git(words)
    if program in ("tofu", "terraform"):
        return _check_infra(program, args)
    if program == "gh":
        return _check_gh(args)
    if program == "aws":
        return _check_aws(args)
    if (program, args[0] if args else "") in PUBLISHERS:
        return "deny", f"`{program} {args[0]}` publishes a package. {NEVER_DEPLOY}"
    if program == "docker" and _deletes_docker_data(args):
        return (
            "ask",
            "This deletes Docker volumes, including the local Postgres data. "
            "Confirm the data can go.",
        )
    if "downgrade" in args and (program == "alembic" or "alembic" in args):
        # `alembic downgrade`, or through `uv run` / `python -m`.
        return "ask", ALEMBIC_DOWNGRADE
    return None


def check_command(command: str, depth: int = 0) -> Decision:
    """(decision, reason) for a Bash command line, or None. A deny
    anywhere wins; otherwise every ask is collected."""
    asks: list[str] = []
    for part in _split_commands(_without_heredoc_bodies(command)):
        result = _check_words(_words(part), depth)
        if result is None:
            continue
        if result[0] == "deny":
            return result
        asks.append(result[1])
    if asks:
        return "ask", " ".join(dict.fromkeys(asks))
    return None


def _is_tag_listing(args: list[str]) -> bool:
    """`git tag`, `git tag -l ...`, `git tag --list`: read-only."""
    return not args or args[0] in ("-l", "--list", "-n") or args[0].startswith("-n")


def _deletes_docker_data(args: list[str]) -> bool:
    if args[:2] == ["volume", "rm"] or args[:2] == ["volume", "prune"]:
        return True
    if args[:1] == ["compose"] and "down" in args:
        return "-v" in args or "--volumes" in args
    return args[:2] == ["system", "prune"] and "--volumes" in args


def check_file(tool_input: dict) -> Decision:
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


def decide(event: dict) -> Decision:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool == "Bash":
        return check_command(tool_input.get("command", ""))
    if tool in FILE_TOOLS:
        return check_file(tool_input)
    return None


def _emit(decision: str, reason: str) -> None:
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


def main() -> int:
    # Fail closed: a payload this can't read, or a bug in the rules,
    # blocks the tool call with a reason instead of letting it through.
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("not a JSON object")
    except ValueError:
        _emit(
            "deny",
            "couldn't read the tool call, so it can't be checked; blocking it. "
            "If this keeps happening, run `make test-hooks`.",
        )
        return 0
    try:
        result = decide(event)
    except Exception as exc:  # any bug must block the call, not let it pass
        result = (
            "deny",
            f"the hook crashed ({type(exc).__name__}: {exc}), so this call "
            "can't be checked; blocking it. Fix agent-hooks/guard.py "
            "(`make test-hooks`).",
        )
    if result is not None:
        _emit(*result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
