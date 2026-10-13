#!/bin/sh
# Runs agent-hooks/guard.py for Claude Code's PreToolUse hook
# (.claude/settings.json), failing closed: if python3 is missing, or
# guard.py exits with an error (a crash, a syntax error), the tool call
# is blocked with a message on stderr instead of every rule silently
# turning off. Exit code 2 is Claude Code's "block this call".
#
# stdin (the tool call) and stdout (guard.py's decision) pass straight
# through. POSIX sh, no other dependencies.

dir=$(cd "$(dirname "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
    echo "agent-hooks: python3 not found, so the guard hook can't check this tool call; blocking it. Install Python 3.9+ (see agent-hooks/README.md)." >&2
    exit 2
fi

python3 "$dir/guard.py"
status=$?
if [ "$status" -ne 0 ]; then
    echo "agent-hooks: guard.py failed (exit $status), so this tool call can't be checked; blocking it. Run 'make test-hooks' to find the problem." >&2
    exit 2
fi
