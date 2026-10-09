import ast
import dataclasses
import enum
import functools
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import github_orchestrator

pytestmark = pytest.mark.xdist_group("layering")

SOURCE = Path(github_orchestrator.__file__).parent
REPO_ROOT = SOURCE.parents[1]
DOMAIN = "github_orchestrator.conversation._domain"
APPLICATION = "github_orchestrator.conversation._application"
ADAPTERS = "github_orchestrator.conversation._adapters"
BOARD_API = "github_orchestrator.board_api"
PORTS = SOURCE / "conversation" / "_application" / "ports.py"
DOCUMENT = "github_orchestrator.conversation._adapters.conversation_document"
DOCUMENT_CALLERS = frozenset({
    "github_orchestrator.conversation._adapters.conversations",
})


def _modules(package):
    root = SOURCE.joinpath(*package.split(".")[1:])
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(SOURCE).with_suffix("").parts
        is_package = parts[-1] == "__init__"
        if is_package:
            parts = parts[:-1]
        yield ".".join(("github_orchestrator", *parts)), path, is_package


def _every_module():
    for base, prefix in ((REPO_ROOT / "src", ()), (REPO_ROOT / "tests", ("tests",))):
        for path in sorted(base.rglob("*.py")):
            parts = path.relative_to(base).with_suffix("").parts
            is_package = parts[-1] == "__init__"
            if is_package:
                parts = parts[:-1]
            yield ".".join((*prefix, *parts)), path, is_package


@functools.cache
def _imported(name, path, is_package):
    return tuple(_walk_imports(name, path, is_package))


def _walk_imports(name, path, is_package):
    own_package = name if is_package else name.rsplit(".", 1)[0]
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = own_package
                for _ in range(node.level - 1):
                    base = base.rsplit(".", 1)[0]
                package = base if node.module is None else f"{base}.{node.module}"
            else:
                package = node.module
            yield package
            for alias in node.names:
                yield f"{package}.{alias.name}"


def _stdlib(module):
    return module.split(".")[0] in sys.stdlib_module_names


def _under(module, package):
    return module == package or module.startswith(f"{package}.")


KERNEL = "github_orchestrator.domain"
KERNEL_ENTRIES = frozenset({"HubState", "LocalClock", "Location", "Mention", "Monotonic", "Pr", "Repo",
                            "Sha", "Side", "Sleep", "UtcClock"})


def _shared(module):
    return _stdlib(module) or _under(module, KERNEL)


def test_the_kernel_holds_only_the_entries_admitted_to_it():
    entries = set(importlib.import_module(KERNEL).__all__)
    assert entries == KERNEL_ENTRIES, (
        f"{KERNEL} holds {sorted(entries - KERNEL_ENTRIES)} and no longer "
        f"{sorted(KERNEL_ENTRIES - entries)}; each entry of the shared kernel is a "
        f"decision, so admit it here by name"
    )


def test_the_kernel_imports_nothing():
    path = SOURCE / "domain.py"
    for imported in _imported(KERNEL, path, False):
        assert _stdlib(imported), (
            f"{KERNEL} imports {imported}; the kernel is what every module may "
            f"import, so it imports nothing of theirs"
        )


@pytest.mark.parametrize("entry", sorted(KERNEL_ENTRIES))
def test_a_kernel_entry_is_an_immutable_value(entry):
    value = getattr(importlib.import_module(KERNEL), entry)
    frozen = getattr(value, "__dataclass_params__", None)
    assert issubclass(value, enum.Enum) or (frozen is not None and frozen.frozen), (
        f"{KERNEL}.{entry} is neither an enum nor a frozen dataclass; the kernel "
        f"holds immutable values only"
    )


def _modules_naming(entry):
    named = set()
    for name, path, is_package in _modules("github_orchestrator"):
        if name.count(".") and not _under(name, KERNEL):
            if f"{KERNEL}.{entry}" in _imported(name, path, is_package):
                named.add(name.split(".")[1])
    return named


@pytest.mark.parametrize("entry", sorted(KERNEL_ENTRIES))
def test_a_kernel_entry_is_used_by_two_modules_at_least(entry):
    named = _modules_naming(entry)
    assert len(named) >= 2, (
        f"{KERNEL}.{entry} is named only by {sorted(named)}; the kernel holds values "
        f"several modules share, and a value one module uses belongs in that module"
    )


def _port_attributes(path, port: str):
    for node in ast.walk(ast.parse(path.read_text())):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == port):
            yield node.attr


def _records_protocol_names():
    for node in ast.parse(PORTS.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == "Records":
            return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    return set()


def test_an_adapter_reaches_the_records_port_only_where_the_protocol_names_it():
    named = _records_protocol_names()
    assert "load" in named, "the walk found no Records protocol in the ports module"
    for name, path, _ in [*_modules(ADAPTERS), *_modules(BOARD_API)]:
        for attribute in _port_attributes(path, "records"):
            assert attribute in named, (
                f"{name} calls records.{attribute}, which the Records protocol "
                f"does not name; the port has to say everything its callers need"
            )


def test_the_records_document_is_encoded_and_decoded_by_two_modules_only():
    walked = 0
    for name, path, is_package in _every_module():
        walked += 1
        if name in DOCUMENT_CALLERS:
            continue
        for imported in _imported(name, path, is_package):
            assert not _under(imported, DOCUMENT), (
                f"{name} imports {imported}; the document is the shape the "
                f"records adapter writes to disk, and its codec has two "
                f"callers, {', '.join(sorted(DOCUMENT_CALLERS))}"
            )
    assert walked > len(list(_modules(ADAPTERS))), (
        "this walks every module under src/ and tests/, so a walk no wider "
        "than the adapters means it stopped finding them"
    )


def test_the_domain_imports_nothing_but_the_standard_library_and_the_kernel():
    for name, path, is_package in _modules(DOMAIN):
        importlib.import_module(name)
        for imported in _imported(name, path, is_package):
            assert _shared(imported) or _under(imported, DOMAIN), (
                f"{name} imports {imported}; the domain is testable without "
                f"git, GitHub or the filesystem only while it imports "
                f"nothing but the standard library and the shared kernel"
            )


def _a_working_copies_export(imported):
    package = "github_orchestrator.working_copies"
    exports = importlib.import_module(package).__all__
    return imported == package or (imported.startswith(f"{package}.")
                                   and imported[len(package) + 1:] in exports)


def test_the_application_imports_the_domain_its_ports_and_the_working_copies_package():
    for name, path, is_package in _modules(APPLICATION):
        for imported in _imported(name, path, is_package):
            assert (_shared(imported) or _under(imported, DOMAIN)
                    or _under(imported, APPLICATION)
                    or _a_working_copies_export(imported)), (
                f"{name} imports {imported}; the application layer reaches the "
                f"outside world through the ports it defines itself, and git through "
                f"the working copies' own interface, so it imports no adapter and no "
                f"settings"
            )


ROOT = "github_orchestrator"
LIBRARIES = "libraries"
WIRING = f"{ROOT}.wiring"


@dataclasses.dataclass(frozen=True)
class Package:
    pinned: frozenset[str]
    may_import: tuple[str, ...] | None = None
    role: str = ""
    imported_by: tuple[str, ...] | None = None
    entries: frozenset[str] = frozenset({"fake"})
    builds_the_container: frozenset[str] = frozenset()
    wiring_skips: frozenset[str] = frozenset()


PACKAGES = {
    "agent_runs": Package(
        pinned=frozenset({"Agent", "FixComment", "History", "LastRun", "PointedAt", "PrWork",
                          "Run", "Summaries", "ThreadFix", "ThreadWork"}),
        may_import=("desktop", "pr_processes"),
        role="agent runs hear about review threads and the PR manager only through the requests their callers fill in",
    ),
    "board_api": Package(
        pinned=frozenset({"BoardApi", "Hub", "Dashboard", "ManagerPanel"}),
        may_import=("conversation", "working_copies", "terminal_sessions", ROOT, LIBRARIES),
        role="the board serves one PR's review threads and its terminal sessions, and reaches the rest of the program only through them",
        imported_by=("wiring", "pr_manager", "watcher", "preview"),
        entries=frozenset({"interface", "fake"}),
    ),
    "change_detection": Package(
        pinned=frozenset({
            "BecameMergeable", "BecameUnmergeable", "ChangeDetection", "CiFailed",
            "CiStatus", "CiSucceeded", "Facts", "HeadChanged", "Poll",
            "PrClosed", "PrEvent", "PushedSinceReview", "ReviewDecisionChanged",
            "ReviewRequested", "ReviewerStatus", "SinceReview",
        }),
        may_import=("github",),
        role="change detection is handed what GitHub says and hands back events, and knows nothing of the watcher, the windows or the review threads that read its snapshots",
    ),
    "cli": Package(
        pinned=frozenset({"Cli"}),
        may_import=("settings", "github", "pr_event_queue", "working_copies", "pr_processes",
                    "conversation", "change_detection", "watcher", "agent_runs", "desktop"),
        role="the CLI reads and changes the other modules only through their interfaces, and only its entry points build the container",
        imported_by=("wiring",),
        entries=frozenset({"__main__"}),
        builds_the_container=frozenset({"__main__"}),
    ),
    "conversation": Package(
        pinned=frozenset({
            "Classification", "ConfidenceLevel", "Conversation", "ConversationManager",
            "ConversationState", "Denied", "EditableConversation", "ErrorCode",
            "OperationKind", "OperationState", "ReasonCode",
            "ReviewState", "ConversationManagerFactory", "ThreadActivity", "Verdict",
        }),
        may_import=("github", "notifications", "working_copies", "agent_runs", "thread_records",
                    "change_detection", ROOT),
        role="review threads reach GitHub, git, agents and records through those modules and know nothing of the board, the CLI or the PR manager that call them",
        wiring_skips=frozenset({"fake"}),
    ),
    "desktop": Package(
        pinned=frozenset({"Badge", "Desktop"}),
        may_import=(),
        role="the desktop answers in its own types and the modules that use it adapt them, never the reverse",
    ),
    "github": Package(
        pinned=frozenset({
            "Access", "CommentKind", "PullRequestState", "PullRequests", "ReviewState",
            "Reviews", "Thread", "ThreadComment", "Threads", "Verdict",
        }),
        may_import=(),
        role="GitHub answers in its own types and the modules that use it adapt them, never the reverse",
    ),
    "notifications": Package(
        pinned=frozenset({
            "BoardPages", "Courier", "FixProgress", "Polling", "PrStatus", "Runs", "Settling",
            "Standing", "ThreadNews", "Worktrees",
        }),
        may_import=("desktop", "agent_runs", "change_detection"),
        role="every module states its facts to the notifications, which reach only the desktop they deliver to, agent runs' summaries and the change detection events they are told of",
    ),
    "pr_event_queue": Package(
        pinned=frozenset({
            "Intake", "Launching", "Queues", "Response", "Taken", "Worklist",
        }),
        may_import=("notifications", "desktop", "change_detection", "conversation"),
        role="the PrEventQueue holds change detection's events and review threads' thread activity, decides the response and the PR manager carries it out, so it never reaches agent runs or the manager",
    ),
    "pr_manager": Package(
        pinned=frozenset({"Front", "ManagedPr", "PrManager"}),
        may_import=("settings", "desktop", "notifications", "pr_event_queue", "working_copies",
                    "pr_processes", "agent_runs", "conversation", "change_detection", "board_api",
                    "github"),
        role="the PR manager takes its work from the event_queue, carries it out through agent runs, review threads and the desktop, writes to the PR itself through GitHub, starts the board only through the board API, and only its entry point builds the container",
        imported_by=("wiring",),
        entries=frozenset({"__main__"}),
        builds_the_container=frozenset({"__main__"}),
    ),
    "preview": Package(
        pinned=frozenset(),
        imported_by=(),
        entries=frozenset({"__main__"}),
    ),
    "pr_processes": Package(
        pinned=frozenset({"AgentChanges", "ManagerPane", "PrProcesses"}),
        may_import=("terminal_sessions",),
        role="PR windows run each PR's agent manager in the background and open its terminal sessions, and are handed the worktree by their callers",
    ),
    "settings": Package(
        pinned=frozenset({"Boards", "ConfigFile", "Dismissals", "Logs", "Holds", "Process"}),
        wiring_skips=frozenset({"_paths"}),
    ),
    "terminal_sessions": Package(
        pinned=frozenset({"TerminalSessions", "Terminals"}),
        may_import=(),
        role="a terminal session is a command on a pty in a worktree it is handed, and knows nothing of who starts or serves it",
    ),
    "thread_records": Package(
        pinned=frozenset({"PrRecords", "ThreadRecords", "UnreadableThread"}),
        may_import=(),
        role="thread records keep documents, and review threads turn them into conversations, never the reverse",
        imported_by=("conversation", "wiring", "watcher"),
    ),
    "watcher": Package(
        pinned=frozenset({"Health", "Releases", "Watcher", "WatcherHealth"}),
        may_import=("settings", "github", "desktop", "notifications", "pr_event_queue", "pr_processes",
                    "conversation", "change_detection", "working_copies", "thread_records",
                    "board_api"),
        role="the watcher polls through GitHub, change detection and review threads, hands events to the event_queue and windows to PR windows, serves the board api's hub, and only its entry point builds the container",
        imported_by=("wiring", "cli._cli", "cli._status", "cli._restart", "cli._restart_all",
                     "cli._doctor", "cli._update"),
        entries=frozenset({"__main__"}),
        builds_the_container=frozenset({"__main__"}),
    ),
    "working_copies": Package(
        pinned=frozenset({
            "FileDiff", "PrCheckout", "ThreadWorkspace", "WorkingCopies", "WrongBranch",
        }),
        may_import=("github", "desktop", "notifications"),
        role="git working copies answer in their own types and review adapts them, never the reverse",
    ),
}
WALLED = sorted(short for short, package in PACKAGES.items() if package.may_import is not None)
GUARDED = sorted(short for short, package in PACKAGES.items() if package.imported_by is not None)


def _full(short):
    return f"{ROOT}.{short}"


def _submodule_stems(short):
    return frozenset(
        path.stem if path.is_file() else path.name
        for path in SOURCE.joinpath(short).iterdir()
        if path.name != "__init__.py" and (path.suffix == ".py" or (path / "__init__.py").exists())
    )


def _implementation(short):
    return frozenset(f"{_full(short)}.{stem}" for stem in _submodule_stems(short)
                     if stem.startswith("_") and stem != "__main__")


def _submodules(short, imported_names):
    package, stems = _full(short), _submodule_stems(short)
    for imported in imported_names:
        if not imported.startswith(f"{package}."):
            continue
        submodule = imported[len(package) + 1:].split(".")[0]
        if submodule in stems:
            yield f"{package}.{submodule}"


def _outside(short):
    for name, path, is_package in _every_module():
        if not _under(name, _full(short)):
            yield name, set(_submodules(short, _imported(name, path, is_package)))


def _reaches(imported, allowed):
    if allowed == LIBRARIES:
        return not _under(imported, ROOT)
    if allowed == ROOT:
        return imported == ROOT
    return _under(imported, _full(allowed))


@pytest.mark.parametrize(("short", "private", "public"), [
    ("pr_event_queue", "_disk", "PrEventQueue"),
    ("agent_runs", "_runs", "History"),
], ids=["pr_event_queue", "agent_runs"])
def test_a_submodule_imported_off_the_package_is_seen(tmp_path, short, private, public):
    borrower = tmp_path / "borrower.py"
    borrower.write_text(f"from {_full(short)} import {private}, {public}\n")

    seen = set(_submodules(short, _imported("borrower", borrower, False)))

    assert seen == {f"{_full(short)}.{private}"}


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_only_wiring_builds_the_real_package(short):
    implementation = _implementation(short)
    for name, submodules in _outside(short):
        if name == WIRING:
            continue
        assert not submodules & implementation, (
            f"{name} imports {sorted(submodules & implementation)}; the implementation of "
            f"{_full(short)} is built by {WIRING} and handed to everyone else"
        )


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_outside_code_imports_a_package_only_through_its_package(short):
    package = PACKAGES[short]
    allowed = {f"{_full(short)}.{entry}" for entry in package.entries}
    skipped = {f"{_full(short)}.{skip}" for skip in package.wiring_skips}
    wiring_allowed = (allowed | _implementation(short)) - skipped
    for name, submodules in _outside(short):
        own = wiring_allowed if name == WIRING else allowed
        assert submodules <= own, (
            f"{name} imports {sorted(submodules - own)}; outside {_full(short)}, import "
            f"its package or one of {sorted(own)}"
        )


@pytest.mark.parametrize("short", WALLED)
def test_a_package_imports_only_what_it_may(short):
    package = PACKAGES[short]
    walked = 0
    for name, path, is_package in _modules(_full(short)):
        walked += 1
        allowed = (short, *package.may_import)
        if name in {f"{_full(short)}.{entry}" for entry in package.builds_the_container}:
            allowed = (*allowed, "wiring")
        for imported in _imported(name, path, is_package):
            assert _shared(imported) or any(_reaches(imported, a) for a in allowed), (
                f"{name} imports {imported}; {package.role}"
            )
    assert walked > 3, f"the walk found no {short} package to check"


@pytest.mark.parametrize("short", GUARDED)
def test_only_the_named_users_import_a_package(short):
    users = (short, *PACKAGES[short].imported_by)
    walked = 0
    for name, path, is_package in _modules(ROOT):
        if any(_under(name, _full(user)) for user in users):
            continue
        walked += 1
        for imported in _imported(name, path, is_package):
            assert not _under(imported, _full(short)), (
                f"{name} imports {imported}; only {', '.join(users[1:]) or 'the tests'} "
                f"import {_full(short)}"
            )
    assert walked > 10, "the walk found no production modules to check"


CONVERSATION = f"{ROOT}.conversation"
WORKING_COPIES = f"{ROOT}.working_copies"
NOTIFICATIONS = f"{ROOT}.notifications"
DESKTOP = f"{ROOT}.desktop"
PR_EVENT_QUEUE = f"{ROOT}.pr_event_queue"
PR_PROCESSES = f"{ROOT}.pr_processes"
TERMINAL_SESSIONS = f"{ROOT}.terminal_sessions"
THREAD_RECORDS = f"{ROOT}.thread_records"
CHANGE_DETECTION = f"{ROOT}.change_detection"
WATCHER = f"{ROOT}.watcher"
PR_MANAGER = f"{ROOT}.pr_manager"
PREVIEW = f"{ROOT}.preview"


def test_only_the_notifications_pass_the_desktop_a_badge():
    walked = 0
    for name, path, _ in _modules("github_orchestrator"):
        if _under(name, NOTIFICATIONS) or _under(name, DESKTOP):
            continue
        walked += 1
        tree = ast.parse(path.read_text())
        named = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                 for alias in node.names}
        assert "Badge" not in named, (
            f"{name} imports Badge; callers state what happened and the notifications "
            f"pick the badge"
        )
    assert walked > 50, "the walk found no modules to check"


def test_the_event_queue_names_only_the_thread_activity_it_holds_from_conversation():
    walked = 0
    for name, path, _ in _modules(PR_EVENT_QUEUE):
        walked += 1
        named = set(_names_from_conversation(path))
        assert named <= {"ThreadActivity"}, (
            f"{name} names {sorted(named - {'ThreadActivity'})} from {CONVERSATION}; the "
            f"queue holds the thread activity review threads found and hands it back whole"
        )
    assert walked > 3, "the walk found no event_queue module to check"


PR_EVENT_QUEUE_ROLES = {
    "Intake": frozenset({"add", "add_thread_activity"}),
    "Worklist": frozenset({"next", "waiting", "settling", "recover", "drop_in_flight",
                           "is_torn_down", "forget"}),
    "Queues": frozenset({"queues", "failed_since", "archive_other_repos"}),
}


@pytest.mark.parametrize("role", sorted(PR_EVENT_QUEUE_ROLES))
def test_the_event_queue_says_what_waits_and_never_hands_out_the_events_it_holds(role):
    interface = getattr(importlib.import_module(PR_EVENT_QUEUE), role)
    members = {name for name in vars(interface) if not name.startswith("_")}
    expected = PR_EVENT_QUEUE_ROLES[role]
    assert members == expected, (
        f"{role} gained {sorted(members - expected)} and lost {sorted(expected - members)}; "
        f"callers take events in, work through a PR's events or list the queues, and the "
        f"stored events stay inside the event queue"
    )


WORKING_COPIES_MEMBERS = frozenset({
    "forget_pr", "pr_worktree", "fetch_pr_branch", "report_branch",
    "verdict", "handed_off", "request_release", "wrong_branch", "commits_since",
    "checkout",
})
PR_CHECKOUT_MEMBERS = frozenset({
    "workspace", "is_clean", "push", "unpick", "fetch", "origin_head", "local_head", "commit_message",
    "diff_files", "pr_diff", "has_commit", "blob", "no_worktree",
})
THREAD_WORKSPACE_MEMBERS = frozenset({
    "path", "branch", "base_sha", "ensure", "pick", "head_sha", "descends", "progress", "drop",
})


def _members(protocol):
    return {name for name in vars(protocol) if not name.startswith("_")}


def test_working_copies_offer_worktrees_branch_trouble_and_a_checkout_per_pr():
    package = importlib.import_module(WORKING_COPIES)
    assert _members(package.WorkingCopies) == WORKING_COPIES_MEMBERS
    assert _members(package.PrCheckout) == PR_CHECKOUT_MEMBERS
    assert _members(package.ThreadWorkspace) == THREAD_WORKSPACE_MEMBERS, (
        "a thread's git work goes through the handles a PR checkout hands out, and "
        "none of them takes a worktree path or a stored workspace string"
    )


PR_PROCESSES_MEMBERS = frozenset({
    "open", "revive", "manager", "stop_managers", "manager_path", "detach", "close", "split",
    "close_other_repos",
})


def test_pr_processes_offer_only_manager_and_session_operations():
    interface = importlib.import_module(PR_PROCESSES).PrProcesses
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == PR_PROCESSES_MEMBERS, (
        f"PrProcesses gained {sorted(members - PR_PROCESSES_MEMBERS)} and lost "
        f"{sorted(PR_PROCESSES_MEMBERS - members)}; deciding what to open, revive, detach or "
        f"reap belongs to the watcher, and branches and worktrees to working copies"
    )


TERMINAL_SESSIONS_MEMBERS = frozenset({"start", "listed", "attach", "hang_up"})
TERMINALS_MEMBERS = frozenset({"of", "everywhere"})


def test_terminal_sessions_start_list_attach_and_hang_up_and_nothing_more():
    interface = importlib.import_module(TERMINAL_SESSIONS).TerminalSessions
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == TERMINAL_SESSIONS_MEMBERS, (
        f"TerminalSessions gained {sorted(members - TERMINAL_SESSIONS_MEMBERS)} and lost "
        f"{sorted(TERMINAL_SESSIONS_MEMBERS - members)}; a session ends when its command "
        f"does or when its pull request's sessions are hung up together, never one by one"
    )


def test_terminals_only_hand_out_a_pull_requests_sessions():
    interface = importlib.import_module(TERMINAL_SESSIONS).Terminals
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == TERMINALS_MEMBERS, (
        f"Terminals gained {sorted(members - TERMINALS_MEMBERS)} and lost "
        f"{sorted(TERMINALS_MEMBERS - members)}; everything done to a session is done "
        f"through its pull request's TerminalSessions"
    )


THREAD_RECORDS_FOR_EVERYONE = frozenset({"ThreadRecords"})


def _thread_records_names(imported_names):
    for imported in imported_names:
        if imported.startswith(f"{THREAD_RECORDS}."):
            yield imported[len(THREAD_RECORDS) + 1:]


def test_only_conversation_read_what_a_thread_record_holds():
    walked = 0
    for name, path, is_package in _modules("github_orchestrator"):
        if any(_under(name, owner) for owner in (THREAD_RECORDS, CONVERSATION, WIRING)):
            continue
        walked += 1
        names = set(_thread_records_names(_imported(name, path, is_package)))
        assert names <= THREAD_RECORDS_FOR_EVERYONE, (
            f"{name} imports {sorted(names - THREAD_RECORDS_FOR_EVERYONE)} from "
            f"{THREAD_RECORDS}; documents, pending decisions and reviews are the review threads' "
            f"to read, everyone else hands the records on or forgets a PR's"
        )
    assert walked > 10, "the walk found no production modules to check"


def _private_conversation_names(imported_names):
    for imported in imported_names:
        if imported == CONVERSATION or not _under(imported, CONVERSATION):
            continue
        if any(part.startswith("_") for part in imported[len(CONVERSATION) + 1:].split(".")):
            yield imported


def test_no_test_imports_a_private_name_of_conversation():
    walked = 0
    for name, path, is_package in _every_module():
        if not _under(name, "tests"):
            continue
        walked += 1
        private = sorted(set(_private_conversation_names(_imported(name, path, is_package))))
        assert not private, (
            f"{name} imports {private}; tests reach review threads through "
            f"ConversationManagerFactory.of(pr) and its fake, never its private modules or names"
        )
    assert walked > 100, "the walk found no tests to check"


CONVERSATION_MEMBERS = frozenset({"of"})
ROLE_MEMBERS = {
    "ConversationManager": frozenset({
        "editing", "get", "all", "open_draft", "open_thread", "send_review", "reviews",
        "facts", "activity", "comment_url", "too_long", "poll", "absorb", "tick", "counts",
        "recheck"}),
    "EditableConversation": frozenset({
        "approve", "rework", "start_session", "retry", "fix", "stop", "resolve", "reject", "place",
        "unpark", "reply", "mark_seen", "edit", "enrol", "withdraw", "discard", "post_now",
        "plan", "step_done", "ready", "move_base", "not_a_fix", "fail"}),
}


def test_conversation_offer_only_a_handle_per_pr():
    interface = importlib.import_module(CONVERSATION).ConversationManagerFactory
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == CONVERSATION_MEMBERS, (
        f"ConversationManagerFactory gained {sorted(members - CONVERSATION_MEMBERS)} and lost "
        f"{sorted(CONVERSATION_MEMBERS - members)}; everything else is the PR's "
        f"conversation manager's or one conversation's"
    )


@pytest.mark.parametrize("role", sorted(ROLE_MEMBERS))
def test_the_manager_and_a_conversation_offer_only_their_own_methods(role):
    interface = getattr(importlib.import_module(CONVERSATION), role)
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == ROLE_MEMBERS[role], (
        f"{role} gained {sorted(members - ROLE_MEMBERS[role])} and lost "
        f"{sorted(ROLE_MEMBERS[role] - members)}; a command on one conversation is the "
        f"conversation's, and what arrives without one in hand is the manager's"
    )


CHANGE_DETECTION_MEMBERS = frozenset({
    "advance", "ended", "facts", "tracked", "stored", "closing", "close", "forget",
    "archive_other_repos",
})


def test_change_detection_hands_out_facts_never_the_snapshot_it_stores():
    interface = importlib.import_module(CHANGE_DETECTION).ChangeDetection
    members = {name for name in vars(interface) if not name.startswith("_")}
    assert members == CHANGE_DETECTION_MEMBERS, (
        f"ChangeDetection gained {sorted(members - CHANGE_DETECTION_MEMBERS)} and lost "
        f"{sorted(CHANGE_DETECTION_MEMBERS - members)}; the snapshot's format is change "
        f"detection's own, so callers read typed facts and never the stored dict"
    )


WATCHER_HEALTH_READ = frozenset({WATCHER, f"{WATCHER}.WatcherHealth", f"{WATCHER}.Health",
                                 f"{WATCHER}.Releases"})


def test_the_cli_imports_only_the_watchers_health_read():
    walked = 0
    for name, path, is_package in _every_module():
        if not _under(name, "github_orchestrator.cli"):
            continue
        walked += 1
        for imported in _imported(name, path, is_package):
            assert not _under(imported, WATCHER) or imported in WATCHER_HEALTH_READ, (
                f"{name} imports {imported}; the CLI asks the watcher two things, how it is "
                f"doing, through WatcherHealth, and which release is newest, through Releases, "
                f"words the answers itself, and reads none of its files"
            )
    assert walked > 3, "the walk found no cli package to check"


@pytest.mark.no_replay
def test_the_cli_starts_without_loading_the_board_s_web_server():
    loaded = subprocess.run(
        [sys.executable, "-c",
         "import sys, github_orchestrator.cli.__main__\n"
         "print(' '.join(m for m in ('fastapi', 'uvicorn', 'starlette.applications') if m in sys.modules))"],
        capture_output=True, text=True, check=True).stdout.split()
    assert loaded == [], (
        f"importing the CLI loads {loaded}; only the board and the hub serve pages, so the "
        f"wiring imports their server where it builds them, and every CLI command starts "
        f"without paying for it"
    )


def test_the_watcher_names_only_the_conversation_interface():
    walked = 0
    for name, path, _ in _modules(WATCHER):
        walked += 1
        named = set(_names_from_conversation(path))
        assert named <= {"ConversationManagerFactory", "ThreadActivity"}, (
            f"{name} names {sorted(named - {'ConversationManagerFactory', 'ThreadActivity'})} from "
            f"{CONVERSATION}; the "
            f"poll answers the comments that arrived and the thread activity whole, so the "
            f"watcher reads no record and applies no rule of theirs"
        )
    assert walked > 3, "the walk found no watcher module to check"


PR_MANAGER_NAMES_FROM_CONVERSATION = frozenset({
    "ConversationManagerFactory", "ConversationManager", "ThreadActivity",
})


def test_the_pr_manager_names_only_the_handle_the_roles_and_the_thread_activity():
    walked = 0
    for name, path, _ in _modules(PR_MANAGER):
        walked += 1
        named = set(_names_from_conversation(path))
        assert named <= PR_MANAGER_NAMES_FROM_CONVERSATION, (
            f"{name} names {sorted(named - PR_MANAGER_NAMES_FROM_CONVERSATION)} from "
            f"{CONVERSATION}; the manager ticks a PR's threads and hands them the thread "
            f"activity the watcher found"
        )
    assert walked > 3, "the walk found no pr_manager module to check"


BOARD_API_NAMES_FROM_WORKING_COPIES = frozenset({
    "FileDiff", "PrCheckout", "WorkingCopies",
})


BOARD_API_NAMES_FROM_CONVERSATION = frozenset({
    "Classification", "ConfidenceLevel", "Conversation", "ConversationManager",
    "ConversationState", "Denied", "EditableConversation", "ErrorCode",
    "OperationKind", "OperationState", "ReasonCode", "ReviewState",
    "ConversationManagerFactory", "Verdict",
})

PREVIEW_NAMES_FROM_CONVERSATION = frozenset({
    "Classification", "Conversation", "ConversationManager", "ConversationManagerFactory",
    "ConversationState", "Denied", "EditableConversation",
})


def _names_from_conversation(path):
    parsed = ast.parse(path.read_text())
    aliases = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.ImportFrom) and node.module == CONVERSATION:
            yield from (alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == "github_orchestrator":
            aliases |= {alias.asname or alias.name for alias in node.names
                        if alias.name == "conversation"}
    for node in ast.walk(parsed):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            yield node.attr


def test_the_board_api_names_only_the_conversation_vocabulary_it_serves():
    walked = 0
    for name, path, _ in _modules(BOARD_API):
        walked += 1
        named = set(_names_from_conversation(path))
        assert named <= BOARD_API_NAMES_FROM_CONVERSATION, (
            f"{name} names {sorted(named - BOARD_API_NAMES_FROM_CONVERSATION)} from "
            f"{CONVERSATION}; the board reads threads, asks for verbs and projects "
            f"their states, and names nothing else of theirs"
        )
    assert walked > 3, "the walk found no board_api module to check"


def test_the_board_api_names_only_the_checkout_and_the_diff_values_of_the_working_copies():
    walked = 0
    for name, path, _ in _modules(BOARD_API):
        walked += 1
        named = {alias.name for node in ast.walk(ast.parse(path.read_text()))
                 if isinstance(node, ast.ImportFrom) and node.module == WORKING_COPIES
                 for alias in node.names}
        assert named <= BOARD_API_NAMES_FROM_WORKING_COPIES, (
            f"{name} names {sorted(named - BOARD_API_NAMES_FROM_WORKING_COPIES)} from "
            f"{WORKING_COPIES}; the board reads commits, files and diffs through a "
            f"checkout and runs no git of its own"
        )
    assert walked > 3, "the walk found no board_api module to check"


def test_the_preview_names_only_the_commands_it_seeds_the_board_with():
    named = set(_names_from_conversation(SOURCE / "preview" / "__init__.py"))

    assert named <= PREVIEW_NAMES_FROM_CONVERSATION, (
        f"the preview names {sorted(named - PREVIEW_NAMES_FROM_CONVERSATION)} from "
        f"{CONVERSATION}; it seeds the board through commands a user or the agent "
        f"would give, not by writing records"
    )


def test_the_python_side_serves_only_the_built_board_web_app():
    walked = 0
    for path in sorted(SOURCE.rglob("*.py")):
        walked += 1
        assert "frontend" not in path.read_text().replace('"build_frontend"', ""), (
            f"{path.relative_to(REPO_ROOT)} names the frontend; the board web app's "
            f"sources are its own, and the board API serves only the bundle "
            f"make build_frontend leaves in board_api/static/app"
        )
    assert walked > 50, "the walk found no python sources to check"


WRITTEN = frozenset({"annotation", "call", "isinstance", "match", "base", "attribute"})


def _packages():
    return sorted(path.parent.name for path in SOURCE.glob("*/__init__.py"))


@functools.cache
def _import_nodes(tree):
    return tuple(node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))


def _exported_names(tree, package, name, is_package):
    names, aliases = {}, set()
    short = package.rsplit(".", 1)[1]
    for node in _import_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            source = _resolved(node, name, is_package)
            for alias in node.names:
                if source == package:
                    names[alias.asname or alias.name] = alias.name
                elif source == "github_orchestrator" and alias.name == short:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            aliases |= {alias.asname for alias in node.names
                        if alias.name == package and alias.asname}
    return names, aliases


def _resolved(node, name, is_package):
    if not node.level:
        return node.module
    base = name if is_package else name.rsplit(".", 1)[0]
    for _ in range(node.level - 1):
        base = base.rsplit(".", 1)[0]
    return base if node.module is None else f"{base}.{node.module}"


def _inside_a_function(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
    return False


def _nothing_to_infer_from(value):
    if value is None or (isinstance(value, ast.Constant) and value.value is None):
        return True
    if isinstance(value, ast.Dict):
        return not value.keys
    return isinstance(value, (ast.List, ast.Set, ast.Tuple)) and not value.elts


def _needs_its_annotation(assignment, parents):
    return (not _inside_a_function(assignment, parents)
            or isinstance(assignment.target, ast.Attribute)
            or _nothing_to_infer_from(assignment.value))


def _how_written(node, parents):
    child, parent = node, parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.arg) and parent.annotation is child:
            return "annotation"
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and parent.returns is child:
            return "annotation"
        if isinstance(parent, ast.AnnAssign) and parent.annotation is child:
            return "annotation" if _needs_its_annotation(parent, parents) else "local annotation"
        if isinstance(parent, ast.ClassDef) and child in parent.bases:
            return "base"
        if isinstance(parent, ast.MatchClass) and parent.cls is child:
            return "match"
        if isinstance(parent, ast.ExceptHandler) and parent.type is child:
            return "isinstance"
        if isinstance(parent, ast.Call):
            if parent.func is child:
                return "call" if child is node else "value"
            is_check = isinstance(parent.func, ast.Name) and parent.func.id in {"isinstance", "issubclass"}
            return "isinstance" if is_check and parent.args[1:2] == [child] else "value"
        if isinstance(parent, ast.Attribute) and child is node:
            return "attribute"
        if not isinstance(parent, (ast.Subscript, ast.BinOp, ast.Tuple, ast.List)):
            return "value"
        child, parent = parent, parents.get(parent)
    return "value"


def _writes(tree, names, aliases):
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
                and [target.id for target in node.targets if isinstance(target, ast.Name)] == ["__all__"]):
            yield from ((names[item.value], "export") for item in node.value.elts
                        if isinstance(item, ast.Constant) and item.value in names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, ast.Load):
            yield names[node.id], _how_written(node, parents)
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
              and node.value.id in aliases):
            yield node.attr, _how_written(node, parents)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and names:
            how = _how_written(node, parents)
            if how in {"annotation", "local annotation"}:
                yield from ((names[sub.id], how) for sub in _parsed_annotation(node.value)
                            if isinstance(sub, ast.Name) and sub.id in names)


def _parsed_annotation(text):
    try:
        return list(ast.walk(ast.parse(text, mode="eval")))
    except SyntaxError:
        return []


@functools.cache
def _parsed(path):
    return ast.parse(path.read_text())


@functools.cache
def _outside_users(package):
    return tuple(_each_outside_user(package))


def _each_outside_user(package):
    for name, path, is_package in _modules("github_orchestrator"):
        if _under(name, package) or name.rsplit(".", 1)[-1] == "fake":
            continue
        tree = _parsed(path)
        names, aliases = _exported_names(tree, package, name, is_package)
        written = {}
        if names or aliases:
            for exported, how in _writes(tree, names, aliases):
                written.setdefault(exported, set()).add(how)
        yield name, set(names.values()), written


def _outside_writes(package):
    written = {}
    for _, _, in_module in _outside_users(package):
        for exported, hows in in_module.items():
            written.setdefault(exported, set()).update(hows)
    return written


def _is_written(package, exported, hows):
    value = getattr(importlib.import_module(package), exported, None)
    named_type = "value" in hows and isinstance(value, type)
    return bool(hows & WRITTEN) or named_type


def test_every_package_has_its_export_list_pinned():
    assert _packages() == sorted(PACKAGES)


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_a_package_exports_only_its_pinned_names(short):
    package = f"github_orchestrator.{short}"
    exported = set(importlib.import_module(package).__all__)
    pinned = PACKAGES[short].pinned
    assert exported == pinned, (
        f"{package} exports {sorted(exported - pinned)} and no longer "
        f"{sorted(pinned - exported)}; each export is a decision, so pin it here by name"
    )


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_a_package_exports_no_fake(short):
    package = importlib.import_module(f"github_orchestrator.{short}")
    fakes = {name for name in package.__all__
             if name.lower().startswith("fake")
             or getattr(getattr(package, name), "__module__", "").endswith(".fake")}
    assert not fakes, (
        f"{package.__name__} exports {sorted(fakes)}; a fake lives only in "
        f"{package.__name__}.fake, where tests import it"
    )


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_every_export_is_written_by_a_module_outside_its_package(short):
    package = f"github_orchestrator.{short}"
    written = _outside_writes(package)
    unwritten = sorted(name for name in PACKAGES[short].pinned
                       if not _is_written(package, name, written.get(name, set())))
    assert not unwritten, (
        f"no module outside {package} writes {unwritten} in an annotation, a call, an "
        f"isinstance or a match; a value callers only read fields from stays out of "
        f"__all__, and tests and fakes are not outside users"
    )


@pytest.mark.parametrize("short", sorted(PACKAGES))
def test_no_module_imports_an_export_it_only_reads_fields_from(short):
    package = f"github_orchestrator.{short}"
    for name, imported, written in _outside_users(package):
        passed_on = {exported for exported, hows in written.items() if "export" in hows}
        read_only = sorted(exported for exported in imported - passed_on
                           if not _is_written(package, exported, written.get(exported, set())))
        assert not read_only, (
            f"{name} imports {read_only} from {package} and never writes them in a "
            f"signature, a call, an isinstance or a match; read the fields off what the "
            f"call returns and leave the name to its package"
        )
