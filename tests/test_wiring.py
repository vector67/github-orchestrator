import ast
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dishka import Provider, Scope, from_context, provide

from github_orchestrator.board_api.interface import Timers
from github_orchestrator.domain import Repo
from github_orchestrator.settings.fake import HarvestProject
from github_orchestrator.wiring import (
    SUMMARISE,
    FetchedEmojis,
    HarvestWiring,
    Wiring,
    utility_clamp,
    wire,
    wires,
)
from tests.conftest import clocks_of
from tests.conversation.support import at
from tests.harvest.scripted_harvest import ACCOUNT, TOKEN, ScriptedHarvest

SHIPIT = "https://github.githubassets.com/images/icons/emoji/shipit.png?v8"


@dataclass(frozen=True)
class GreetingWiring(Wiring):
    name: str


class Greeting(str):
    pass


@wires(GreetingWiring)
class GreetingProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=GreetingWiring, scope=Scope.APP)

    @provide
    def greeting(self, wiring: GreetingWiring) -> Greeting:
        return Greeting(f"hello {wiring.name}")


def test_containers_of_one_shape_share_one_graph_and_keep_their_own_values():
    first = wire(GreetingWiring("ada"))
    second = wire(GreetingWiring("grace"))

    assert second.registry is first.registry
    assert first.get(Greeting) == "hello ada"
    assert second.get(Greeting) == "hello grace"


def _providers_holding_values(root: Path) -> list[str]:
    holding = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text()
        if "Provider" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.ClassDef)
                    and any(ast.unparse(base).endswith("Provider") for base in node.bases)
                    and any(isinstance(member, ast.FunctionDef) and member.name == "__init__"
                            for member in node.body)):
                holding.append(f"{path.name}:{node.name}")
    return holding


def test_no_provider_holds_values_of_its_own():
    repository = Path(__file__).parent.parent

    assert _providers_holding_values(repository / "src") == []
    assert _providers_holding_values(repository / "tests") == []


def test_closing_one_container_leaves_another_of_its_shape_working():
    first = wire(GreetingWiring("ada"))
    second = wire(GreetingWiring("grace"))

    first.close()

    assert second.get(Greeting) == "hello grace"


def test_the_summary_lane_runs_the_plugin_this_checkout_carries():
    plugin = Path(__file__).resolve().parents[1] / "plugins" / "pr-summary" / "scripts" / "summarise.py"

    assert SUMMARISE.resolve() == plugin


def test_background_work_is_clamped_to_the_utility_class_on_macos_only():
    assert utility_clamp("darwin") == ("taskpolicy", "-c", "utility")
    assert utility_clamp("linux") == ()


def test_the_emojis_are_asked_of_github_as_soon_as_they_are_made():
    asked = threading.Event()

    def listed():
        asked.set()
        return {}

    FetchedEmojis(listed)

    assert asked.wait(5)


def test_the_emojis_are_the_ones_github_listed():
    assert FetchedEmojis(lambda: {"shipit": SHIPIT}).named() == {"shipit": SHIPIT}


def test_a_repo_s_timer_runs_on_its_own_harvest_project_and_task_on_the_local_date():
    harvest = ScriptedHarvest()
    widgets, gadgets = Repo("acme", "widgets"), Repo("acme", "gadgets")
    timers = wire(
        HarvestWiring(ACCOUNT, {widgets: HarvestProject(111, 222)}, lambda: TOKEN, harvest),
        clocks_of(at("2026-10-21T23:30:00Z"), local=lambda: datetime.fromisoformat(
            "2026-10-22T01:30:00+02:00")),
    ).get(Timers)

    timer = timers.of(widgets)
    assert timer is not None
    assert timer.start() is None

    assert harvest.running() == [(111, 222)]
    assert harvest.entries[0].spent_date == "2026-10-22"
    assert timer.running() is True
    assert timers.of(gadgets) is None
