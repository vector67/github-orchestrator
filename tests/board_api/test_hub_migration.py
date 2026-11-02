from github_orchestrator.board_api.fake import FakeNamesMigration
from github_orchestrator.board_api.interface import FolderInUse
from tests.board_api.support import THE_PR, one_server, served_hub

BOARD = "/pr/acme/widgets/54"
IN_USE = FolderInUse(pr=THE_PR, thread="PRRT_a",
                     folder="/data/thread-worktrees/acme/widgets/54/PRRT_a")


def test_while_sessions_are_in_the_migration_s_way_the_wall_is_refused_as_waiting_to_migrate():
    answer = served_hub(migration=FakeNamesMigration([IN_USE])).get("/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"
    assert answer.headers["Retry-After"] == "1"


def test_the_hub_names_each_session_in_the_migration_s_way():
    answer = served_hub(migration=FakeNamesMigration([IN_USE])).get(
        "/api/thread-names-migration")

    assert answer.status_code == 200
    assert answer.json() == {"migrated": False, "sessions": [{
        "repo": "acme/widgets", "number": 54, "thread": "PRRT_a",
        "folder": "/data/thread-worktrees/acme/widgets/54/PRRT_a"}]}


def test_close_sessions_and_migrate_closes_them_and_says_it_migrated():
    migration = FakeNamesMigration([IN_USE])
    hub = served_hub(migration=migration)

    answer = hub.post("/api/thread-names-migration:close-sessions-and-migrate")

    assert answer.status_code == 200
    assert answer.json() == {"migrated": True, "sessions": []}
    assert migration.closed == 1


def test_a_held_prs_board_is_not_served_until_the_thread_names_migrate():
    server = one_server(THE_PR, migration=FakeNamesMigration([IN_USE]))

    answer = server.client.get(f"{BOARD}/api/pull-request")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "waiting-to-migrate"
    assert server.panels.asked == []
