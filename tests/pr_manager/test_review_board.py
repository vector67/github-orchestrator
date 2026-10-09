
from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.conversation import (
    ConversationState,
    Denied,
    ErrorCode,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import (
    conversation_managers_over,
    fake_conversation_managers,
    hear,
    on_github,
    propose,
    repo_at,
    said,
)
from tests.disk_layout import board_port_file
from tests.pr_manager.support import (
    PR,
    REPO,
    manager_over,
    run_manager,
    seed_state,
)
from tests.settings.support import disk_boards, disk_holds

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_1"


def _carry_on(board):
    return lambda: board.panel.carry_on()


def test_the_board_starts_on_the_port_the_window_was_given(settings, tmp_path):
    port = board_port_file(settings.board_dir, THE_PR)
    port.parent.mkdir(parents=True, exist_ok=True)
    port.write_text("8742")
    board = FakeBoardApi()
    run_manager(settings, is_author=True, worktree=tmp_path, board=board)
    assert board.starts[0]["port"] == 8742


def test_a_restarted_manager_brings_the_board_back_as_it_was(tmp_path):
    settings = fake_settings(tmp_path)
    disk_boards(settings.data_dir).want_board(THE_PR, True)
    board_port_file(settings.board_dir, THE_PR).write_text("8742")
    seed_state(settings, title="Fix the frobnicator", base_branch="main", is_author=False)
    board = FakeBoardApi()
    manager = run_manager(settings, worktree=tmp_path, is_author=False, board=board)
    assert len(board.starts) == 1
    assert board.starts[0]["port"] == 8742
    assert manager.desktop.opened == []
    assert board.running is True


def test_a_restarted_manager_leaves_the_board_down_until_a_poll_says_whose_pr_this_is(
        settings, tmp_path):
    disk_boards(settings.data_dir).want_board(THE_PR, True)
    board = FakeBoardApi()
    run_manager(settings, None, None, worktree=tmp_path, board=board)
    assert board.starts == []


def test_a_board_that_will_not_bind_does_not_take_the_manager_down(settings, tmp_path):
    disk_boards(settings.data_dir).want_board(THE_PR, True)
    seed_state(settings, title="Fix the frobnicator")
    board = FakeBoardApi(taken={disk_boards(settings.data_dir).board_port(THE_PR)})
    reached = []
    run_manager(settings, lambda: reached.append(True), is_author=True, worktree=tmp_path,
                board=board)
    assert reached == [True]
    assert board.running is False


def test_freezing_on_the_wrong_branch_leaves_the_board_running(settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "other-branch")
    board = FakeBoardApi(running=True)
    run_manager(settings, is_author=True, worktree=tmp_path, board=board, working_copies=working_copies)
    assert board.stops == 0


def _proposed(tmp_path, pr_processes=None):
    fake = fake_conversation_managers(FakeAgentRuns(pr_processes or FakePrProcesses()))
    repo_at(fake.working_copies, tmp_path, {"f": "old\n"}, pr=THE_PR)
    fake.watch(THE_PR, is_author=True)
    threads = fake.of(THE_PR)
    on_github(fake.github, KEY, said(1, "rename this"), pr=THE_PR)
    hear(threads)
    propose(fake, threads, KEY, pr=THE_PR)
    return fake


def _manager_over(settings, fake, *script, worktree, board=None):
    return manager_over(settings, *script, is_author=True, worktree=worktree,
                        board=board or FakeBoardApi(),
                        pr_processes=fake.agent_runs.pr_processes, agent_runs=fake.agent_runs,
                        github=fake.github, working_copies=fake.working_copies,
                        conversation_managers=fake)


def _standing(fake):
    return fake.of(THE_PR).get(KEY).standing


def _approved(fake):
    with fake.of(THE_PR).editing(KEY) as editable:
        asked = editable.approve()
    assert not isinstance(asked, Denied), asked


def test_a_tick_drains_the_boards_decisions(settings, tmp_path):
    fake = _proposed(tmp_path)
    _approved(fake)

    _manager_over(settings, fake, worktree=tmp_path).run()

    assert _standing(fake) is ConversationState.DONE


def test_a_tick_drains_a_reply_with_no_intent_beside_it(settings, tmp_path):
    fake = _proposed(tmp_path)
    with fake.of(THE_PR).editing(KEY) as editable:
        editable.reply("what about this?")

    _manager_over(settings, fake, worktree=tmp_path).run()

    assert [comment.body for comment in fake.github.thread(KEY).comments[1:]] == [
        "what about this?"]


def test_the_drain_knows_a_claude_run_is_live(settings, tmp_path):
    fake = _proposed(tmp_path)
    fake.agent_runs.script(Outcome(finishes=False))

    board = FakeBoardApi()
    _manager_over(settings, fake, _carry_on(board), lambda: _approved(fake), worktree=tmp_path,
                  board=board).run()

    assert _standing(fake) is ConversationState.READY


def test_the_drain_runs_with_claude_disabled_when_the_config_says_so(tmp_path):
    settings = fake_settings(tmp_path, agents_enabled=False)
    github = FakeGitHub()
    working_copies = FakeWorkingCopies(github)
    repo_at(working_copies, tmp_path, pr=THE_PR)
    manager = run_manager(settings, is_author=True, worktree=tmp_path, github=github,
                          working_copies=working_copies)
    on_github(github, KEY, said(1, "rename this"), pr=THE_PR)
    hear(conversation_managers_over(fake_settings(tmp_path, agents_enabled=True),
                                    github=github, working_copies=working_copies).of(THE_PR))
    threads = manager.conversation_managers.of(THE_PR)

    with threads.editing(KEY) as editable:
        asked = editable.rework(note="again")

    assert isinstance(asked, Denied)
    assert asked.code == ErrorCode.AGENTS_DISABLED


def test_a_manager_on_hold_leaves_the_decisions_until_it_is_off_hold(settings, tmp_path):
    fake = _proposed(tmp_path)
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)
    left_while_on_hold = []

    def release():
        left_while_on_hold.append(_standing(fake))
        disk_holds(settings.data_dir).set_on_hold(THE_PR, False)

    _approved(fake)
    _manager_over(settings, fake, release, worktree=tmp_path).run()

    assert left_while_on_hold == [ConversationState.READY]
    assert _standing(fake) is ConversationState.DONE


def test_the_decisions_wait_while_frozen_on_the_wrong_branch(settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    fake = _proposed(tmp_path)
    fake.working_copies.check_out(tmp_path, "other-branch")
    _approved(fake)

    _manager_over(settings, fake, worktree=tmp_path).run()

    assert _standing(fake) is ConversationState.READY
