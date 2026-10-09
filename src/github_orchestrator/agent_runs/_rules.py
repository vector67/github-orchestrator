def test_parallelism_note(workers: int) -> str:
    return (
        f"   Cap the test runner's own parallelism: pass `-n {workers}` to "
        f"pytest, never `-n auto`, and use the equivalent for any other runner. "
        f"Other agents are running their own test suites on this machine at the "
        f"same time, and a runner that takes every core starves them and the "
        f"user's own session."
    )
