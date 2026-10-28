"""Exact-range remote streaming with verified transactional chunk reuse."""

from __future__ import annotations

import re
from pathlib import Path

from .. import catalog
from .cache import cache_key, open_cached, write_json_events
from .provenance import config_hash, file_hash

EOS_PUBLIC = "root://eospublic.cern.ch//eos/opendata"


def dataset_url(record_path: str) -> str:
    return f"{EOS_PUBLIC}/{record_path.strip('/')}"


def _manifests_dir() -> Path:
    return catalog.manifests_dir()


def load_manifest(dataset: str):
    return catalog.get(dataset, _manifests_dir())


def _sample_limit(sample: str | int | None) -> int | None:
    if sample is None:
        return None
    if type(sample) is int:
        value = sample
    elif isinstance(sample, str) and re.fullmatch(r"[0-9]+(?:events)?", sample.strip()):
        value = int(sample.strip().removesuffix("events"))
    else:
        raise ValueError(
            "sample must be an exact positive event count; byte estimates are unsupported"
        )
    if value <= 0:
        raise ValueError("sample count must be positive")
    return value


def iter_chunks(
    dataset: str,
    branches: list[str] | None = None,
    sample=None,
    *,
    cache: bool = True,
    chunk_size: int = 100_000,
    is_data: bool | None = None,
    lumi_mask=None,
):
    import uproot

    from ..readers.nanoaod import READER_VERSION, read

    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk size must be a positive integer")
    manifest, path = load_manifest(dataset)
    if not manifest.get("files") or not manifest.get("record"):
        raise ValueError("example manifest: verified record and file list required")
    if manifest.get("format", "").upper() not in {"NANOAOD", "NANOAODSIM"}:
        raise ValueError("unsupported dataset format")
    source_is_data = manifest.get("kind", "data") == "data"
    if is_data is not None and is_data != source_is_data:
        raise ValueError("CLI data/simulation kind disagrees with manifest")
    name = manifest.get("name", manifest.get("dataset_id", dataset))
    manifest_hash = file_hash(path)
    limit = _sample_limit(sample)
    remaining = limit
    for record in manifest["files"]:
        url = record.get("url") or record.get("uri") or record.get("path")
        if not isinstance(url, str) or not url:
            raise ValueError("file entry has no source URL")
        if not url.startswith(("root://", "https://", "http://")) and not Path(url).is_file():
            url = dataset_url(f"{manifest['url_path'].strip('/')}/{url.lstrip('/')}")
        url = url.replace(EOS_PUBLIC, "https://opendata.cern.ch/eos/opendata", 1)
        declared = record.get(
            "checksum", {"algorithm": "adler32", "value": str(record.get("adler32", ""))}
        )
        if (
            not re.fullmatch(r"[0-9a-f]{8}|[0-9a-f]{64}", declared.get("value", ""))
            or int(record.get("size_bytes", 0)) <= 0
        ):
            raise ValueError("file entry needs a valid declared checksum and positive size")
        algorithm = declared.get("algorithm")
        if (
            algorithm not in {"adler32", "sha256"}
            or len(declared["value"]) != {"adler32": 8, "sha256": 64}[algorithm]
        ):
            raise ValueError("source checksum algorithm and value disagree")
        source_id = config_hash(
            {"url": url, "checksum": declared, "size_bytes": record["size_bytes"]}
        )
        with uproot.open(url) as root:
            entries = root["Events"].num_entries
            actual_size = root.file.source.num_bytes
        if actual_size != record["size_bytes"]:
            raise ValueError("SourceChanged: declared file size differs from source")
        if record.get("entries") is not None and entries != record["entries"]:
            raise ValueError("SourceChanged: source entry count differs from manifest")
        stop = entries if remaining is None else min(entries, remaining)
        for start in range(0, stop, chunk_size):
            descriptor = {
                "dataset": name,
                "source_id": source_id,
                "uri": url,
                "entry_start": start,
                "entry_stop": min(start + chunk_size, stop),
                "declared_checksum": declared,
                "integrity": "declared_only",
                "manifest_sha256": manifest_hash,
                "reader": READER_VERSION,
                "is_data": source_is_data,
                "certification_sha256": lumi_mask.sha256 if lumi_mask else "",
            }
            key = cache_key(name, frozenset(branches or ()), 1, source_descriptor=descriptor)
            try:
                if not cache:
                    raise FileNotFoundError
                events = open_cached(key, expected=descriptor)
            except FileNotFoundError:
                events = list(
                    read(
                        url,
                        entry_start=start,
                        entry_stop=descriptor["entry_stop"],
                        is_data=source_is_data,
                        branches=branches,
                        source_id=source_id,
                    )
                )
                if len(events) != descriptor["entry_stop"] - start:
                    raise ValueError("source returned incomplete entry range") from None
                if lumi_mask and source_is_data:
                    for event in events:
                        info = event["EventInfo"]
                        info["certified"] = lumi_mask.accepts(info["run"], info["luminosity_block"])
                        info["certification_sha256"] = lumi_mask.sha256
                if cache:
                    write_json_events(key, events, descriptor=descriptor)
            yield descriptor, events
        if remaining is not None:
            remaining -= stop
            if remaining == 0:
                return
    if remaining:
        raise ValueError("dataset contains fewer events than the requested sample")


def fetch(
    dataset: str,
    branches=None,
    sample=None,
    *,
    cache=True,
    chunk_size=100_000,
    is_data: bool | None = None,
    lumi_mask=None,
) -> list[dict]:
    """Small-sample compatibility API; use iter_chunks for large datasets."""
    if sample is None:
        raise ValueError("fetch requires a bounded sample; use iter_chunks for full datasets")
    return [
        event
        for _, chunk in iter_chunks(
            dataset,
            branches,
            sample,
            cache=cache,
            chunk_size=chunk_size,
            is_data=is_data,
            lumi_mask=lumi_mask,
        )
        for event in chunk
    ]
