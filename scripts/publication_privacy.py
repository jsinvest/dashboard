"""Remove local home paths from published copies, including ZIP members.

Source collectors and original evidence are never changed. Source validation
hashes still describe the original evidence; public copies have separate hashes.
Run --apply before staging a release, or --check as a publication gate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import pathlib
import re
import subprocess
import zipfile

HOME_PATH = re.compile(r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+[^\\/]+[\\/]|/Users/[^/]+/|/home/[^/]+/)")
WINDOWS_HOME = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/]+[\\/]")
TEXT_SUFFIXES = {'.json', '.html', '.md', '.csv', '.txt', '.xml', '.js', '.cjs', '.py', '.yml', '.yaml', '.css'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_alias(value):
    normalized = value.replace('\\', '/')
    name = normalized.rstrip('/').rsplit('/', 1)[-1]
    return 'source-file://' + digest(value.encode())[:16] + '/' + name


def redact_string(value):
    # URLs with a /home/ route are ordinary public links, not local files.
    if re.match(r'^https?://', value, re.I):
        return value
    if HOME_PATH.match(value):
        return source_alias(value)
    # Embedded paths occur in Markdown explanations and exported HTML.
    pattern = r'''(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/]+[\\/][^\r\n"'<>|]*'''
    return re.sub(pattern, lambda m: source_alias(m.group(0).rstrip()), value)


def redact_json(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            new_key = redact_string(key)
            if new_key in result:
                raise ValueError('Redaction would merge distinct source keys')
            result[new_key] = redact_json(child)
        return result
    if isinstance(value, list):
        return [redact_json(child) for child in value]
    return redact_string(value) if isinstance(value, str) else value


def transform_text(name, raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw
    if pathlib.PurePosixPath(name).suffix.lower() == '.json':
        value = json.loads(text)
        clean = redact_json(value)
        if clean == value:
            return raw
        return (json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    if pathlib.PurePosixPath(name).suffix.lower() == '.csv':
        rows = list(csv.reader(io.StringIO(text)))
        clean = [[redact_string(cell) for cell in row] for row in rows]
        if clean == rows:
            return raw
        output = io.StringIO(newline='')
        csv.writer(output, lineterminator='\n').writerows(clean)
        return output.getvalue().encode()
    # Runtime code must use home-directory APIs rather than broken aliases.
    if pathlib.PurePosixPath(name).suffix.lower() in {'.py', '.js', '.cjs'}:
        return raw
    if not WINDOWS_HOME.search(text):
        return raw
    return redact_string(text).encode()


def transform_zip(raw):
    output = io.BytesIO()
    changes = []
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        entries = []
        for info in original.infolist():
            data = original.read(info)
            clean = transform_text(info.filename, data) if pathlib.PurePosixPath(info.filename).suffix.lower() in TEXT_SUFFIXES else data
            if clean != data:
                changes.append({'file': info.filename, 'original_sha256': digest(data), 'public_sha256': digest(clean)})
            entries.append((info, clean))
        if not changes:
            return raw
        # Validate the upstream originals separately from the redacted exports.
        privacy = {'schema_version': 1, 'scope': 'Published copies only; local source paths removed.',
                   'source_validation_scope': 'Existing producer hashes and validation results refer to original upstream files.',
                   'redacted_files': changes}
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as new:
            for info, data in entries:
                new.writestr(info, data)
            new.writestr('PUBLIC_PRIVACY_MANIFEST.json', json.dumps(privacy, ensure_ascii=False, indent=2) + '\n')
    return output.getvalue()


def leaks(name, raw):
    suffix = pathlib.PurePosixPath(name).suffix.lower()
    if suffix == '.zip':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return [name + '!' + item.filename for item in archive.infolist()
                    if pathlib.PurePosixPath(item.filename).suffix.lower() in TEXT_SUFFIXES
                    and leaks(item.filename, archive.read(item))]
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return []
    # Absolute Windows homes must never be present. Unix routes are checked
    # only as whole JSON values to avoid false positives in public news links.
    found = bool(WINDOWS_HOME.search(text))
    if suffix == '.json':
        def visit(value):
            if isinstance(value, dict):
                return any(visit(k) or visit(v) for k, v in value.items())
            if isinstance(value, list):
                return any(visit(v) for v in value)
            return isinstance(value, str) and bool(HOME_PATH.match(value))
        found = found or visit(json.loads(text))
    return [name] if found else []


def run(root, apply=False):
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    changed, remaining = [], []
    for name in paths:
        if not name or not (root / name).is_file():
            continue
        suffix = pathlib.PurePosixPath(name).suffix.lower()
        if suffix not in TEXT_SUFFIXES and suffix != '.zip':
            continue
        path = root / name
        raw = path.read_bytes()
        clean = transform_zip(raw) if suffix == '.zip' else transform_text(name, raw)
        if clean != raw:
            changed.append({'file': name, 'original_sha256': digest(raw), 'public_sha256': digest(clean)})
            if apply:
                path.write_bytes(clean)
        remaining.extend(leaks(name, clean if apply else raw))
    return {'changed': changed, 'remaining': remaining}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=pathlib.Path)
    args = parser.parse_args()
    result = run(args.root, args.apply)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'changed_files': len(result['changed']), 'remaining': result['remaining']}, ensure_ascii=False))
    raise SystemExit(1 if result['remaining'] else 0)
