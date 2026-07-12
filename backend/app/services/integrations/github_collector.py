"""Collect GitHub evidence (commits, pull requests, merges) for an incident.

Normalizes GitHub API responses into the same raw-evidence shape produced by
the fake collectors, so the investigation engine is provider-agnostic. All
free-text content is secret-redacted before it leaves this module.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.services.integrations.collector_interface import CollectorError
from app.services.integrations.github_client import GithubClient
from app.services.knowledge_builder.secret_redactor import redact_secrets

_SOURCE = "github"
_DEPLOY_KEYWORDS = ("deploy", "release", "hotfix", "rollback", "revert", "ship", "publish")


class GithubCollector:
    name = "github_collector"

    def __init__(
        self,
        client: GithubClient,
        *,
        default_repo: str = "",
    ) -> None:
        self._client = client
        self._default_repo = default_repo

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        repo = self._resolve_repo(service_name, alert_context)
        if not repo:
            return []

        branch = self._resolve_branch(alert_context)
        evidence: list[dict] = []
        try:
            commits = self._client.get_commits(
                repo, since=start_time, until=end_time, branch=branch
            )
            for commit in commits:
                normalized = self._normalize_commit(repo, branch, commit)
                if normalized:
                    evidence.append(normalized)

            pulls = self._client.get_pull_requests(repo, state="all")
            for pull in pulls:
                normalized = self._normalize_pull(repo, pull, start_time, end_time)
                if normalized:
                    evidence.append(normalized)
        except httpx.HTTPError as exc:
            raise CollectorError(f"GitHub collection failed for {repo}: {exc}") from exc

        return evidence

    def _resolve_repo(self, service_name: str, alert_context: dict) -> str:
        hint = (alert_context or {}).get("github_repo")
        if isinstance(hint, str) and "/" in hint:
            return hint
        if "/" in (service_name or ""):
            return service_name
        return self._default_repo

    def _resolve_branch(self, alert_context: dict) -> str | None:
        branch = (alert_context or {}).get("github_branch")
        return branch if isinstance(branch, str) and branch else None

    def _normalize_commit(self, repo: str, branch: str | None, commit: dict) -> dict | None:
        if not isinstance(commit, dict):
            return None
        sha = str(commit.get("sha") or "")
        commit_body = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        message = str(commit_body.get("message") or "")
        first_line = message.splitlines()[0] if message else "(no message)"

        author_info = commit_body.get("author") if isinstance(commit_body, dict) else {}
        author = ""
        observed = None
        if isinstance(author_info, dict):
            author = str(author_info.get("name") or "")
            observed = author_info.get("date")
        login = ""
        if isinstance(commit.get("author"), dict):
            login = str(commit["author"].get("login") or "")

        is_deploy = any(kw in message.lower() for kw in _DEPLOY_KEYWORDS)
        evidence_type = "deploy" if is_deploy else "commit"
        short_sha = sha[:7]

        return {
            "source": _SOURCE,
            "evidence_type": evidence_type,
            "title": redact_secrets(f"Commit {short_sha} on {repo}: {first_line}").redacted_text,
            "content": redact_secrets(message or first_line).redacted_text,
            "observed_at": observed,
            "metadata": {
                "repo": repo,
                "branch": branch,
                "sha": sha,
                "author": author or login,
                "author_login": login,
                "deploy_related": is_deploy,
                "url": commit.get("html_url"),
            },
        }

    def _normalize_pull(
        self,
        repo: str,
        pull: dict,
        start_time: datetime,
        end_time: datetime,
    ) -> dict | None:
        if not isinstance(pull, dict):
            return None
        merged_at = pull.get("merged_at")
        updated_at = pull.get("updated_at")
        observed = merged_at or updated_at
        # Keep PRs relevant to the investigation window.
        if not _in_window(observed, start_time, end_time):
            return None

        number = pull.get("number")
        title = str(pull.get("title") or "")
        body = str(pull.get("body") or "")
        merged = bool(merged_at)
        state = "merged" if merged else str(pull.get("state") or "open")
        evidence_type = "merge" if merged else "pull_request"

        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
        user = pull.get("user") if isinstance(pull.get("user"), dict) else {}

        return {
            "source": _SOURCE,
            "evidence_type": evidence_type,
            "title": redact_secrets(f"PR #{number} ({state}): {title}").redacted_text,
            "content": redact_secrets(body or title).redacted_text,
            "observed_at": observed,
            "metadata": {
                "repo": repo,
                "number": number,
                "state": state,
                "merged": merged,
                "author": str(user.get("login") or ""),
                "head_branch": str(head.get("ref") or ""),
                "base_branch": str(base.get("ref") or ""),
                "url": pull.get("html_url"),
            },
        }


def _in_window(value, start_time: datetime, end_time: datetime) -> bool:
    if not value:
        return True
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is None:
        return True
    return start_time <= ts <= end_time
