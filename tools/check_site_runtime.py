"""Smoke-test a built or published guide in Production, including asset bodies.

An HTTP 200 alone is insufficient: an unloaded build asset manifest can produce
empty successful responses for styles and scripts. Use only the standard library.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

SITE = Path(__file__).resolve().parents[1] / "web/HEPLab.Web"


class AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: set[str] = set()
        self.links: set[str] = set()
        self.ids: set[str] = set()
        self.headings = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            identifier = attributes["id"]
            if identifier in self.ids:
                raise AssertionError(f"duplicate page id: {identifier}")
            self.ids.add(identifier)
        if tag == "a" and attributes.get("href"):
            self.links.add(attributes["href"])
        if tag == "h1":
            self.headings += 1
        target = attributes.get("src") if tag in {"script", "img"} else None
        if tag == "link" and attributes.get("rel") in {"stylesheet", "icon", "preload"}:
            target = attributes.get("href")
        if target:
            self.urls.add(target)


def fetch(url: str, encoding: str = "identity") -> tuple[str, bytes]:
    request = Request(url, headers={"Accept-Encoding": encoding})
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise AssertionError(f"{url}: expected HTTP 200, got {response.status}")
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        if not body:
            raise AssertionError(f"{url}: empty HTTP 200 response ({encoding})")
        return response.headers.get_content_type(), body


def check(base: str, asset_sources: dict[str, str]) -> tuple[int, int]:
    assets = {"/assets/z-boson-demo.json"}
    _, index_body = fetch(base + "/search-index.json")
    search_index = json.loads(index_body)
    routes = tuple(dict.fromkeys(["/", *(page["url"] for page in search_index)]))
    pages: dict[str, AssetReferences] = {}
    local_links: set[str] = set()
    for route in routes:
        page_url = base + route
        content_type, body = fetch(page_url)
        if content_type != "text/html":
            raise AssertionError(f"{page_url}: expected HTML, got {content_type}")
        parser = AssetReferences()
        parser.feed(body.decode("utf-8"))
        pages[route] = parser
        if parser.headings != 1:
            raise AssertionError(f"{route}: expected one page heading, got {parser.headings}")
        for target in parser.links:
            url = urljoin(page_url, target)
            if urlsplit(url).netloc == urlsplit(base).netloc:
                local_links.add(url)
        if route == "/":
            check_preview(body.decode("utf-8"))
        if route == "/education/" and b'id="zlab-stage"' not in body:
            raise AssertionError("Razor lab component did not render")
        if route == "/gallery/" and body.count(b'class="zgallery-card"') != 4:
            raise AssertionError("Razor gallery component must render all four evidence examples")
        for target in parser.urls:
            url = urljoin(page_url, target)
            if urlsplit(url).netloc == urlsplit(base).netloc:
                assets.add(urlsplit(url).path)

    for url in sorted(local_links):
        parsed = urlsplit(url)
        if parsed.path in pages:
            if parsed.fragment and unquote(parsed.fragment) not in pages[parsed.path].ids:
                raise AssertionError(f"broken page anchor: {url}")
        else:
            fetch(url)

    required = {
        "/css/site.css",
        "/css/activities.css",
        "/js/theme-init.js",
        "/js/site.js",
        "/js/detector-view.js",
        "/js/zlab.js",
        "/js/gallery.js",
        "/vendor/bootstrap/5.3.8/bootstrap.min.css",
        "/vendor/bootstrap/5.3.8/bootstrap.bundle.min.js",
    }
    canonical_assets = {asset_sources.get(asset, asset) for asset in assets}
    if not required.issubset(canonical_assets):
        raise AssertionError(
            f"page asset references missing: {sorted(required - canonical_assets)}"
        )
    for stylesheet in tuple(assets):
        if stylesheet.endswith(".css"):
            _, css = fetch(base + stylesheet)
            for target in re.findall(r"url\(['\"]?(/[^)'\"]+)", css.decode("utf-8")):
                assets.add(target)
    mime_types = {
        ".css": {"text/css"},
        ".js": {"text/javascript", "application/javascript"},
        ".png": {"image/png"},
        ".svg": {"image/svg+xml"},
        ".json": {"application/json"},
        ".woff2": {"font/woff2"},
    }
    for asset in sorted(assets):
        source = SITE / "wwwroot" / unquote(asset_sources.get(asset, asset)).lstrip("/")
        expected = source.read_bytes()
        if source.suffix == ".svg":
            if ElementTree.fromstring(expected).tag != "{http://www.w3.org/2000/svg}svg":
                raise AssertionError(f"{asset}: standalone SVG is missing its namespace")
        for encoding in ("identity", "gzip"):
            content_type, body = fetch(base + asset, encoding)
            if content_type not in mime_types[source.suffix]:
                raise AssertionError(f"{asset}: incorrect content type {content_type}")
            if body != expected:
                raise AssertionError(f"{asset}: served bytes differ from source ({encoding})")

    content_type, body = fetch(base + "/search-index.json")
    if content_type != "application/json" or not json.loads(body):
        raise AssertionError("search index is not a nonempty JSON response")
    return len(routes), len(assets)


def check_preview(html: str) -> None:
    """Check figure scope and independent physics conventions against the fixed fixture."""
    fixture = json.loads(
        (SITE / "wwwroot/examples/analytic-muon-pair-result-v1.json").read_text(encoding="utf-8")
    )
    requirements = (
        'data-fixture-url="/examples/analytic-muon-pair-result-v1.json"',
        "data-detector-view",
        'role="img"',
        "SYNTHETIC FIXTURE",
        "B = +z",
        "1 mm Si slab at s = 1 m",
        "Dashed: outside field region",
        "3 m bore boundary",
        fixture["geometry"]["id"],
    )
    missing = [token for token in requirements if token not in html]
    if missing:
        raise AssertionError(
            f"home 3D event figure is missing its declared scope, units, or provenance: {missing}"
        )
    tracks = fixture["tracks"]
    if len(tracks) != 2 or {track["charge"] for track in tracks} != {-1, 1}:
        raise AssertionError("the declared fixture must contain one muon of each charge")
    bz = fixture["geometry"]["field"]["nominal_bz_t"]
    pt = fixture["config"]["momentum_gev"]
    if not math.isclose(bz, 3.8) or not math.isclose(pt, 5.0):
        raise AssertionError("home figure settings no longer match its declared fixture")
    for track in tracks:
        trajectory = track["trajectory"]
        if len(trajectory["points"]) != len(trajectory["path_m"]):
            raise AssertionError("fixture path positions and path lengths must stay paired")
        if trajectory["field_exit_path_m"] <= 0 or not track["material"].get("state", {}).get(
            "position"
        ):
            raise AssertionError("fixture must declare the field exit and material-slab location")
        truth_px = track["truth"]["momentum"]["px"]
        first_y = next(y for _, y, _ in trajectory["points"][1:] if abs(y) > 1e-10)
        expected_y_sign = -track["charge"] * math.copysign(1, truth_px * bz)
        if math.copysign(1, first_y) != expected_y_sign:
            raise AssertionError("muon initial bending direction disagrees with q(v × B)")
        expected_radius = pt / (0.299792458 * abs(track["charge"] * bz))
        if not math.isclose(expected_radius, 4.39, abs_tol=0.02):
            raise AssertionError(
                "fixture settings give an unexpected ideal transverse curvature scale"
            )
    if fixture["artifact"]["result_sha256"][:10] not in html:
        raise AssertionError("home preview lacks its actual fixture result digest")
    manifest = json.loads((SITE / "wwwroot/vendor/ui-assets.json").read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        source = SITE / "wwwroot" / asset["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != asset["sha256"]:
            raise AssertionError(f"vendored UI asset hash mismatch: {source}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True, help="Built or published DLL")
    parser.add_argument("--content-root", type=Path, help="Defaults to the DLL directory")
    args = parser.parse_args()
    app = args.app.resolve(strict=True)
    manifest_path = app.with_name("HEPLab.Web.staticwebassets.endpoints.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset_sources = {}
    for endpoint in manifest["Endpoints"]:
        if endpoint["Selectors"]:
            continue
        properties = {item["Name"]: item["Value"] for item in endpoint["EndpointProperties"]}
        asset_sources["/" + endpoint["Route"]] = "/" + properties.get(
            "label", endpoint["AssetFile"]
        )
    content_root = (args.content_root or app.parent).resolve(strict=True)
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "ASPNETCORE_ENVIRONMENT": "Production",
        "DOTNET_ENVIRONMENT": "Production",
    }
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            ["dotnet", str(app), "--urls", base, "--contentRoot", str(content_root)],
            cwd=content_root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"site exited during startup: {process.returncode}")
                try:
                    fetch(base + "/")
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("site did not start within 30 seconds") from None
                    time.sleep(0.1)
            pages, assets = check(base, asset_sources)
            print(
                f"Production runtime passed: {pages} pages, {assets} assets with exact "
                f"source bytes and MIME types (identity + gzip), and search JSON; {app}."
            )
        except Exception:
            log.seek(0)
            print(log.read().decode("utf-8", errors="replace"))
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
