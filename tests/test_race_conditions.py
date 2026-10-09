import threading

from tests.builders import a_pr
from tests.change_detection.support import PR, REPO
from tests.settings.support import disk_holds

THE_PR = a_pr(PR, REPO)


class TestHoldFlagToctou:
    def test_concurrent_holds_and_resumes_never_crash(self, tmp_path):
        n = 100
        errors = []

        def setter(on_hold):
            try:
                disk_holds(tmp_path).set_on_hold(a_pr(1, "org/repo"), on_hold)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=setter, args=(i % 2 == 0,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"hold.clear_on_hold TOCTOU regressed — got {len(errors)} crashes "
            f"(e.g. {type(errors[0]).__name__}: {errors[0]})."
        )
