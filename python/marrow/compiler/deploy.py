"""Produce a DeploymentManifest from a compiled RuntimePlan.

A DeploymentManifest names a plan (by its content-addressed id) and where it
should run. It is a description, not an action — actually deploying a plan is out
of scope; this records the intent in a portable, validated artifact.
"""
from __future__ import annotations

from typing import Any

from .errors import CompileError
from .validate import validate

MANIFEST_VERSION = "ari/v0.draft"


def make_deployment_manifest(
    runtime_plan: dict[str, Any],
    target: str = "local",
    name: str | None = None,
    replicas: int | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a DeploymentManifest for ``runtime_plan`` targeting ``target``.

    Raises :class:`CompileError` if the plan has no ``runtime_plan_id``. The
    returned manifest validates against ``deployment_manifest.schema.json``.
    """
    if "runtime_plan_id" not in runtime_plan:
        raise CompileError("runtime_plan has no runtime_plan_id to deploy")

    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "name": name or runtime_plan.get("name", "deployment"),
        "runtime_plan_id": runtime_plan["runtime_plan_id"],
        "target": target,
    }
    if replicas is not None:
        manifest["replicas"] = replicas
    if env is not None:
        manifest["env"] = env

    validate(manifest, "deployment_manifest.schema.json")
    return manifest
