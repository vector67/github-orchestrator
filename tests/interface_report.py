import importlib
import inspect
from pathlib import Path

SOURCE = Path(__file__).parent.parent / "src" / "github_orchestrator"
WIDE = frozenset({"conversation", "agent_runs", "github"})
METHOD_CAP = 10
OWN = ("github_orchestrator", "tests")


def budget(short):
    return 10 if short in WIDE else 5


def method_count(cls):
    names = set()
    for klass in cls.__mro__:
        if not klass.__module__.startswith(OWN):
            continue
        for name, member in vars(klass).items():
            if name.startswith("_"):
                continue
            if inspect.isfunction(member) or isinstance(member, (property, staticmethod, classmethod)):
                names.add(name)
    return len(names)


def exported(short):
    package = importlib.import_module(f"github_orchestrator.{short}")
    return {name: method_count(value) if isinstance(value, type) else None
            for name in package.__all__
            for value in [getattr(package, name)]}


def report_lines(packages):
    lines = []
    for short, names in sorted(packages.items()):
        allowed = budget(short)
        over = "  OVER" if len(names) > allowed else ""
        lines.append(f"{short}  {len(names)} exports / budget {allowed}{over}")
        for name, methods in sorted(names.items()):
            if methods:
                flag = "  OVER" if methods > METHOD_CAP else ""
                lines.append(f"  {name}  {methods} methods / cap {METHOD_CAP}{flag}")
    return lines


def main():
    shorts = sorted(path.parent.name for path in SOURCE.glob("*/__init__.py"))
    print("\n".join(report_lines({short: exported(short) for short in shorts})))


if __name__ == "__main__":
    main()
