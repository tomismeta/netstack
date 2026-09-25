"""Offline, bounded package integrity rules shared by installed and maintainer tools."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping

MANIFEST = "release-manifest.json"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 512
MAX_DIRECTORIES = 128
MAX_PATH_BYTES = 255
MAX_PATH_DEPTH = 8
MAX_JSON_DEPTH = 32
DIGEST_ALGORITHM = "SHA-256 over lexicographically sorted POSIX relative paths, each followed by NUL and file bytes"
RUNTIME_SCOPE = "SKILL.md, assets/**, references/** (including references/guardrail.md) and scripts/**; excludes README.md, root LICENSE, release-manifest.json and non-distributable maintenance/tests."
NOTE = "Integrity, not authenticity: independently review and pin the complete release and verifier."
ROOT_FILES = frozenset({"LICENSE", "README.md", "SKILL.md", MANIFEST})
RUNTIME_DIRS = frozenset({"assets", "references", "scripts"})
REPOSITORY_ROOTS = frozenset({".git", ".github", ".omp", "maintenance", "tests", "handoffs", "dist",
                              ".gitignore", ".gitattributes", "netstack-handoff.md"})
CACHE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"})
REQUIRED = frozenset({"LICENSE", "README.md", "SKILL.md", "assets/LICENSE.txt",
                      "scripts/analytics.py", "scripts/netstack_core.py", "scripts/netstack_package.py",
                      "scripts/verify.py"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?\Z")
_COMPONENT = re.compile(r"[A-Za-z0-9_.-]+\Z")
_RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z", re.I)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key[:120])
        result[key] = value
    return result


def _number(text):
    if len(text) > 128:
        raise ValueError("JSON number exceeds digit limit")
    value = float(text) if any(c in text for c in ".eE") else int(text)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite JSON number")
    return value


def _constant(text):
    raise ValueError("nonfinite JSON number: " + text)


def loads_json_bytes(raw, label="JSON"):
    """Strict UTF-8 JSON with bounded bytes, nesting and numbers; duplicate keys fail."""
    if not isinstance(raw, bytes) or len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"{label}: JSON exceeds byte limit or is not bytes")
    try:
        text = raw.decode("utf-8")
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "[{":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise ValueError("JSON nesting exceeds limit")
            elif character in "]}":
                depth -= 1
        return json.loads(text, object_pairs_hook=_pairs, parse_int=_number,
                          parse_float=_number, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{label}: {exc}") from exc


def validate_path(path):
    """Require one portable spelling, before any filesystem operation or classification."""
    if not isinstance(path, str) or not 1 <= len(path) <= MAX_PATH_BYTES:
        raise ValueError("invalid package path")
    parts = path.split("/")
    if (len(parts) > MAX_PATH_DEPTH or any(not _COMPONENT.fullmatch(part)
            or part in {".", ".."} or part.endswith(".") or _RESERVED.fullmatch(part) for part in parts)):
        raise ValueError(f"unsafe package path: {path!r}")
    return parts


def repository_only(path):
    parts = validate_path(path)
    return (parts[0] in REPOSITORY_ROOTS or any(part in CACHE_NAMES for part in parts)
            or parts[-1].endswith((".pyc", ".pyo")))


def runtime_path(path):
    parts = validate_path(path)
    if repository_only(path):
        return False
    if path in ROOT_FILES:
        return True
    if len(parts) > 1 and parts[0] in RUNTIME_DIRS and not any(part.startswith(".") for part in parts):
        return True
    raise ValueError(f"unexpected package path: {path}")


def _members(paths):
    if not 1 <= len(paths) <= MAX_FILES:
        raise ValueError("package file count exceeds limit or is empty")
    aliases, directories = {}, set()
    for path in paths:
        if not runtime_path(path):
            raise ValueError(f"repository-only member in package: {path}")
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            name = "/".join(parts[:index])
            alias = name.casefold()
            if alias in aliases and aliases[alias] != name:
                raise ValueError(f"case-aliased package paths: {aliases[alias]}, {name}")
            aliases[alias] = name
            if index < len(parts):
                directories.add(name)
    if directories.intersection(paths):
        raise ValueError("package path is both file and directory")
    if len(directories) > MAX_DIRECTORIES:
        raise ValueError("package directory count exceeds limit")
    if not REQUIRED <= set(paths):
        raise ValueError("missing required package files: " + ", ".join(sorted(REQUIRED - set(paths))))
    return directories


def validate_files(files):
    """Validate a complete path-to-bytes mapping, with an optional manifest."""
    if not isinstance(files, Mapping):
        raise ValueError("package must be a path-to-bytes mapping")
    directories = _members(files.keys())
    total = 0
    for path, raw in files.items():
        cap = MAX_MANIFEST_BYTES if path == MANIFEST else MAX_FILE_BYTES
        if not isinstance(raw, bytes) or len(raw) > cap:
            raise ValueError(f"non-byte or oversized package file: {path}")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("package exceeds total byte limit")
    return directories


def runtime_digest(files):
    """Hash sorted runtime path + NUL + bytes, excluding root license/readme/manifest."""
    digest = hashlib.sha256()
    count = 0
    for path in sorted(files):
        if path == "SKILL.md" or path.split("/", 1)[0] in RUNTIME_DIRS:
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[path])
            count += 1
    return count, digest.hexdigest()


def build_manifest(files, version):
    validate_files(files)
    if not isinstance(version, str) or len(version) > 64 or not _VERSION.fullmatch(version):
        raise ValueError("invalid package version")
    hashes = {path: hashlib.sha256(files[path]).hexdigest() for path in sorted(files) if path != MANIFEST}
    count, digest = runtime_digest(files)
    return {"skill": "netstack", "version": version, "files": len(hashes),
            "total_distributable_files": len(hashes) + 1, "manifest_sha256": hashes,
            "runtime_bundle": {"files": count, "sha256": digest,
                               "digest_algorithm": DIGEST_ALGORITHM, "scope": RUNTIME_SCOPE}}


def manifest_bytes(manifest):
    return (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def verify_files(files):
    """Verify exact membership, schema/counts, every file hash and the runtime digest."""
    validate_files(files)
    if MANIFEST not in files:
        raise ValueError("missing release-manifest.json")
    manifest = loads_json_bytes(files[MANIFEST], MANIFEST)
    keys = {"skill", "version", "files", "total_distributable_files", "manifest_sha256", "runtime_bundle"}
    if not isinstance(manifest, dict) or set(manifest) != keys or manifest["skill"] != "netstack":
        raise ValueError("unsupported manifest schema")
    hashes = manifest["manifest_sha256"]
    if not isinstance(hashes, dict) or MANIFEST in hashes:
        raise ValueError("invalid manifest membership")
    _members(hashes.keys())
    for path, digest in hashes.items():
        if not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise ValueError(f"invalid file hash: {path}")
    if set(files) != set(hashes) | {MANIFEST}:
        raise ValueError("manifest membership mismatch (missing or extra package file)")
    runtime = manifest["runtime_bundle"]
    if (not isinstance(runtime, dict) or set(runtime) != {"files", "sha256", "digest_algorithm", "scope"}
            or type(runtime["files"]) is not int or type(manifest["files"]) is not int
            or type(manifest["total_distributable_files"]) is not int):
        raise ValueError("invalid manifest counts or runtime schema")
    expected = build_manifest(files, manifest["version"])
    for path, digest in expected["manifest_sha256"].items():
        if hashes[path] != digest:
            raise ValueError(f"package file hash mismatch: {path}")
    if manifest != expected:
        raise ValueError("manifest count, runtime digest or scope mismatch")
    return {"status": "verified", "version": manifest["version"], "files": len(files),
            "bytes": sum(map(len, files.values())),
            "manifest_sha256": hashlib.sha256(files[MANIFEST]).hexdigest(),
            "runtime_sha256": runtime["sha256"], "note": NOTE}


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _directory(parent, name):
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError(f"not a real package directory: {name}")
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    if _identity(before) != _identity(os.fstat(descriptor)):
        os.close(descriptor)
        raise ValueError("package directory changed while opening")
    return descriptor


def open_directory(path):
    """Pin a directory, refusing symlinks in every ancestor (Linux/macOS only)."""
    if not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise ValueError("host lacks safe descriptor-relative file access")
    spelling = os.fspath(path)
    if not isinstance(spelling, str) or ".." in spelling.split(os.sep):
        raise ValueError("directory path must not contain parent traversal")
    absolute = os.path.abspath(spelling)
    descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in absolute.split(os.sep)[1:]:
            if not component:
                continue
            child = _directory(descriptor, component)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_regular(directory, name, limit):
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
        raise ValueError(f"nonregular, linked or oversized package file: {name}")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened):
            raise ValueError("package file changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if (len(raw) > limit or len(raw) != opened.st_size
                or _identity(opened) != _identity(os.fstat(descriptor))
                or _identity(opened) != _identity(os.stat(name, dir_fd=directory, follow_symlinks=False))):
            raise ValueError("package file changed while reading")
        return raw
    finally:
        os.close(descriptor)


def read_package(root, *, checkout=False, include_manifest=True):
    """Read bounded regular files without following links; installed extras always fail."""
    descriptor = open_directory(root)
    files, directories = {}, set()
    total, entries_seen = 0, 0

    def visit(directory, prefix):
        nonlocal total, entries_seen
        before = os.fstat(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > MAX_FILES + MAX_DIRECTORIES + 128:
                    raise ValueError("package entry count exceeds limit")
                path = prefix + entry.name
                if checkout and repository_only(path):
                    continue
                if path == MANIFEST and not include_manifest:
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    parts = validate_path(path)
                    if (parts[0] not in RUNTIME_DIRS or repository_only(path)
                            or any(part.startswith(".") for part in parts)):
                        raise ValueError(f"unexpected package directory: {path}")
                    directories.add(path)
                    if len(directories) > MAX_DIRECTORIES:
                        raise ValueError("package directory count exceeds limit")
                    child = _directory(directory, entry.name)
                    try:
                        visit(child, path + "/")
                    finally:
                        os.close(child)
                else:
                    if not runtime_path(path):
                        raise ValueError(f"repository-only member in installed package: {path}")
                    if len(files) >= MAX_FILES:
                        raise ValueError("package file count exceeds limit")
                    cap = MAX_MANIFEST_BYTES if path == MANIFEST else MAX_FILE_BYTES
                    raw = read_regular(directory, entry.name, min(cap, MAX_TOTAL_BYTES - total))
                    total += len(raw)
                    files[path] = raw
        if _identity(before) != _identity(os.fstat(directory)):
            raise ValueError("package directory changed during read")

    try:
        visit(descriptor, "")
        if directories != validate_files(files):
            raise ValueError("unexpected empty package directory")
        return files
    finally:
        os.close(descriptor)
