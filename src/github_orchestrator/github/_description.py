import re

_DETAILED_REVIEWER_LINE = re.compile(r"^(\s*detailed reviewer:).*$", re.IGNORECASE | re.MULTILINE)


def with_detailed_reviewer(body: str, login: str) -> str:
    named, found = _DETAILED_REVIEWER_LINE.subn(lambda line: f"{line.group(1)} @{login}", body,
                                                count=1)
    if found:
        return named
    line = f"Detailed reviewer: @{login}"
    return f"{body.rstrip()}\n\n{line}" if body.strip() else line
