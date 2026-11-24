"""Structured HEPLab training catalogue and resumable learner progress."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "heplab-training-catalog-v1"
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class CompletionEvidence:
    """Evidence must describe an application state or public artifact."""

    kind: str
    contract: str
    required: dict[str, Any] = field(default_factory=dict)


def catalogue() -> dict:
    path = HERE / "curriculum.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported HEPLab training catalogue schema")
    validate(value)
    return value


def modules() -> list[dict]:
    return catalogue()["modules"]


def get(module_id: str) -> dict:
    for module in modules():
        if module["id"] == module_id:
            return module
    raise KeyError(f"unknown training module {module_id!r}")


def validate(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("training catalogue must be a JSON object")
    ids: set[str] = set()
    seen: set[str] = set()
    for module in value.get("modules", []):
        if not isinstance(module, Mapping):
            raise ValueError("module must be a JSON object")
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id or module_id in ids:
            raise ValueError("module ids must be unique, non-empty strings")
        ids.add(module_id)
        if not isinstance(module.get("steps"), list) or not module["steps"]:
            raise ValueError(f"module {module_id} must contain steps")
        for step in module["steps"]:
            if not isinstance(step, Mapping):
                raise ValueError(f"module {module_id} contains a malformed step")
            step_id = step.get("id")
            if not isinstance(step_id, str) or not step_id:
                raise ValueError(f"module {module_id} contains a step without an id")
            for prerequisite in step.get("prerequisites", []):
                if prerequisite not in seen:
                    raise ValueError(
                        f"module {module_id} step {step_id} prerequisite "
                        f"{prerequisite} is not an earlier module"
                    )
            evidence = step.get("completion_evidence")
            if not isinstance(evidence, Mapping):
                raise ValueError(f"module {module_id} step {step_id} lacks completion evidence")
        seen.add(module_id)


def start(module_id: str) -> "TrainingSession":
    return TrainingSession(get(module_id))


def resume(path: str | Path) -> "TrainingSession":
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if saved.get("schema") != "heplab-training-progress-v1":
        raise ValueError("unsupported HEPLab training progress schema")
    session = start(saved["module"])
    session.results = saved.get("results", {})
    session.context = saved.get("context", {})
    return session


class TrainingSession:
    def __init__(self, module: Mapping[str, Any]):
        self.module = dict(module)
        self.results: dict[str, dict] = {}
        self.context: dict[str, Any] = {}

    @property
    def current(self) -> dict | None:
        for step in self.module["steps"]:
            if not self.results.get(step["id"], {}).get("passed"):
                return step
        return None

    def complete(self, step_id: str, evidence: Mapping[str, Any]) -> dict:
        step = next((item for item in self.module["steps"] if item["id"] == step_id), None)
        if step is None:
            raise KeyError(f"unknown step {step_id!r}")
        contract = step["completion_evidence"]
        kind = contract["kind"]
        passed = evidence.get("kind") == kind
        if passed:
            for key, expected in contract.get("required", {}).items():
                if evidence.get(key) != expected:
                    passed = False
                    break
        result = {
            "passed": passed,
            "message": (
                "Completion evidence matches the simulator contract."
                if passed
                else f"Evidence must match contract {contract['contract']}."
            ),
            "evidence": dict(evidence),
        }
        self.results[step_id] = result
        return result

    def progress(self) -> dict:
        completed = sum(1 for result in self.results.values() if result.get("passed"))
        return {
            "schema": "heplab-training-progress-v1",
            "module": self.module["id"],
            "completed": completed,
            "steps": len(self.module["steps"]),
            "results": self.results,
            "context": self.context,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(json.dumps(self.progress(), indent=2), encoding="utf-8")
        return target
