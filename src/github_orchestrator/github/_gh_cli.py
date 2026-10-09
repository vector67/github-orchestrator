import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.github.interface import GhError

log = logging.getLogger(__name__)

GH_TIMEOUT = 120
SEARCH_LIMIT = 1000

Run = Callable[..., subprocess.CompletedProcess[str]]

_GH_FILE_REF_RE = re.compile(r"^@.+")
"""Only `-F/--field` reads a leading @ as a filename; `-f/--raw-field` does not."""


def _parse_paginated(text: str) -> list[Any]:
    text = text.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    combined: list[Any] = []
    idx = 0
    n = len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        page, end = decoder.raw_decode(text, idx)
        if isinstance(page, list):
            combined.extend(page)
        else:
            combined.append(page)
        idx = end
    return combined


class Gh:
    def __init__(self, account: str, run: Run) -> None:
        self._account = account
        self._run = run
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            self._token = self._token_of(self._account)
        return self._token

    def _token_of(self, account: str) -> str:
        try:
            result = self._run(
                ["gh", "auth", "token", "--user", account],
                capture_output=True, text=True, check=True,
                timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise GhError(
                f"gh auth token --user {account} failed (exit {exc.returncode}): "
                f"{stderr or '<no stderr>'} — run `gh auth login` as {account}, "
                f"or set gh_account in config.toml to an account `gh auth status` "
                f"lists"
            ) from exc
        except FileNotFoundError as exc:
            raise GhError(f"gh is not on PATH, so nothing can reach GitHub as {account}") from exc
        return result.stdout.strip()

    def check_login(self, account: str) -> None:
        self._token_of(account)

    def active_account(self) -> str | None:
        try:
            result = self._run(["gh", "api", "user", "--jq", ".login"],
                               capture_output=True, text=True, check=True,
                               timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None
        return result.stdout.strip() or None

    def scopes(self) -> tuple[str, ...]:
        said = self._gh(["gh", "api", "user", "--include"]).stdout
        for line in said.splitlines():
            name, _, value = line.partition(":")
            if name.strip().lower() == "x-oauth-scopes":
                return tuple(sorted(scope.strip() for scope in value.split(",") if scope.strip()))
            if not line.strip():
                break
        return ()

    def check_access(self, account: str, repo: Repo) -> None:
        env = {**os.environ, "GH_TOKEN": self._token_of(account)}
        try:
            self._run(
                ["gh", "repo", "view", str(repo), "--json", "nameWithOwner"],
                env=env, capture_output=True, text=True, check=True,
                timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise GhError(
                f"gh cannot see {repo} as {account} (exit {exc.returncode}): "
                f"{stderr or '<no stderr>'}"
            ) from exc

    def clone(self, repo: Repo, into: Path) -> None:
        try:
            self._run(["gh", "repo", "clone", str(repo), str(into)],
                      capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        except subprocess.CalledProcessError as exc:
            stderr = " ".join((exc.stderr or "").split())
            raise GhError(
                f"gh repo clone {repo} failed (exit {exc.returncode}): "
                f"{stderr or '<no stderr>'}"
            ) from exc

    def _gh(self, cmd: list[str], label: str | None = None,
            stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return self._gh_once(cmd, label, stdin_text)
        except GhError as refused:
            if "HTTP 401" not in str(refused):
                raise
            self._token = None
            return self._gh_once(cmd, label, stdin_text)

    def _gh_once(self, cmd: list[str], label: str | None,
                 stdin_text: str | None) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "GH_TOKEN": self.token()}
        if label is None:
            label = " ".join(cmd)
        feed = ({"input": stdin_text} if stdin_text is not None
                else {"stdin": subprocess.DEVNULL})
        start = time.monotonic()
        try:
            result = self._run(
                cmd, env=env, capture_output=True, text=True, check=True,
                timeout=GH_TIMEOUT, **feed,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise GhError(
                f"{label} failed (exit {exc.returncode}): {stderr or '<no stderr>'}"
            ) from exc
        elapsed_ms = (time.monotonic() - start) * 1000
        log.debug("%s → %d bytes, %.0fms", label, len(result.stdout), elapsed_ms)
        return result

    def api(self, path: str, jq: str | None = None, paginate: bool = False) -> Any:
        cmd = ["gh", "api", path]
        if jq is not None:
            cmd += ["--jq", jq]
        if paginate:
            cmd.append("--paginate")

        result = self._gh(cmd)

        if paginate:
            return _parse_paginated(result.stdout)

        return json.loads(result.stdout)

    def api_post(self, path: str, fields: dict[str, str]) -> Any:
        cmd = ["gh", "api", "-X", "POST", path]
        for key, value in fields.items():
            cmd += ["-f", f"{key}={value}"]

        result = self._gh(cmd, label=f"gh api POST {path}")
        return json.loads(result.stdout)

    def api_json(self, path: str, payload: dict[str, Any],
                 method: str = "POST") -> object:
        """A write whose body is JSON, not the `-f k=v` strings `api_post` sends."""
        result = self._gh(
            ["gh", "api", "--method", method, path, "--input", "-"],
            label=f"gh api {method} {path}",
            stdin_text=json.dumps(payload),
        )
        return json.loads(result.stdout)

    def api_delete(self, path: str) -> None:
        """A DELETE, whose 204 carries no body to parse."""
        self._gh(["gh", "api", "-X", "DELETE", path], label=f"gh api DELETE {path}")

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        cmd = ["gh", "api", "graphql"]
        if variables:
            for key, value in variables.items():
                value_str = str(value)
                if _GH_FILE_REF_RE.match(value_str):
                    raise ValueError(
                        f"graphql variable {key!r} starts with '@' which gh "
                        f"interprets as a file path; refusing to pass {value_str!r}"
                    )
                cmd += ["-F", f"{key}={value_str}"]
        cmd += ["-f", f"query={query}"]

        vars_str = ", ".join(f"{k}={v}" for k, v in (variables or {}).items())
        result = self._gh(cmd, label=f"gh graphql ({vars_str})")
        return json.loads(result.stdout)

    def graphql_mutate(self, mutation: str,
                       variables: dict[str, Any] | None = None) -> Any:
        cmd = ["gh", "api", "graphql"]
        for key, value in (variables or {}).items():
            cmd += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        cmd += ["-f", f"query={mutation}"]

        names = ", ".join(variables or {})
        result = self._gh(cmd, label=f"gh graphql mutation ({names})")
        payload = json.loads(result.stdout)

        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            reasons = "; ".join(str(e.get("message") or e) for e in errors)
            raise GhError(f"gh graphql mutation failed: {reasons}")
        return payload

    def search_prs(self, whose: str, repos: Collection[Repo]) -> list[Pr]:
        cmd = [
            "gh", "search", "prs",
            "--json", "number,repository",
            "--state", "open",
            f"--limit={SEARCH_LIMIT}",
            whose,
            *(f"--repo={repo}" for repo in sorted(repos, key=str)),
        ]

        result = self._gh(cmd)
        raw = json.loads(result.stdout)

        prs = []
        for pr in raw:
            repo_obj = pr.get("repository") or {}
            repo_name = repo_obj.get("nameWithOwner", "")
            if not repo_name:
                log.warning("gh search PR %s has null/empty repository, skipping: %r",
                            pr.get("number"), pr)
                continue
            try:
                found_in = Repo.parse(repo_name)
            except ValueError:
                log.warning("gh search PR %s names a repository that is not owner/name, "
                            "skipping: %r", pr.get("number"), pr)
                continue
            prs.append(Pr(found_in, pr["number"]))
        return prs
