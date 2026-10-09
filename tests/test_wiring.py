import ast
from dataclasses import dataclass
from pathlib import Path

from dishka import Provider, Scope, from_context, provide

from github_orchestrator.wiring import Wiring, wire, wires


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
