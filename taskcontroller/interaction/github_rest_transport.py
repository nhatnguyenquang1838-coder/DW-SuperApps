"""Minimal production GitHub REST transport for TaskController mailbox/v2.

The transport owns only issue-comment I/O.  It never interprets mailbox
semantics and never serializes credentials into TaskController records.
Authentication is supplied by the host and used only in the HTTP Authorization
header.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.github_mailbox_v2 import GitHubIssueComment


_GITHUB_ACCEPT = "application/vnd.github+json"
_GITHUB_API_VERSION = "2022-11-28"


@dataclass(frozen=True, slots=True)
class GitHubRestConfig:
    api_url: str = "https://api.github.com"
    user_agent: str = "dw-taskcontroller-mailbox-v2"
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.api_url.startswith("https://"):
            raise TaskControllerValidationError("GitHub REST api_url must use https")
        if not self.user_agent.strip():
            raise TaskControllerValidationError("GitHub REST user_agent must be non-empty")
        if self.timeout_seconds <= 0:
            raise TaskControllerValidationError("GitHub REST timeout_seconds must be > 0")


class GitHubRestIssueCommentTransport:
    """GitHub REST implementation of the mailbox issue-comment host port."""

    def __init__(
        self,
        token: str,
        *,
        config: GitHubRestConfig | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(token, str) or not token.strip():
            raise TaskControllerValidationError("GitHub REST token must be non-empty")
        self._token = token.strip()
        self._config = config or GitHubRestConfig()
        self._opener = opener or urllib.request.urlopen

    @staticmethod
    def _repository_parts(repository: str) -> tuple[str, str]:
        if not isinstance(repository, str):
            raise TaskControllerValidationError("GitHub repository must be owner/name")
        parts = repository.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise TaskControllerValidationError("GitHub repository must be owner/name")
        return parts[0], parts[1]

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": _GITHUB_ACCEPT,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            "User-Agent": self._config.user_agent,
        }

    def _json_request(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, str]]:
        data = None
        headers = self._headers()
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self._config.timeout_seconds) as response:
                raw = response.read()
                response_headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise TaskControllerValidationError(
                f"GitHub REST {method} failed with HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TaskControllerValidationError(
                f"GitHub REST {method} transport failed: {exc.reason}"
            ) from exc

        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError as exc:
            raise TaskControllerValidationError("GitHub REST response is not valid JSON") from exc
        return decoded, response_headers

    def list_comments(self, repository: str, issue_number: int):
        owner, repo = self._repository_parts(repository)
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number <= 0:
            raise TaskControllerValidationError("GitHub issue_number must be int > 0")

        comments: list[GitHubIssueComment] = []
        page = 1
        while True:
            url = (
                f"{self._config.api_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
                f"?per_page=100&page={page}"
            )
            decoded, _headers = self._json_request(method="GET", url=url)
            if not isinstance(decoded, list):
                raise TaskControllerValidationError("GitHub comments response must be an array")
            for item in decoded:
                if not isinstance(item, dict):
                    raise TaskControllerValidationError("GitHub comment entry must be an object")
                comment_id = item.get("id")
                body = item.get("body")
                if isinstance(comment_id, bool) or not isinstance(comment_id, int):
                    raise TaskControllerValidationError("GitHub comment id is invalid")
                if not isinstance(body, str):
                    raise TaskControllerValidationError("GitHub comment body is invalid")
                comments.append(GitHubIssueComment(str(comment_id), body))
            if len(decoded) < 100:
                break
            page += 1
        return tuple(comments)

    def create_comment(self, repository: str, issue_number: int, body: str) -> GitHubIssueComment:
        owner, repo = self._repository_parts(repository)
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number <= 0:
            raise TaskControllerValidationError("GitHub issue_number must be int > 0")
        if not isinstance(body, str) or not body:
            raise TaskControllerValidationError("GitHub comment body must be non-empty")

        url = f"{self._config.api_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        decoded, _headers = self._json_request(method="POST", url=url, payload={"body": body})
        if not isinstance(decoded, dict):
            raise TaskControllerValidationError("GitHub create-comment response must be an object")
        comment_id = decoded.get("id")
        observed_body = decoded.get("body")
        if isinstance(comment_id, bool) or not isinstance(comment_id, int):
            raise TaskControllerValidationError("GitHub created comment id is invalid")
        if observed_body != body:
            raise TaskControllerValidationError("GitHub created comment exact body readback differs")
        return GitHubIssueComment(str(comment_id), observed_body)


__all__ = ["GitHubRestConfig", "GitHubRestIssueCommentTransport"]
