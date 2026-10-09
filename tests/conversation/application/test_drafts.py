import re

from github_orchestrator.domain import Location, Side
from tests.conversation.support import world

GITHUBS_THREAD_PREFIXES = ("PRRT_", "IC_", "PRR_")

def test_a_draft_is_keyed_by_a_thread_key_github_never_hands_out(settings):
    threads = world(settings).threads()

    keys = [threads.open_draft("rename it", Location(path="f.py", line=2, side=Side.AFTER)).key
            for _ in range(50)]

    for key in keys:
        assert re.fullmatch(r"[A-Za-z0-9_-]+", key)
        assert not key.startswith(GITHUBS_THREAD_PREFIXES)
    assert len(set(keys)) == len(keys)


def test_a_draft_is_opened_as_the_account_and_kept_under_its_key(settings):
    here = world(settings)

    drafted = here.threads().open_draft("rename it", Location(path="f.py", line=2, side=Side.AFTER))

    assert here.load(drafted.key) == drafted
    assert drafted.author == settings.config.gh_account
    assert drafted.standing == "draft"
