"""Validate an existing read-only bridge and optionally refresh its public URL.

This tool never starts a server, collector or tunnel, and never publishes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SyncError(ValueError):
    pass


def public_url(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com/?", value
    ):
        raise SyncError("INVALID_PUBLIC_URL")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    request = Request(url, headers={"Cache-Control": "no-cache"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            data = response.read(262145)
            if len(data) > 262144:
                raise SyncError("RESPONSE_TOO_LARGE")
            return response.status, data
    except HTTPError as exc:
        return exc.code, b""
    except (URLError, OSError):
        raise SyncError("CONNECTION_CHECK_FAILED") from None


def validate_bridge(url, fetcher=fetch):
    checks = []
    status, body = fetcher(url + "/health")
    if status != 200:
        raise SyncError("HEALTH_HTTP_STATUS")
    try:
        health = json.loads(body)
    except (ValueError, TypeError, UnicodeError):
        raise SyncError("INVALID_HEALTH_JSON") from None
    if not isinstance(health, dict) or health.get("app") != "readonly-trading-viewer":
        raise SyncError("UNEXPECTED_BRIDGE_APP")
    checks.append({"path": "/health", "status": 200})
    for name in ("program", "investor", "cvd"):
        path = f"/{name}/"
        status, body = fetcher(url + path)
        if status != 200 or b"viewerPassword" not in body:
            raise SyncError("PASSWORD_PAGE_NOT_VERIFIED")
        checks.append({"path": path, "status": status})
        path = f"/{name}/api/state"
        status, _ = fetcher(url + path)
        if status != 401:
            raise SyncError("UNAUTHENTICATED_STATE_NOT_BLOCKED")
        checks.append({"path": path, "status": status})
    return checks


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def same_path(a, b):
    return (Path(a).resolve() == Path(b).resolve()
            or (Path(a).exists() and Path(b).exists() and os.path.samefile(a, b)))


def synchronize(root, bridge_public, *, apply=False, report=None, fetcher=fetch):
    manifest = Path(root) / "live-monitors" / "connection.json"
    bridge_public = Path(bridge_public)
    if report and any(same_path(report, source) for source in (manifest, bridge_public)):
        raise SyncError("REPORT_OVERLAPS_SOURCE")
    original = manifest.read_bytes()
    try:
        connection = json.loads(original.decode("utf-8-sig"))
        source = json.loads(bridge_public.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise SyncError("INVALID_INPUT_JSON") from None
    if (not isinstance(connection, dict) or connection.get("mode") != "readonly"
            or connection.get("authentication") != "server_password"):
        raise SyncError("UNSAFE_MANIFEST_MODE")
    if not isinstance(source, dict):
        raise SyncError("INVALID_BRIDGE_PUBLIC")
    url = public_url(source.get("url"))
    checks = validate_bridge(url, fetcher)
    changed = connection.get("url") not in (url, url + "/")
    result = {"status": "VALIDATED", "url": url, "change_required": changed,
              "applied": False, "checks": checks}
    replacement = None
    try:
        # Fail before editing the manifest if the requested report cannot be written.
        if report:
            atomic_bytes(report, encode(result))
        if apply and changed:
            if manifest.read_bytes() != original:
                raise SyncError("MANIFEST_CHANGED_DURING_CHECK")
            updated = dict(connection)
            updated.update(url=url, published_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
            replacement = encode(updated)
            atomic_bytes(manifest, replacement)
            result["applied"] = True
        if report:
            atomic_bytes(report, encode(result))
    except OSError:
        # Restore only our own bytes, preserving a concurrent owner's changes.
        if replacement is not None and manifest.read_bytes() == replacement:
            atomic_bytes(manifest, original)
        raise SyncError("FILE_WRITE_FAILED") from None
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bridge-public", type=Path,
                        default=Path.home() / "Desktop/restapi/live_dashboard_bridge/data/public.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = synchronize(args.root, args.bridge_public, apply=args.apply, report=args.report)
    except (SyncError, OSError, ValueError, TypeError):
        # Do not disclose filesystem paths, credentials or raw HTTP response bodies.
        import sys
        error = sys.exc_info()[1]
        result = {"status": "FAILED", "error": str(error) if isinstance(error, SyncError) else "INPUT_OR_IO_FAILED",
                  "applied": False}
        if args.report and not any(same_path(args.report, source) for source in (
                args.root / "live-monitors/connection.json", args.bridge_public)):
            try:
                atomic_bytes(args.report, encode(result))
            except OSError:
                pass
        print(json.dumps(result))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
