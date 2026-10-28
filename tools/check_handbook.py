"""Check handbook structure and illustrative target contracts without network access.

Run from any directory: python tools/check_handbook.py
This checks structural consistency; it is not physics validation or a proof.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "docs" / "engineering"
STATUSES = {
    "specified",
    "reference_verified",
    "implemented",
    "verified",
    "physics_validated",
    "deferred",
}


def read_json(path: Path):
    def invalid(value):
        raise ValueError(f"nonfinite JSON value {value} in {path}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def ensure_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite contract value")
    if isinstance(value, dict):
        for child in value.values():
            ensure_finite(child)
    elif isinstance(value, list):
        for child in value:
            ensure_finite(child)


def semantic_example_checks(name: str, value: dict) -> None:
    """Validate cross-field invariants JSON Schema cannot express by itself."""
    ensure_finite(value)
    ranges = value.get("source_ranges", [value["source"]] if "source" in value else [])
    seen_ranges: dict[str, list[tuple[int, int]]] = {}
    for source in ranges:
        low, high = source["entry_start"], source["entry_stop"]
        if low >= high:
            raise ValueError(f"{name}: source entry range is not increasing")
        checksum = source["declared_checksum"]
        expected_length = 8 if checksum["algorithm"] == "adler32" else 64
        if len(checksum["value"]) != expected_length:
            raise ValueError(f"{name}: checksum length disagrees with algorithm")
        intervals = seen_ranges.setdefault(source["source_id"], [])
        if any(low < end and start < high for start, end in intervals):
            raise ValueError(f"{name}: overlapping source ranges")
        intervals.append((low, high))
    if name == "event-chunk":
        seen = set()
        for event in value["events"]:
            info = event["EventInfo"]
            source = value["source"]
            identity = (info["dataset_id"], info["source_id"], info["source_entry"])
            if identity in seen:
                raise ValueError("duplicate event identity")
            seen.add(identity)
            if info["source_id"] != source["source_id"]:
                raise ValueError("event source differs from chunk source")
            if not source["entry_start"] <= info["source_entry"] < source["entry_stop"]:
                raise ValueError("event is outside its source range")
            ids = [obj["object_id"] for obj in event["Muon"]]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate muon object identity")
            if info["kind"] == "data":
                weight = info["weight"]
                if any(weight[key] != 1 for key in ("generator", "normalization", "pileup")):
                    raise ValueError("real data has a simulation normalization weight")
    if name == "detector":
        low, high = value["response"]["valid_pt"]
        if low >= high:
            raise ValueError("response validity range is not increasing")
        ids = [volume["volume_id"] for volume in value["geometry"]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate volume IDs")
    if name == "run-plan":
        budgets = value["budgets"]
        planned = sum(source["entry_stop"] - source["entry_start"] for source in ranges)
        if planned > budgets["max_events"]:
            raise ValueError("source coverage exceeds requested event budget")
        if (
            value["validation"]["mode"] == "measurement"
            and not value["validation"]["required_evidence_ids"]
        ):
            raise ValueError("measurement plan has no required validation evidence")


def main() -> int:
    errors = []
    pages = sorted(HANDBOOK.glob("*.md"))
    diagrams = 0
    for page in pages:
        content = page.read_text(encoding="utf-8")
        blocks = re.findall(r"```mermaid\s*\n(.*?)```", content, re.S)
        diagrams += len(blocks)
        if not blocks:
            errors.append(f"{page.name}: missing Mermaid diagram")
        for block in blocks:
            first_line = block.strip().splitlines()[0]
            if not first_line.startswith(
                ("flowchart ", "stateDiagram-v2", "sequenceDiagram", "classDiagram")
            ):
                errors.append(f"{page.name}: unrecognized Mermaid diagram type")
        # Check real relative links; web citations and in-page links are excluded.
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
            target = target.strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            path = (page.parent / unquote(target)).resolve()
            if not path.is_relative_to(ROOT) or not path.exists():
                errors.append(f"{page.name}: missing or external local link {target}")
    register = read_json(HANDBOOK / "requirements.json")
    requirements = register["requirements"]
    ids = [row["id"] for row in requirements]
    if len(ids) != len(set(ids)):
        errors.append("requirements: duplicate IDs")
    for row in requirements:
        if not re.fullmatch(r"[A-Z]+-\d{3}", row["id"]):
            errors.append(f"invalid requirement ID: {row['id']}")
        if row["status"] not in STATUSES:
            errors.append(f"invalid status: {row['id']}")
        if not (HANDBOOK / row["document"]).is_file():
            errors.append(f"missing requirement document: {row['id']}")
        if not row.get("verification"):
            errors.append(f"missing acceptance case: {row['id']}")
        if row["status"] != "specified" and row["status"] != "deferred" and not row["evidence"]:
            errors.append(f"status has no recorded evidence: {row['id']}")
    try:
        from jsonschema import Draft202012Validator, FormatChecker, SchemaError
    except ImportError:
        print("Contract validation requires jsonschema: pip install -e '.[dev]'", file=sys.stderr)
        return 2
    schemas = {}
    for path in sorted((ROOT / "contracts").glob("*.schema.json")):
        schema = read_json(path)
        try:
            Draft202012Validator.check_schema(schema)
            schemas[path.name.removesuffix(".schema.json")] = schema
        except (ValueError, SchemaError) as exc:
            errors.append(f"{path.name}: {exc}")
    examples = sorted((ROOT / "contracts" / "examples").glob("*.json"))
    for example in examples:
        value = read_json(example)
        try:
            Draft202012Validator(schemas[example.stem], format_checker=FormatChecker()).validate(
                value
            )
            semantic_example_checks(example.stem, value)
            if example.stem == "run-plan":
                for requirement_id in value["validation"]["required_evidence_ids"]:
                    if requirement_id not in ids:
                        raise ValueError(f"unknown requirement {requirement_id}")
        except Exception as exc:
            errors.append(f"{example.name}: {exc}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    words = sum(len(path.read_text(encoding="utf-8").split()) for path in pages)
    print(f"Handbook: {len(pages)} pages, {diagrams} Mermaid blocks, approximately {words:,} words")
    print(f"Traceability: {len(requirements)} requirements with unique IDs and acceptance cases")
    print(
        f"Contracts: {len(schemas)} valid schemas, "
        f"{len(examples)} structurally/semantically valid examples"
    )
    print(
        "PASS: local links and structure checked. "
        "Physics and Mermaid rendering are separate checks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
