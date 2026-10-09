from pathlib import Path

from github_orchestrator.domain import Pr, Repo


def pr_file(base: Path, pr: Pr, suffix: str) -> Path:
    return Path(base) / pr.repo.owner / pr.repo.name / f"{pr.number}{suffix}"


def tracked_prs(base: Path, suffix: str) -> list[Pr]:
    tracked = []
    for path in Path(base).glob(f"*/*/*{suffix}"):
        try:
            repo = Repo.parse(f"{path.parent.parent.name}/{path.parent.name}")
        except ValueError:
            continue
        if path.stem.isdigit():
            tracked.append(Pr(repo, int(path.stem)))
    return sorted(tracked)
