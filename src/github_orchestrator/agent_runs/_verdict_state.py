import re
import unicodedata
from collections.abc import Sequence

VIEWER = "viewer"
PR_AUTHOR = "pr-author"
BOT = "bot"
GHOST = "ghost"
SINCE_VIEWER = "--- comments since viewer's last comment ---"
NOTHING_SINCE_VIEWER = "--- nobody has commented since viewer's last comment ---"
VERDICT_INSTRUCTIONS = "What does this thread ask of viewer now?"

_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"@([\w-]+)")
_EMOJI_ONLY = re.compile(r"^[\s\U0001F300-\U0001FAFF☀-➿️‍]+$")
_JOINERS = "️‍"


def _stand_ins(comments: Sequence[tuple[str, str, str]], viewer: str,
               pr_author: str) -> dict[str, str]:
    names = {viewer: VIEWER}
    if pr_author:
        names[pr_author] = PR_AUTHOR
    colleagues = 0

    def named(login: str) -> None:
        nonlocal colleagues
        if login and login not in names:
            colleagues += 1
            names[login] = f"colleague-{colleagues}"

    for label, login, _ in comments:
        if label != BOT:
            named(login)
    for _, _, body in comments:
        for mention in _MENTION.findall(body):
            named(mention)
    return names


def _scrubbed(body: str, names: dict[str, str]) -> str:
    body = _BARE_URL.sub("", _MARKDOWN_LINK.sub(r"\1", body))
    for login in sorted(names, key=len, reverse=True):
        body = re.sub(rf"(?<![\w-]){re.escape(login)}(?![\w-])", names[login], body,
                      flags=re.IGNORECASE)
    return body.strip()


def _emoji_named(body: str) -> str:
    if not _EMOJI_ONLY.match(body):
        return body
    names = [name.lower() for name in (unicodedata.name(character, None) for character in body
                                       if not character.isspace() and character not in _JOINERS)
             if name]
    return f"{body} [a reply with only the emoji: {', '.join(names)}]"


def verdict_state(comments: Sequence[tuple[str, str, str]], *, viewer: str, pr_author: str,
                  viewer_commented: bool, mentions_viewer: bool, kind: str) -> str:
    names = _stand_ins(comments, viewer, pr_author)
    lines = [f"{names.get(login, login) or GHOST}: {_emoji_named(_scrubbed(body, names))}"
             for _, login, body in comments]
    spoke = [index for index, (_, login, _) in enumerate(comments) if login == viewer]
    if spoke:
        after = spoke[-1] + 1
        lines.insert(after, SINCE_VIEWER if after < len(lines) else NOTHING_SINCE_VIEWER)
    facts = (f"This is {kind}. {VIEWER} is reviewing {PR_AUTHOR}'s pull request. {VIEWER} "
             f"{'has' if viewer_commented else 'has not'} commented in this thread, and "
             f"{'the thread @-mentions viewer' if mentions_viewer else 'nobody @-mentions viewer'}.")
    return "\n\n".join(lines) + f"\n\n{facts}"
