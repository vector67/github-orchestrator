from github_orchestrator.board_api.fake import FakeNamesMigration
from github_orchestrator.board_api.interface import BranchNotRenamed, FolderInUse
from tests.board_api.support import THE_PR, holding, one_server, served_hub

BOARD = "/pr/acme/widgets/54"
IN_USE = FolderInUse(pr=THE_PR, thread="PRRT_a",
                     folder="/data/thread-worktrees/acme/widgets/54/PRRT_a")
NOT_RENAMED = BranchNotRenamed(
    pr=THE_PR, thread="PRRT_b", branch="orchestrator/thread/54/PRRT_b",
    new_branch="orchestrator/thread/54/PRRT_b-2", clone="/data/clones/acme/widgets",
    error="error: cannot lock ref 'refs/heads/orchestrator/thread/54/PRRT_b-2': File exists")


def test_while_sessions_are_in_the_migration_s_way_the_wall_is_refused_as_waiting_to_migrate():
    answer = served_hub(migration=FakeNamesMigration([IN_USE])).get("/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"
    assert answer.headers["Retry-After"] == "1"


def test_while_a_branch_would_not_take_its_new_name_the_wall_is_refused_as_waiting_to_migrate():
    answer = served_hub(told=holding(THE_PR),
                        migration=FakeNamesMigration(not_renamed=[NOT_RENAMED])).get(
        "/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"


def test_the_hub_names_each_session_in_the_migration_s_way():
    answer = served_hub(migration=FakeNamesMigration([IN_USE])).get(
        "/api/thread-names-migration")

    assert answer.status_code == 200
    assert answer.json() == {"migrated": False, "sessions": [{
        "repo": "acme/widgets", "number": 54, "thread": "PRRT_a",
        "folder": "/data/thread-worktrees/acme/widgets/54/PRRT_a"}], "branches": []}


def test_the_hub_names_each_branch_that_would_not_take_its_new_name_and_what_git_said():
    answer = served_hub(migration=FakeNamesMigration(not_renamed=[NOT_RENAMED])).get(
        "/api/thread-names-migration")

    assert answer.status_code == 200
    assert answer.json() == {"migrated": False, "sessions": [], "branches": [{
        "repo": "acme/widgets", "number": 54, "thread": "PRRT_b",
        "branch": "orchestrator/thread/54/PRRT_b",
        "new_branch": "orchestrator/thread/54/PRRT_b-2", "clone": "/data/clones/acme/widgets",
        "error": "error: cannot lock ref 'refs/heads/orchestrator/thread/54/PRRT_b-2': "
                 "File exists"}]}


def test_close_sessions_and_migrate_closes_them_and_says_it_migrated():
    migration = FakeNamesMigration([IN_USE])
    hub = served_hub(migration=migration)

    answer = hub.post("/api/thread-names-migration:close-sessions-and-migrate")

    assert answer.status_code == 200
    assert answer.json() == {"migrated": True, "sessions": [], "branches": []}
    assert migration.closed == 1


def test_a_held_prs_board_is_not_served_until_the_thread_names_migrate():
    server = one_server(THE_PR, migration=FakeNamesMigration([IN_USE]))

    answer = server.client.get(f"{BOARD}/api/pull-request")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"
    assert server.panels.asked == []


def test_a_held_prs_board_waits_to_migrate_while_a_branch_would_not_take_its_new_name():
    server = one_server(THE_PR, migration=FakeNamesMigration(not_renamed=[NOT_RENAMED]))

    answer = server.client.get(f"{BOARD}/api/pull-request")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"
