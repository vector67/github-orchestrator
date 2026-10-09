import json
from pathlib import Path

from tests.board_api.support import board_contract, hub_contract, rewritten

FRONTEND = Path(__file__).parents[2] / "frontend"
COPY = FRONTEND / "tests" / "helpers" / "board-api-contract.json"
TYPES = FRONTEND / "app" / "data" / "api.ts"

PROSE = {"title", "description", "default", "examples"}


def _shape(schema):
    if isinstance(schema, list):
        return [_shape(one) for one in schema]
    if not isinstance(schema, dict):
        return schema
    return {key: ({name: _shape(one) for name, one in value.items()}
                  if key == "properties" else _shape(value))
            for key, value in schema.items() if key not in PROSE}


def _schema_of(answer):
    content = answer.get("content", {})
    if "text/event-stream" in content:
        return _shape(content["text/event-stream"]["itemSchema"]["properties"]["data"]
                      ["contentSchema"])
    return _shape(content.get("application/json", {}).get("schema"))


def _answers(operation):
    return {status: _schema_of(answer) for status, answer in operation["responses"].items()}


def contract_for_the_board_app(document):
    return {
        "paths": {path: {method: _answers(operation)
                         for method, operation in methods.items()}
                  for path, methods in document["paths"].items()},
        "schemas": {name: _shape(schema)
                    for name, schema in document["components"]["schemas"].items()},
    }


def _merged(board, hub):
    shared = board["schemas"].keys() & hub["schemas"].keys()
    differing = sorted(name for name in shared if board["schemas"][name] != hub["schemas"][name])
    assert not differing, f"the board and the hub each serve their own {differing}"
    return {"paths": {**hub["paths"], **board["paths"]},
            "schemas": {**hub["schemas"], **board["schemas"]}}


def _literal(value):
    return f"'{value}'" if isinstance(value, str) else json.dumps(value)


def _union(parts):
    return " | ".join(dict.fromkeys(parts))


def _ts(schema):
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[1]
    if "anyOf" in schema or "oneOf" in schema:
        return _union(_ts(one) for one in schema.get("anyOf") or schema["oneOf"])
    if "const" in schema:
        return _literal(schema["const"])
    if "enum" in schema:
        return _union(_literal(value) for value in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        item = _ts(schema["items"])
        return f"({item})[]" if " | " in item else f"{item}[]"
    if kind == "object":
        return "{ " + " ".join(f"{line};" for line in _fields(schema)) + " }"
    return {"string": "string", "integer": "number", "number": "number",
            "boolean": "boolean", "null": "null"}.get(kind, "unknown")


def _fields(schema):
    required = set(schema.get("required", []))
    return [f"{name}{'' if name in required else '?'}: {_ts(one)}"
            for name, one in schema.get("properties", {}).items()]


def _declarations(name, schema):
    if schema.get("type") == "object" and "properties" in schema:
        body = "".join(f"  {line};\n" for line in _fields(schema))
        return [f"export interface {name} {{\n{body}}}\n"]
    items = schema.get("items", {})
    if schema.get("type") == "array" and "$ref" not in items and name.endswith("List"):
        member = name.removesuffix("List")
        return [f"export type {member} = {_ts(items)};\n",
                f"export type {name} = {member}[];\n"]
    return [f"export type {name} = {_ts(schema)};\n"]


def wire_types(contract):
    return "\n".join(declaration for name in sorted(contract["schemas"])
                     for declaration in _declarations(name, contract["schemas"][name]))


def test_the_board_app_checks_its_fake_against_the_contract_the_board_serves():
    board = contract_for_the_board_app(board_contract())
    hub = contract_for_the_board_app(hub_contract())
    contract = _merged(board, hub)
    wanted = json.dumps(contract, indent=1, sort_keys=True) + "\n"
    types = wire_types(contract)

    held = rewritten(COPY, wanted)
    held_types = rewritten(TYPES, types)

    assert (held, held_types) == (wanted, types), (
        f"{COPY.name} or {TYPES.name} was behind /api/openapi.json and has "
        "been rewritten; commit both and run the ember suite, whose types "
        "come from it and whose FakeBoard answers are checked against it")
