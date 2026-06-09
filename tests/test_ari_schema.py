"""ARI manifest schemas are well-formed and the validator accepts/rejects
manifests with clear errors."""
import json

import pytest

from marrow.compiler.errors import CompileError
from marrow.compiler.validate import load_schema, validate

SCHEMA_FILES = [
    "agent_graph.schema.json",
    "tool_spec.schema.json",
    "provider_spec.schema.json",
    "policy_spec.schema.json",
    "runtime_plan.schema.json",
    "execution_trace.schema.json",
    "deployment_manifest.schema.json",
]


def _echo_graph() -> dict:
    return {
        "version": "ari/v0.draft",
        "name": "echo_agent",
        "providers": [
            {"id": "mock", "type": "mock", "model": "mock-echo", "config_ref": None}
        ],
        "tools": [
            {
                "name": "echo",
                "description": "Echo input text",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                "side_effects": False,
                "timeout_ms": 1000,
                "requires_approval": False,
            }
        ],
        "agents": [
            {
                "id": "agent_1",
                "name": "Echo Agent",
                "provider": "mock",
                "system_prompt": "You are a test echo agent.",
                "tools": ["echo"],
                "state": {},
            }
        ],
        "edges": [],
        "entrypoint": "agent_1",
    }


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_files_are_valid_json(name):
    schema = load_schema(name)
    assert schema["$schema"]
    assert schema["title"]
    assert isinstance(json.dumps(schema), str)  # serializable round-trip


def test_validator_accepts_echo_graph():
    validate(_echo_graph(), "agent_graph.schema.json")  # must not raise


def test_missing_required_field_is_rejected_clearly():
    bad = _echo_graph()
    del bad["entrypoint"]
    with pytest.raises(CompileError) as ei:
        validate(bad, "agent_graph.schema.json")
    assert "entrypoint" in str(ei.value)
    assert "required" in str(ei.value)


def test_wrong_type_is_rejected():
    bad = _echo_graph()
    bad["agents"][0]["tools"] = "echo"  # should be a list
    with pytest.raises(CompileError) as ei:
        validate(bad, "agent_graph.schema.json")
    assert "tools" in str(ei.value)


def test_additional_property_is_rejected():
    bad = _echo_graph()
    bad["surprise"] = 1
    with pytest.raises(CompileError) as ei:
        validate(bad, "agent_graph.schema.json")
    assert "surprise" in str(ei.value)


def test_cross_file_ref_validates_nested_provider_and_tool():
    bad = _echo_graph()
    bad["providers"][0]["config_ref"] = 123  # must be string or null
    with pytest.raises(CompileError) as ei:
        validate(bad, "agent_graph.schema.json")
    assert "config_ref" in str(ei.value)


def test_enum_condition_rejected_when_invalid():
    bad = _echo_graph()
    bad["edges"] = [{"from": "agent_1", "to": "agent_1", "condition": {"type": "sometimes"}}]
    with pytest.raises(CompileError) as ei:
        validate(bad, "agent_graph.schema.json")
    assert "condition" in str(ei.value) or "sometimes" in str(ei.value)
