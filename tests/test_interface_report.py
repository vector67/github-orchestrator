from typing import Protocol

from tests.interface_report import budget, handed_out, method_count, report_lines


class _Role(Protocol):
    def one(self) -> None: ...
    def two(self) -> None: ...


class _Shape:
    def first(self) -> None: ...
    def second(self) -> None: ...
    def _hidden(self) -> None: ...

    @property
    def size(self) -> int:
        return 1


class _Wider(_Shape):
    def third(self) -> None: ...


def test_a_class_counts_its_public_methods_and_properties_only():
    assert method_count(_Shape) == 3


def test_a_class_counts_the_methods_it_inherits_from_the_project():
    assert method_count(_Wider) == 4


def test_a_protocol_counts_its_members():
    assert method_count(_Role) == 2


def test_the_exceptional_modules_get_the_wider_budget():
    assert budget("conversation") == 10
    assert budget("settings") == 5


def test_the_report_flags_a_package_over_its_budget_and_a_class_over_the_cap():
    lines = report_lines({"settings": {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}, "github": {"Big": 11}})

    assert "settings  6 exports / budget 5  OVER" in lines
    assert "  Big  11 methods / cap 10  OVER" in lines
    assert "github  1 exports / budget 10" in lines


class _Handle:
    @property
    def role(self) -> _Role: ...
    def shape(self) -> _Shape | None: ...
    def count(self) -> int: ...
    def itself(self) -> "_Handle": ...


def test_an_object_hands_out_the_roles_its_properties_and_methods_return_from_its_own_package():
    assert handed_out(_Handle, "tests") == {"_Role": 2, "_Shape": 3}


def test_an_object_hands_out_nothing_from_another_package():
    assert handed_out(_Handle, "github_orchestrator") == {}


def test_the_report_indents_a_handed_out_role_under_its_object_and_flags_it_over_the_cap():
    lines = report_lines({"github": {"Big": 3}}, {"github": {"Big": {"Role": 11}}})

    assert lines.index("    Role  11 methods / cap 10  OVER") == lines.index("  Big  3 methods / cap 10") + 1
