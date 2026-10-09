from collections.abc import Mapping, Sequence

SEPARATOR = "||"


def comment_gist_prompt(body: str, path: str | None, line: int | None, chars: int) -> str:
    where = f"{path}:{line}" if path and line is not None else (path or "the pull request")
    return (
        "Summarise this pull request review comment in one line of at most "
        f"{chars} characters: lowercase, no trailing period, say what "
        "the reviewer wants changed. Reply with the line alone.\n\n"
        f"Comment on {where}:\n\n{body}"
    )


def thread_gist_prompt(comments: Sequence[tuple[str, str]], path: str | None, line: int | None,
                  chars: int) -> str:
    said = "\n\n".join(f"{author or 'ghost'}: {body}" for author, body in comments)
    return comment_gist_prompt(said, path, line, chars)


def comments_prompt(bodies: Sequence[str], chars: int) -> str:
    numbered = "\n\n".join(f"{at}. {body}" for at, body in enumerate(bodies, 1))
    return (
        "Summarise each of these pull request review comments in one line of at most "
        f"{chars} characters: lowercase, no trailing period, say what the commenter "
        "is asking or saying. Reply on a single line with the summaries in the order "
        f"the comments are numbered, separated by {SEPARATOR}, and nothing else.\n\n"
        f"{numbered}"
    )


def gists_in(answer: str, count: int) -> tuple[str, ...]:
    said = tuple(part.strip() for part in answer.split(SEPARATOR))
    return said if len(said) == count else ("",) * count


def fixes_prompt(fixes: Sequence[tuple[Sequence[tuple[str, str]], str | None]],
                 chars: int) -> str:
    threads = "\n\n".join(
        "\n".join([*(f"{author}: {body}" for author, body in comments),
                   f"fix: {summary or 'no summary'}"])
        for comments, summary in fixes
    )
    return (
        f"These pull request review comments have just been fixed. In at most {chars} "
        "characters, say what the comments asked for and what the fixes do overall, "
        "the way a colleague would sum it up: 'general cleanup', 'missing tests and a "
        "rename'. Lowercase, no trailing period. Reply with the line alone.\n\n"
        f"{threads}"
    )


def _yes(said: bool) -> str:
    return "yes" if said else "no"


def verdict_prompt(comments: Sequence[tuple[str, str, str]], *, viewer: str, pr_author: str,
                   spoke_last: str, viewer_commented: bool, mentions_viewer: bool, kind: str,
                   answers: Mapping[str, str]) -> str:
    thread = "\n\n".join(f"[{label}] {login or 'ghost'}: {body}"
                          for label, login, body in comments)
    offered = "\n".join(f"- {word}: {meaning}" for word, meaning in answers.items())
    return (
        "You sort pull request comment threads for one person, the viewer, who is "
        "reviewing someone else's pull request. Read the thread and decide what it asks "
        "of the viewer now. Each comment is labelled: `you` is the viewer, `PR author` "
        "wrote the pull request, `colleague` is anyone else, `bot` is a review bot.\n\n"
        f"Viewer: {viewer}\n"
        f"PR author: {pr_author or 'unknown'}\n"
        f"Thread kind: {kind}\n"
        f"Spoke last: {spoke_last}\n"
        f"The viewer has commented in this thread: {_yes(viewer_commented)}\n"
        f"The thread @-mentions the viewer: {_yes(mentions_viewer)}\n\n"
        f"Answer with exactly one of these words on the first line, and nothing else:\n"
        f"{offered}\n\n"
        f"The thread, oldest comment first:\n\n{thread}"
    )


def verdict_in(answer: str, answers: Mapping[str, str]) -> str | None:
    word = answer.strip().lower()
    return word if word in answers else None
