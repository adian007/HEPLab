"""End-to-end source checks use server digests, local bytes, and a streamed fallback."""

import hashlib
import io
import zlib

import pytest

from heplab.io import xrootd
from heplab.io.cache import source_integrity_record
from heplab.io.provenance import config_hash


class Response(io.BytesIO):
    def __init__(self, body=b"", headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_local_adler32_checks_exact_bytes_and_size(tmp_path):
    source = tmp_path / "source.root"
    payload = b"verified input bytes"
    source.write_bytes(payload)
    declared = {"algorithm": "adler32", "value": f"{zlib.adler32(payload):08x}"}
    identity = config_hash({"source": str(source), "checksum": declared})

    assert xrootd._verify_source(str(source), declared, len(payload), identity, cache=False)
    with pytest.raises(ValueError, match="adler32 mismatch"):
        xrootd._verify_source(
            str(source),
            {"algorithm": "adler32", "value": "00000001"},
            len(payload),
            identity,
            cache=False,
        )
    with pytest.raises(ValueError, match="file size"):
        xrootd._verify_source(str(source), declared, len(payload) + 1, identity, cache=False)


def test_remote_digest_is_cached_without_downloading_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HEPLAB_CACHE_DIR", str(tmp_path / "cache"))
    payload = b"remote bytes"
    checksum = f"{zlib.adler32(payload):08x}"
    calls = []

    def open_request(request, timeout):
        calls.append(request.get_method())
        assert request.headers["Want-digest"] == "adler32"
        return Response(
            headers={"Content-Length": str(len(payload)), "Digest": f"adler32={checksum}"}
        )

    monkeypatch.setattr(xrootd.urllib.request, "urlopen", open_request)
    declared = {"algorithm": "adler32", "value": checksum}
    source_id = config_hash({"url": "https://example.test/source.root", "declared": declared})
    url = "https://example.test/source.root"

    assert (
        xrootd._verify_source(url, declared, len(payload), source_id, cache=True) == "remote_digest"
    )
    assert (
        xrootd._verify_source(url, declared, len(payload), source_id, cache=True) == "remote_digest"
    )
    assert calls == ["HEAD", "HEAD"]
    assert source_integrity_record(source_id, declared, len(payload))["verified"] is True


def test_remote_checksum_stream_fallback_and_retry_backoff(monkeypatch):
    payload = b"fallback payload" * 3
    expected = f"{zlib.adler32(payload):08x}"
    calls, delays = [], []

    def open_request(request, timeout):
        calls.append(request.get_method())
        if len(calls) in {1, 2}:
            raise OSError("temporary endpoint failure")
        if request.get_method() == "HEAD":
            return Response(headers={"Content-Length": str(len(payload))})
        return Response(payload, {"Content-Length": str(len(payload))})

    monkeypatch.setattr(xrootd.urllib.request, "urlopen", open_request)
    monkeypatch.setattr(xrootd.time, "sleep", delays.append)
    assert xrootd._remote_checksum("https://example.test/a.root", "adler32", len(payload)) == (
        expected,
        "remote_stream",
    )
    assert delays == [2, 4]
    assert calls[-1] == "GET"


def test_remote_sha256_stream_matches_bytes(monkeypatch):
    payload = b"sha256 fallback"
    monkeypatch.setattr(
        xrootd.urllib.request,
        "urlopen",
        lambda request, timeout: Response(payload, {"Content-Length": str(len(payload))}),
    )
    actual, method = xrootd._remote_checksum("https://example.test/a.root", "sha256", len(payload))
    assert actual == hashlib.sha256(payload).hexdigest()
    assert method == "remote_stream"
