"""Provenance stamp tests (ADR-0008).

Hashes must be deterministic and content-sensitive: two identical stamps imply
identical physics content, so any drift must change the digest.
"""

from heplab.io.provenance import ProvenanceStamp, config_hash, sha256_hex


def test_sha256_known_vector():
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_config_hash_is_order_independent():
    a = config_hash({"selection": {"min_pt": 25.0, "max_eta": 2.4}, "fit": {"range": [70, 110]}})
    b = config_hash({"fit": {"range": [70, 110]}, "selection": {"max_eta": 2.4, "min_pt": 25.0}})
    assert a == b


def test_config_hash_is_content_sensitive():
    a = config_hash({"min_pt": 25.0})
    b = config_hash({"min_pt": 30.0})
    assert a != b


def _stamp(**overrides) -> ProvenanceStamp:
    fields = dict(
        schema_version=1,
        git_sha="0" * 40,
        config_sha256="1" * 64,
        dataset_manifest_hash="2" * 64,
        container_digest="sha256:" + "3" * 64,
    )
    fields.update(overrides)
    return ProvenanceStamp(**fields)


def test_stamp_digest_is_deterministic():
    assert _stamp().digest() == _stamp().digest()


def test_stamp_digest_detects_drift():
    base = _stamp()
    for changed in (
        {"git_sha": "f" * 40},
        {"config_sha256": "a" * 64},
        {"dataset_manifest_hash": "b" * 64},
        {"container_digest": ""},
        {"schema_version": 2},
    ):
        assert _stamp(**changed).digest() != base.digest(), changed


def test_stamp_roundtrip():
    stamp = _stamp()
    d = stamp.to_dict()
    assert ProvenanceStamp(**d) == stamp
