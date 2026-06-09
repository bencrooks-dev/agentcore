"""Minimal JSON-Schema validation for ARI manifests.

Stdlib only, on purpose: Marrow targets a near-zero dependency footprint
(ARI-SPEC §10.2), so the compiler does not pull in a full JSON-Schema engine for
seven small schemas. This validator supports exactly the subset those schemas
use:

- ``type`` (a string, or a list of strings including ``"null"``)
- ``properties`` / ``required`` / ``additionalProperties`` (``false``)
- ``items`` / ``minItems`` for arrays
- ``enum``
- ``$ref`` to a sibling ``<name>.schema.json`` or a local ``#/$defs/...`` pointer

It is not a general validator; it is enough to validate (and clearly reject)
the manifests this compiler produces and consumes.
"""
from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

from .errors import CompileError


def _find_schema_dir() -> Path:
    """Locate ``ari/schemas`` relative to this source tree (editable install) or
    via the ``MARROW_ARI_SCHEMA_DIR`` override."""
    env = os.environ.get("MARROW_ARI_SCHEMA_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "ari" / "schemas"
        if candidate.is_dir():
            return candidate
    raise CompileError(
        "ari/schemas directory not found; set MARROW_ARI_SCHEMA_DIR to its path"
    )


@cache
def _schema_dir() -> Path:
    return _find_schema_dir()


@cache
def load_schema(name: str) -> dict[str, Any]:
    path = _schema_dir() / name
    if not path.is_file():
        raise CompileError(f"schema not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _type_ok(value: Any, type_name: str) -> bool:
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    return True  # unknown type keyword: don't fail on it


def _resolve_ref(ref: str, root: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if ref.startswith("#/"):
        node: Any = root
        for part in ref[2:].split("/"):
            node = node[part]
        return node, root
    sub = load_schema(ref)
    return sub, sub


def _validate(value: Any, schema: dict[str, Any], root: dict[str, Any],
              path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        sub, sub_root = _resolve_ref(schema["$ref"], root)
        _validate(value, sub, sub_root, path, errors)
        return

    where = path or "<root>"

    declared_type = schema.get("type")
    if declared_type is not None:
        types = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{where}: expected type {declared_type}, got {type(value).__name__}")
            return  # further checks assume the type matched

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{where}: missing required property '{req}'")
        allow_additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            if key in props:
                _validate(item, props[key], root, child, errors)
            elif allow_additional is False:
                errors.append(f"{child}: additional property not allowed")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{where}: expected at least {min_items} item(s), got {len(value)}")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, element in enumerate(value):
                _validate(element, items, root, f"{path}[{i}]", errors)


def validate(value: Any, schema_name: str) -> None:
    """Validate ``value`` against ``ari/schemas/<schema_name>``.

    Raises :class:`CompileError` listing every problem, or returns ``None`` if
    the value is valid.
    """
    schema = load_schema(schema_name)
    errors: list[str] = []
    _validate(value, schema, schema, "", errors)
    if errors:
        raise CompileError(
            f"schema validation failed against {schema_name}:\n  - "
            + "\n  - ".join(errors)
        )
