import importlib
import inspect
import typing
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


def _returned_classes(member):
    function = member.fget if isinstance(member, property) else member
    try:
        hint = typing.get_type_hints(function).get("return")
    except NameError:
        return []
    pending, found = [hint], []
    while pending:
        current = pending.pop()
        if isinstance(current, type):
            found.append(current)
        pending.extend(typing.get_args(current))
    return found


def handed_out(cls, package):
    roles = {}
    for name, member in inspect.getmembers(cls):
        if name.startswith("_") or not (inspect.isfunction(member) or isinstance(member, property)):
            continue
        for role in _returned_classes(member):
            module = role.__module__
            if role is not cls and (module == package or module.startswith(f"{package}.")):
                roles[role.__name__] = method_count(role)
    return roles


def exported(short):
    package = importlib.import_module(f"github_orchestrator.{short}")
    return {name: method_count(value) if isinstance(value, type) else None
            for name in package.__all__
            for value in [getattr(package, name)]}


def handed_out_roles(short):
    package = importlib.import_module(f"github_orchestrator.{short}")
    return {name: {role: methods for role, methods in handed_out(value, package.__name__).items()
                   if role not in package.__all__}
            for name in package.__all__
            for value in [getattr(package, name)]
            if isinstance(value, type)}


def report_lines(packages, roles=None):
    lines = []
    for short, names in sorted(packages.items()):
        allowed = budget(short)
        over = "  OVER" if len(names) > allowed else ""
        lines.append(f"{short}  {len(names)} exports / budget {allowed}{over}")
        for name, methods in sorted(names.items()):
            if methods:
                flag = "  OVER" if methods > METHOD_CAP else ""
                lines.append(f"  {name}  {methods} methods / cap {METHOD_CAP}{flag}")
            for role, role_methods in sorted((roles or {}).get(short, {}).get(name, {}).items()):
                flag = "  OVER" if role_methods > METHOD_CAP else ""
                lines.append(f"    {role}  {role_methods} methods / cap {METHOD_CAP}{flag}")
    return lines


def main():
    shorts = sorted(path.parent.name for path in SOURCE.glob("*/__init__.py"))
    print("\n".join(report_lines({short: exported(short) for short in shorts},
                                  {short: handed_out_roles(short) for short in shorts})))


if __name__ == "__main__":
    main()
