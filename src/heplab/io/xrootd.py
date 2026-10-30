"""Exact-range remote streaming with verified transactional chunk reuse."""

from __future__ import annotations

import hashlib
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from .. import catalog
from .cache import (
    cache_key,
    open_cached,
    quarantine,
    record_source_integrity,
    source_integrity_record,
    write_json_events,
)
from .provenance import config_hash, file_hash

EOS_PUBLIC = "root://eospublic.cern.ch//eos/opendata"


def dataset_url(record_path: str) -> str:
    return f"{EOS_PUBLIC}/{record_path.strip('/')}"


def _manifests_dir() -> Path:
    return catalog.manifests_dir()


def load_manifest(dataset: str):
    return catalog.get(dataset, _manifests_dir())


def _retry(call, attempts: int = 3, delay_s: float = 2.0):
    """Retry transient I/O (network) failures with exponential backoff."""
    for attempt in range(attempts):
        try:
            return call()
        except OSError as exc:
            if attempt == attempts - 1:
                raise
            print(f"heplab: transient read error ({exc}); retrying", file=sys.stderr)
            time.sleep(delay_s * 2**attempt)


def _checksum_file(path: Path, algorithm: str) -> tuple[str, int]:
    size = 0
    if algorithm == "adler32":
        checksum = 1
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum = zlib.adler32(block, checksum)
                size += len(block)
        return f"{checksum & 0xFFFFFFFF:08x}", size
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _remote_checksum(url: str, algorithm: str, expected_size: int) -> tuple[str, str]:
    """Ask the CERN HTTP endpoint for its digest, streaming the file if unsupported."""

    def head():
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"Want-Digest": algorithm},
        )
        try:
            return urllib.request.urlopen(request, timeout=45)
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 405, 501}:
                return None
            error_type = OSError if exc.code == 429 or exc.code >= 500 else ValueError
            raise error_type(f"source checksum HEAD failed with HTTP {exc.code}") from exc

    response = _retry(head)
    if response is not None:
        with response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != expected_size:
                raise ValueError("SourceChanged: declared file size differs from HTTP source")
            entries = response.headers.get("Digest", "").split(",")
            for entry in entries:
                key, separator, value = entry.strip().partition("=")
                if separator and key.lower().replace("-", "") == algorithm.lower().replace("-", ""):
                    return value.strip().strip('"').lower(), "remote_digest"

    print(
        "heplab: source has no server checksum response; streaming "
        f"{expected_size} bytes to verify {algorithm}",
        file=sys.stderr,
    )

    def stream():
        request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            error_type = OSError if exc.code == 429 or exc.code >= 500 else ValueError
            raise error_type(f"source checksum GET failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"source checksum download failed: {exc}") from exc
        count = 0
        if algorithm == "adler32":
            checksum = 1
            with response:
                while block := response.read(1024 * 1024):
                    checksum = zlib.adler32(block, checksum)
                    count += len(block)
            actual = f"{checksum & 0xFFFFFFFF:08x}"
        else:
            digest = hashlib.sha256()
            with response:
                while block := response.read(1024 * 1024):
                    digest.update(block)
                    count += len(block)
            actual = digest.hexdigest()
        if count != expected_size:
            raise OSError(
                f"incomplete source checksum stream: read {count} of {expected_size} bytes"
            )
        return actual, "remote_stream"

    return _retry(stream)


def _verify_source(url: str, declared: dict, size_bytes: int, source_id: str, *, cache: bool):
    # Receipts are audit/cache records; current local bytes or the server digest are
    # checked again so a mutable URL cannot silently change under a warm event cache.
    if cache:
        source_integrity_record(source_id, declared, size_bytes)
    algorithm, expected = declared["algorithm"], declared["value"].lower()
    local = Path(url)
    if local.is_file():
        actual, actual_size = _checksum_file(local, algorithm)
        method = "local_bytes"
        if actual_size != size_bytes:
            raise ValueError("SourceChanged: declared file size differs from local source")
    else:
        actual, method = _remote_checksum(url, algorithm, size_bytes)
    if actual != expected:
        raise ValueError(
            f"SourceChanged: {algorithm} mismatch; declared {expected}, observed {actual}"
        )
    if cache:
        record_source_integrity(source_id, declared, size_bytes, method)
    return method


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
    import uproot

    from ..readers.nanoaod import READER_VERSION, read

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
        size_bytes = int(record["size_bytes"])
        source_id = config_hash({"url": url, "checksum": declared, "size_bytes": size_bytes})
        integrity_method = _verify_source(url, declared, size_bytes, source_id, cache=cache)

        def inspect(url=url):
            with uproot.open(url) as root:
                return root["Events"].num_entries, root.file.source.num_bytes

        entries, actual_size = _retry(inspect)
        if actual_size != size_bytes:
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
                "integrity": "source_checksum_verified",
                "integrity_method": integrity_method,
                "manifest_sha256": manifest_hash,
                "reader": READER_VERSION,
                "is_data": source_is_data,
            }
            # The cache holds raw source rows; certification is applied on the way out,
            # so `heplab fetch` warms the same entries that a certified `run` reads.
            key = cache_key(name, frozenset(branches or ()), 1, source_descriptor=descriptor)
            events = None
            if cache:
                try:
                    events = open_cached(key, expected=descriptor)
                except FileNotFoundError:
                    pass
                except ValueError as exc:
                    moved = quarantine(key)
                    print(
                        f"heplab: cache entry {key} is damaged ({exc}); moved to {moved}",
                        file=sys.stderr,
                    )
            if events is None:
                request = dict(
                    entry_start=start,
                    entry_stop=descriptor["entry_stop"],
                    is_data=source_is_data,
                    branches=branches,
                    source_id=source_id,
                )
                events = _retry(lambda url=url, request=request: list(read(url, **request)))
                if len(events) != descriptor["entry_stop"] - start:
                    raise ValueError("source returned incomplete entry range") from None
                if cache:
                    write_json_events(key, events, descriptor=descriptor)
            if lumi_mask and source_is_data:
                for event in events:
                    info = event["EventInfo"]
                    info["certified"] = lumi_mask.accepts(info["run"], info["luminosity_block"])
                    info["certification_sha256"] = lumi_mask.sha256
            descriptor = {
                **descriptor,
                "certification_sha256": lumi_mask.sha256 if lumi_mask else "",
            }
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
