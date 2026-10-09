GIST_MAX_CHARS = 60


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
