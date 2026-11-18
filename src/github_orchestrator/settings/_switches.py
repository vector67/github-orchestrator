import json
import logging
from collections.abc import Set
from pathlib import Path
from typing import Any

from github_orchestrator.atomic_write import write_atomically
from github_orchestrator.domain import (
    DismissUntil,
    IgnoredChecks,
    IgnoreFor,
    Pr,
    Repo,
    ReviewerPick,
)
from github_orchestrator.settings._paths import repo_subdir

log = logging.getLogger(__name__)

_OLD_WORDS = {"until-event": DismissUntil.NEXT_EVENT, "until-ready": DismissUntil.READY_FOR_REVIEW}


def _flag_prs(flag_dir: Path) -> set[Pr]:
    if not flag_dir.exists():
        return set()
    flagged = set()
    for path in flag_dir.glob("*/*/*.flag"):
        owner, name, pr_file = path.relative_to(flag_dir).parts
        try:
            flagged.add(Pr(Repo(owner, name), int(pr_file[: -len(".flag")])))
        except ValueError:
            continue
    return flagged


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _remove(pr: Pr, *paths: Path) -> bool:
    ok = True
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("reap %s: failed to remove %s", pr, path, exc_info=True)
            ok = False
    return ok


def _flag_file(flag_dir: Path, pr: Pr) -> Path:
    return repo_subdir(flag_dir, pr.repo) / f"{pr.number}.flag"


class FlagFileHolds:
    def __init__(self, on_hold_dir: Path) -> None:
        self._on_hold_dir = on_hold_dir

    def on_hold(self, pr: Pr) -> bool:
        return _flag_file(self._on_hold_dir, pr).exists()

    def set_on_hold(self, pr: Pr, on_hold: bool) -> None:
        flag = _flag_file(self._on_hold_dir, pr)
        if on_hold:
            _touch(flag)
        else:
            flag.unlink(missing_ok=True)

    def on_hold_prs(self) -> set[Pr]:
        return _flag_prs(self._on_hold_dir)

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, _flag_file(self._on_hold_dir, pr))

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        archived: list[Path] = []
        if not self._on_hold_dir.exists():
            return archived
        for owner_dir in self._on_hold_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in list(owner_dir.iterdir()):
                if not repo_dir.is_dir():
                    continue
                if (owner_dir.name, repo_dir.name) in {(repo.owner, repo.name) for repo in keep}:
                    continue
                dest_parent = into / owner_dir.name
                dest_parent.mkdir(parents=True, exist_ok=True)
                dest = dest_parent / repo_dir.name
                repo_dir.rename(dest)
                archived.append(dest)
        return archived


class FlagFileDismissals:
    def __init__(self, dismissed_dir: Path) -> None:
        self._dismissed_dir = dismissed_dir

    def migrate(self) -> None:
        for pr in self.dismissed_prs():
            dismissal = _OLD_WORDS.get(self._word(pr) or "")
            if dismissal is not None:
                self._dismiss(pr, dismissal)

    def _word(self, pr: Pr) -> str | None:
        path = _flag_file(self._dismissed_dir, pr)
        if not path.exists():
            return None
        try:
            return path.read_text().strip()
        except (OSError, UnicodeDecodeError):
            return None

    def dismissal(self, pr: Pr) -> DismissUntil | None:
        word = self._word(pr)
        if word not in set(DismissUntil):
            return None
        return DismissUntil(word)

    def _dismiss(self, pr: Pr, dismissal: DismissUntil) -> None:
        path = _flag_file(self._dismissed_dir, pr)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dismissal)

    def dismiss_forever(self, pr: Pr) -> None:
        self._dismiss(pr, DismissUntil.FOREVER)

    def dismiss_until_next_event(self, pr: Pr) -> None:
        self._dismiss(pr, DismissUntil.NEXT_EVENT)

    def dismiss_until_ready_for_review(self, pr: Pr) -> None:
        self._dismiss(pr, DismissUntil.READY_FOR_REVIEW)

    def is_hidden(self, pr: Pr, *, events_waiting: bool, draft: bool) -> bool:
        dismissal = self.dismissal(pr)
        if dismissal is DismissUntil.NEXT_EVENT and events_waiting:
            log.info("%s: an event is waiting — ending its dismissal until the next event", pr)
            self.undismiss(pr)
            return False
        if dismissal is DismissUntil.READY_FOR_REVIEW and not draft:
            log.info("%s: no longer a draft — ending its dismissal until ready for review", pr)
            self.undismiss(pr)
            return False
        return dismissal is not None

    def is_dismissed_forever(self, pr: Pr) -> bool:
        return self.dismissal(pr) is DismissUntil.FOREVER

    def undismiss(self, pr: Pr) -> bool:
        try:
            _flag_file(self._dismissed_dir, pr).unlink()
        except FileNotFoundError:
            return False
        return True

    def dismissed_prs(self) -> set[Pr]:
        return _flag_prs(self._dismissed_dir)

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, _flag_file(self._dismissed_dir, pr))


class JsonFileReviewerPicks:
    def __init__(self, picks_dir: Path) -> None:
        self._picks_dir = picks_dir

    def saved(self, pr: Pr) -> ReviewerPick | None:
        try:
            fields = json.loads(self._path(pr).read_text())
            return ReviewerPick(tuple(fields["reviewers"]), fields["detailed"])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("%s: unreadable reviewer pick at %s", pr, self._path(pr), exc_info=True)
            return None

    def save(self, pr: Pr, pick: ReviewerPick) -> None:
        write_atomically(self._path(pr), json.dumps(
            {"reviewers": list(pick.reviewers), "detailed": pick.detailed}).encode())

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, self._path(pr))

    def _path(self, pr: Pr) -> Path:
        return repo_subdir(self._picks_dir, pr.repo) / f"{pr.number}.json"


class JsonFileRerequests:
    def __init__(self, rerequests_dir: Path) -> None:
        self._rerequests_dir = rerequests_dir

    def queued(self, pr: Pr) -> tuple[str, ...]:
        try:
            return tuple(json.loads(self._path(pr).read_text())["reviewers"])
        except FileNotFoundError:
            return ()
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("%s: unreadable re-request queue at %s", pr, self._path(pr), exc_info=True)
            return ()

    def queue(self, pr: Pr, login: str) -> None:
        queued = self.queued(pr)
        if login not in queued:
            self._write(pr, (*queued, login))

    def drop(self, pr: Pr, login: str) -> None:
        queued = self.queued(pr)
        if login in queued:
            self._write(pr, tuple(each for each in queued if each != login))

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, self._path(pr))

    def _write(self, pr: Pr, reviewers: tuple[str, ...]) -> None:
        if not reviewers:
            self.forget(pr)
            return
        write_atomically(self._path(pr), json.dumps({"reviewers": list(reviewers)}).encode())

    def _path(self, pr: Pr) -> Path:
        return repo_subdir(self._rerequests_dir, pr.repo) / f"{pr.number}.json"


def _checks_from(fields: dict[str, Any]) -> IgnoredChecks:
    return IgnoredChecks(frozenset(fields["names"]), bool(fields["every"]),
                         frozenset(fields.get("spared", [])))


def _fields_of(checks: IgnoredChecks) -> dict[str, Any]:
    return {"names": sorted(checks.names), "every": checks.every, "spared": sorted(checks.spared)}


class JsonFileCiIgnores:
    def __init__(self, ci_ignored_dir: Path) -> None:
        self._ci_ignored_dir = ci_ignored_dir

    def ignored(self, pr: Pr, head_sha: str | None) -> IgnoredChecks:
        kept = self._read(self._pr_path(pr))
        this_push = kept.get("this_push")
        pushed = (_checks_from(this_push) if this_push is not None and head_sha is not None
                  and this_push["sha"] == head_sha else IgnoredChecks())
        this_pr = _checks_from(kept["this_pr"]) if "this_pr" in kept else IgnoredChecks()
        repo = self._read(self._repo_path(pr.repo))
        this_repo = _checks_from(repo) if repo else IgnoredChecks()
        return pushed | this_pr | this_repo

    def ignore(self, pr: Pr, checks: IgnoredChecks, ignore_for: IgnoreFor, head_sha: str | None) -> None:
        if ignore_for is IgnoreFor.THIS_REPO:
            repo = self._read(self._repo_path(pr.repo))
            had = _checks_from(repo) if repo else IgnoredChecks()
            write_atomically(self._repo_path(pr.repo), json.dumps(_fields_of(had | checks)).encode())
            return
        kept = self._read(self._pr_path(pr))
        if ignore_for is IgnoreFor.THIS_PR:
            had = _checks_from(kept["this_pr"]) if "this_pr" in kept else IgnoredChecks()
            kept["this_pr"] = _fields_of(had | checks)
        else:
            this_push = kept.get("this_push")
            had = (_checks_from(this_push) if this_push is not None and this_push["sha"] == head_sha
                   else IgnoredChecks())
            kept["this_push"] = {"sha": head_sha, **_fields_of(had | checks)}
        write_atomically(self._pr_path(pr), json.dumps(kept).encode())

    def stop_ignoring(self, pr: Pr) -> None:
        _remove(pr, self._pr_path(pr), self._repo_path(pr.repo))

    def count_again(self, pr: Pr, names: frozenset[str]) -> None:
        kept = self._read(self._pr_path(pr))
        if "this_push" in kept:
            kept["this_push"] = {**kept["this_push"],
                                 **_fields_of(_checks_from(kept["this_push"]).without(names))}
        if "this_pr" in kept:
            kept["this_pr"] = _fields_of(_checks_from(kept["this_pr"]).without(names))
        if kept:
            write_atomically(self._pr_path(pr), json.dumps(kept).encode())
        repo = self._read(self._repo_path(pr.repo))
        if repo:
            write_atomically(self._repo_path(pr.repo),
                             json.dumps(_fields_of(_checks_from(repo).without(names))).encode())

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, self._pr_path(pr))

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            kept = json.loads(path.read_text())
            if not isinstance(kept, dict):
                raise TypeError("not an object")
            return kept
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError):
            log.warning("unreadable ignored checks at %s; counting every check", path, exc_info=True)
            return {}

    def _pr_path(self, pr: Pr) -> Path:
        return repo_subdir(self._ci_ignored_dir, pr.repo) / f"{pr.number}.json"

    def _repo_path(self, repo: Repo) -> Path:
        return repo_subdir(self._ci_ignored_dir, repo) / "repo.json"
