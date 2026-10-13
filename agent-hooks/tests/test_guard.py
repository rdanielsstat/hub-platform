"""agent-hooks/guard.py: the decisions, and the JSON contract with
Claude Code. Standard library only:

    python3 -m unittest discover -s agent-hooks/tests -t agent-hooks

(or `make test-hooks`), from the repo root."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard.py"
sys.path.insert(0, str(HOOK.parent))

import guard  # noqa: E402


def bash(command: str):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": command}})


def file_tool(tool: str, path: str):
    key = {"NotebookEdit": "notebook_path", "Grep": "path"}.get(tool, "file_path")
    return guard.decide({"tool_name": tool, "tool_input": {key: path}})


def decision(result) -> str | None:
    return result[0] if result else None


class SecretFiles(unittest.TestCase):
    def test_real_env_files_and_secrets_are_denied_to_every_file_tool(self):
        for path in (
            "backend/.env",
            "/abs/frontend/.env",
            ".env.local",
            "frontend/.env.production",
            "config/prod.env",
            ".secrets",
            "infra/hub/terraform.tfvars",
        ):
            for tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(decision(file_tool(tool, path)), "deny")

    def test_templates_and_ordinary_files_are_allowed(self):
        for path in (
            "backend/.env.example",
            "frontend/.env.example",
            "infra/hub/terraform.tfvars.example",
            "backend/app/core/config.py",
            ".gitignore",
            "docs/environment.md",
        ):
            with self.subTest(path=path):
                self.assertIsNone(file_tool("Read", path))
                self.assertIsNone(file_tool("Edit", path))

    def test_shell_access_to_secrets_is_denied(self):
        for command in (
            "cat backend/.env",
            "head -5 frontend/.env.local",
            "cd backend && source .env",
            "grep SECRET < backend/.env",
            "echo X=1 >> backend/.env",
            "cp backend/.env /tmp/x",
            'cat "$CLAUDE_PROJECT_DIR/backend/.env"',
            "docker compose --env-file=.env up",
            "cat .secrets",
            "less infra/hub/terraform.tfvars",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "deny")

    def test_templates_and_patterns_in_commands_are_allowed(self):
        for command in (
            "cat backend/.env.example",
            "diff backend/.env.example frontend/.env.example",
            r"grep -n '\.env' README.md",
            "git grep -n 'env.*example'",
            "ls -a backend",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_excluding_a_secrets_file_is_not_reading_it(self):
        # The scans in security/IAC_SCANS.md name terraform.tfvars to skip it.
        for command in (
            "tfsec infra/hub --exclude-path terraform.tfvars --minimum-severity HIGH",
            "uvx checkov -d infra/hub --skip-path terraform.tfvars --compact",
            "grep -rn SECRET backend --exclude=.env",
            "rsync -a backend/ /tmp/b --exclude .env",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))
        # ...but only the option's own value is skipped.
        self.assertEqual(
            decision(bash("grep -rn X --exclude-dir node_modules backend/.env")),
            "deny",
        )

    def test_heredoc_bodies_are_data_but_their_target_is_checked(self):
        writes_docs = "cat > notes.md <<'EOF'\nSkip terraform.tfvars and .env\nEOF"
        self.assertIsNone(bash(writes_docs))
        python_script = 'python3 - <<"PY"\nprint("backend/.env")\nPY\nls'
        self.assertIsNone(bash(python_script))
        writes_secret = "cat <<EOF > backend/.env\nX=1\nEOF"
        self.assertEqual(decision(bash(writes_secret)), "deny")
        after_heredoc = "cat <<-EOF\nhello\n\tEOF\ncat .secrets"
        self.assertEqual(decision(bash(after_heredoc)), "deny")
        # A here-string (<<<) opens no body, so the next line is still checked.
        self.assertEqual(decision(bash("cat <<< EOF\ncat backend/.env")), "deny")


class Git(unittest.TestCase):
    def test_commits_are_denied_however_written(self):
        for command in (
            "git commit -m 'feat: x'",
            "git add -A && git commit -am x",
            "git -C backend commit -m x",
            "git -c user.name=x commit -m y",
            "GIT_AUTHOR_NAME=x git commit -m y",
            "cd frontend; git commit --amend --no-edit",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "deny")

    def test_push_and_tagging_ask_first(self):
        for command in (
            "git push origin main",
            "git push origin v1.1.0",
            'git tag -a v1.1.0 -m "Release v1.1.0"',
            "git tag -d v1.1.0",
            "gh pr merge 12 --squash",
            "gh release create v1.1.0",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "ask")

    def test_read_only_git_is_allowed(self):
        for command in (
            "git status",
            "git diff --stat",
            "git log --oneline -5",
            "git tag",
            "git tag -l 'v1.*'",
            "git tag --list",
            "git describe --tags",
            "git show HEAD:frontend/package.json",
            "git commit-graph verify",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


class Deploys(unittest.TestCase):
    def test_deploys_are_denied(self):
        for command in (
            "tofu apply",
            "cd infra/hub && tofu apply -auto-approve",
            "terraform destroy",
            "tofu import aws_s3_bucket.x y",
            "gh workflow run promote.yml",
            "aws lambda update-function-code --function-name x --image-uri y",
            "aws lambda invoke --function-name hub-dev-bootstrap out.json",
            "aws s3 sync dist s3://bucket",
            "aws s3 cp index.html s3://bucket/index.html",
            "aws s3 rm s3://bucket/x",
            "aws cloudfront create-invalidation --distribution-id X --paths '/*'",
            "sudo tofu apply",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "deny")

    def test_read_only_infra_and_aws_calls_are_allowed(self):
        for command in (
            "tofu plan",
            "tofu validate",
            "tofu fmt -check",
            "gh workflow list",
            "gh run view 123 --log",
            "aws sts get-caller-identity",
            "aws lambda list-aliases --function-name x",
            "aws s3 ls s3://bucket",
            "aws s3 cp s3://bucket/index.html .",
            "aws s3 cp s3://bucket/index.html . --region us-east-1",
            "aws ssm get-parameter --name /hub-dev/db-url",
            "aws logs tail /aws/lambda/hub-dev-backend",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


class DeployBypasses(unittest.TestCase):
    """H3: each bypass found in the 2026-10-13 sweep, and the variants
    found auditing each command family."""

    def assert_denied(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "deny")

    def assert_asks(self, *commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "ask")

    def test_tofu_global_options_before_the_subcommand(self):
        self.assert_denied(
            "tofu -chdir=infra/hub apply -auto-approve",
            "tofu -chdir=infra/hub destroy",
            "terraform -chdir=infra/hub apply",
            "tofu -no-color apply",
        )

    def test_tofu_state_changes(self):
        self.assert_denied(
            "tofu state rm aws_s3_bucket.x",
            "tofu state mv a b",
            "tofu state push terraform.tfstate.backup",
            "tofu -chdir=infra/hub state rm x",
            "tofu untaint x",
            "tofu force-unlock 1234",
            "tofu workspace delete prod",
        )
        for command in (
            "tofu state list",
            "tofu -chdir=infra/hub plan",
            "tofu workspace list",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_shell_wrappers_are_inspected(self):
        self.assert_denied(
            "bash -c 'git commit -m x'",
            'sh -c "git commit -m x"',
            "zsh -c 'tofu apply'",
            "bash -lc 'cd infra/hub && tofu apply'",
            "eval 'git commit -m x'",
            "eval git commit -m x",
            "env -i PATH=/usr/bin git commit -m x",
            "sudo -u rob git commit -m x",
            "nohup bash -c 'git commit -m x'",
            "xargs -I{} git commit -m {}",
        )
        self.assert_asks("bash -c 'git push origin main'")
        self.assertIsNone(bash("bash -c 'ls -la'"))

    def test_separators_inside_quotes_stay_in_one_command(self):
        # Splitting at ; or && inside quotes used to cut the quoted script
        # in two and mangle its last word ("destroy\"").
        self.assert_denied(
            'sh -c "cd infra/hub; tofu destroy"',
            "bash -c 'git add -A && git commit -m x'",
        )
        self.assertIsNone(bash("echo 'docs: run tofu plan; never tofu apply'"))

    def test_git_commands_that_create_commits(self):
        self.assert_denied(
            "git merge feature",
            "git cherry-pick abc123",
            "git revert HEAD",
            "git am < fix.patch",
            "git rebase main",
            "git commit-tree HEAD^{tree} -m x",
            "git -c alias.ci=commit ci -m x",
            "git config alias.ci commit",
            "git config --global alias.ci commit",
        )
        self.assert_asks("git pull", "git pull --rebase origin main")
        for command in ("git merge-base main HEAD", "git config --list"):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_gh_api_workflow_dispatch_and_writes(self):
        self.assert_denied(
            "gh api -X POST repos/o/r/actions/workflows/promote.yml/dispatches",
            "gh api --method POST /repos/o/r/actions/workflows/1/dispatches -f ref=main",
            "gh api repos/o/r/actions/workflows/ci.yml/dispatches -f ref=main",
            "gh api repos/o/r/dispatches -f event_type=deploy",
            "gh run rerun 123",
            "gh workflow enable promote.yml",
        )
        self.assert_asks(
            "gh api -X PATCH repos/o/r -f description=x",
            "gh api repos/o/r/issues -f title=x",
            "gh api --method DELETE repos/o/r/git/refs/tags/v1",
            "gh api repos/o/r/rulesets --input rules.json",
        )
        for command in ("gh api repos/o/r", "gh api -X GET repos/o/r/actions/runs"):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_aws_secret_reads(self):
        self.assert_denied(
            "aws ssm get-parameter --name /hub-dev/db-url --with-decryption",
            "aws ssm get-parameters --names a b --with-decryption",
            "aws ssm get-parameters-by-path --path /hub-prod --with-decryption",
            "aws secretsmanager get-secret-value --secret-id x",
            "aws kms decrypt --ciphertext-blob fileb://x",
            "aws lambda get-function --function-name hub-prod-backend",
            "aws lambda get-function-configuration --function-name hub-prod-backend",
            "aws lambda list-functions",
            "aws configure export-credentials",
            "aws sts get-session-token",
            "aws sts assume-role --role-arn x --role-session-name y",
            "aws lambda get-function --function-name x --query Configuration",
            "aws lambda get-function --function-name x --query Configuration.Environment",
            "aws lambda list-functions --query 'Functions[].Environment'",
        )
        self.assert_asks("aws ecr get-login-password")

    def test_lambda_reads_narrowed_to_safe_fields_are_allowed(self):
        # security/IAC_SCANS.md finds the prod image this way.
        for command in (
            "aws lambda get-function --function-name hub-prod-backend "
            "--query Code.ResolvedImageUri --output text",
            "aws lambda get-function-configuration --function-name x --query Runtime",
            "aws lambda list-functions --query 'Functions[].FunctionName'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_aws_s3_uploads_with_options_anywhere(self):
        self.assert_denied(
            "aws s3 cp dist s3://bucket --recursive --region us-east-1",
            "aws s3 cp index.html s3://bucket/ --cache-control max-age=60",
            "aws --region us-east-1 s3 sync dist s3://bucket --delete",
            "aws s3 mv x s3://bucket/x --profile prod",
            "aws s3 sync dist s3://bucket --exclude '*.map' --region us-east-1",
        )

    def test_publishing_packages(self):
        self.assert_denied(
            "pnpm publish",
            "npm publish --access public",
            "uv publish",
            "twine upload dist/*",
        )


class EnvironmentDumps(unittest.TestCase):
    """H1: commands that print the environment, where a credential such
    as the MCP server's could sit."""

    def test_environment_dumps_are_denied(self):
        for command in (
            "printenv",
            "printenv HUB_PASSWORD",
            "env",
            "env -0",
            "env | grep HUB",
            "set",
            "set | grep HUB",
            "export",
            "export -p",
            "declare -p",
            "declare -x",
            "declare -p HUB_PASSWORD",
            "typeset -x",
            "cat /proc/self/environ",
            "xargs -0 -n1 < /proc/1/environ",
            "strings /proc/$$/environ",
            "tr '\\0' '\\n' < /proc/12345/environ",
            "echo $HUB_PASSWORD",
            'echo "${HUB_PASSWORD}"',
            "ps eww",
            "ps auxe",
            "ps -E -p 123",
            "ps -o command -E",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "deny")

    def test_ordinary_uses_are_allowed(self):
        for command in (
            "env FOO=1 ls",
            "env -i PATH=/usr/bin ls",
            "set -euo pipefail",
            "export FOO=1",
            "ps aux",
            "ps -p 123 -o pid,command",
            "grep -rn HUB_PASSWORD mcp-server",
            "echo $HOME",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


class DataLoss(unittest.TestCase):
    def test_deleting_local_data_asks_first(self):
        for command in (
            "docker compose down -v",
            "docker compose down --volumes",
            "docker volume rm hub-platform_postgres_data",
            "docker volume prune -f",
            "docker system prune --volumes",
            "alembic downgrade -1",
            "uv run alembic downgrade base",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(bash(command)), "ask")

    def test_keeping_data_is_allowed(self):
        for command in (
            "docker compose down",
            "docker compose up -d --build",
            "make docker-down",
            "uv run alembic upgrade head",
            "uv run alembic revision --autogenerate -m x",
        ):
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


class Robustness(unittest.TestCase):
    def test_unbalanced_quotes_still_catch_plain_commits(self):
        self.assertEqual(decision(bash("git commit -m 'oops")), "deny")

    def test_other_tools_and_empty_input_are_left_alone(self):
        self.assertIsNone(guard.decide({"tool_name": "WebFetch", "tool_input": {}}))
        self.assertIsNone(guard.decide({}))
        self.assertIsNone(bash(""))

    def test_a_deny_wins_over_an_ask_in_the_same_line(self):
        self.assertEqual(decision(bash("git push && git commit -m x")), "deny")


class HookContract(unittest.TestCase):
    """The script as Claude Code runs it: JSON in on stdin, a
    PreToolUse permission decision out on stdout, exit 0."""

    def run_hook(self, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_a_denied_call_prints_the_decision(self):
        done = self.run_hook(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git commit -m x"},
                }
            )
        )
        self.assertEqual(done.returncode, 0)
        output = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("agents never commit", output["permissionDecisionReason"])

    def test_an_allowed_call_prints_nothing(self):
        done = self.run_hook(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        )
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_garbage_input_fails_closed(self):
        # L7: input the hook can't read is denied, not waved through.
        done = self.run_hook("not json")
        self.assertEqual(done.returncode, 0)
        output = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("couldn't read", output["permissionDecisionReason"])


class FailsClosed(unittest.TestCase):
    """L7: a crash, or no python3 at all, blocks the tool call with a
    message instead of silently turning every rule off."""

    RUNNER = HOOK.parent / "run-guard.sh"

    def test_a_crash_in_the_rules_denies(self):
        original = guard.decide

        def boom(event):
            raise RuntimeError("simulated bug")

        guard.decide = boom
        stdin, stdout = sys.stdin, sys.stdout
        try:
            sys.stdin = io.StringIO(json.dumps({"tool_name": "Bash"}))
            sys.stdout = io.StringIO()
            code = guard.main()
            printed = sys.stdout.getvalue()
        finally:
            guard.decide = original
            sys.stdin, sys.stdout = stdin, stdout
        self.assertEqual(code, 0)
        output = json.loads(printed)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("RuntimeError", output["permissionDecisionReason"])

    def run_runner(self, path: str, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/bin/sh", str(self.RUNNER)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": path},
        )

    def tool_dir(self, **scripts: str) -> str:
        """A PATH directory with dirname, plus the given stub programs."""
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        os.symlink(shutil.which("dirname"), os.path.join(directory, "dirname"))
        for name, body in scripts.items():
            path = os.path.join(directory, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n" + body + "\n")
            os.chmod(path, 0o755)
        return directory

    def test_runner_blocks_when_python3_is_missing(self):
        done = self.run_runner(self.tool_dir(), '{"tool_name": "Bash"}')
        self.assertEqual(done.returncode, 2)
        self.assertIn("python3 not found", done.stderr)

    def test_runner_blocks_when_the_hook_crashes(self):
        done = self.run_runner(self.tool_dir(python3="exit 1"), '{"tool_name": "Bash"}')
        self.assertEqual(done.returncode, 2)
        self.assertIn("guard.py failed", done.stderr)

    def test_runner_passes_decisions_through(self):
        python_dir = os.path.dirname(sys.executable)
        if not os.path.exists(os.path.join(python_dir, "python3")):
            self.skipTest("no python3 next to the test interpreter")
        done = self.run_runner(
            self.tool_dir() + os.pathsep + python_dir,
            json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
            ),
        )
        self.assertEqual(done.returncode, 0)
        output = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")

    def test_settings_run_the_hook_through_the_runner(self):
        settings = json.loads(
            (HOOK.parents[1] / ".claude" / "settings.json").read_text()
        )
        (entry,) = settings["hooks"]["PreToolUse"]
        (hook,) = entry["hooks"]
        self.assertIn("agent-hooks/run-guard.sh", hook["command"])


if __name__ == "__main__":
    unittest.main()
