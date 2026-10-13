"""agent-hooks/guard.py: the decisions, and the JSON contract with
Claude Code. Standard library only:

    python3 -m unittest discover -s agent-hooks/tests -t agent-hooks

(or `make test-hooks`), from the repo root."""

from __future__ import annotations

import json
import subprocess
import sys
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
            "aws lambda get-function --function-name x",
            "aws s3 ls s3://bucket",
            "aws s3 cp s3://bucket/index.html .",
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

    def test_garbage_input_never_blocks(self):
        done = self.run_hook("not json")
        self.assertEqual((done.returncode, done.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
