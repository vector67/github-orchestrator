from collections.abc import Sequence

GIST_MAX_CHARS = 60
GIST_ASK_CHARS = 45
GIST_LABEL = "gist:"


def fits(texts: Sequence[str]) -> bool:
    said = " ".join(text.strip() for text in texts)
    return "\n" not in said and len(said) <= GIST_MAX_CHARS


def gist_in(answer: str) -> str:
    said = answer.strip()
    if said.lower().startswith(GIST_LABEL):
        said = said[len(GIST_LABEL):]
    said = said.strip().rstrip(".")
    if said[:1].isupper() and said[1:2].islower():
        said = said[0].lower() + said[1:]
    return clip(said)


def clip(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= GIST_MAX_CHARS:
        return text
    return text[: GIST_MAX_CHARS - 1].rstrip() + "…"


def fallback_summary(body: str) -> str:
    in_fence = False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        return clip(line)
    return ""
