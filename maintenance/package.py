#!/usr/bin/env python3
"""Build/verify a checkout or export/archive a reviewed HEAD, entirely offline."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time
import uuid
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from netstack_package import (MANIFEST, MAX_FILE_BYTES, MAX_FILES, MAX_MANIFEST_BYTES, MAX_TOTAL_BYTES,
                              build_manifest, manifest_bytes, open_directory, read_package,
                              repository_only, runtime_path, validate_files, verify_files)
from content import verify_content

GIT_TIMEOUT = 30
MAX_TREE_BYTES = 1024 * 1024


def _git(root, *arguments, limit=MAX_TREE_BYTES):
    """Bound Git's stdout and duration; never execute filters, hooks or network commands."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    command = ["git", "--no-replace-objects", "-C", str(root), "-c", "core.fsmonitor=false",
               "-c", "core.hooksPath=" + os.devnull, *arguments]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment) as child:
        chunks, size = [], 0
        deadline = time.monotonic() + GIT_TIMEOUT
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError("Git read exceeded time limit")
                    chunk = os.read(child.stdout.fileno(), min(65536, limit + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Git output exceeds byte limit")
                    chunks.append(chunk)
            child.wait(timeout=max(0.001, deadline - time.monotonic()))
            if child.returncode:
                raise ValueError("Git could not read the requested repository object")
            return b"".join(chunks)
        except BaseException:
            child.kill()
            child.wait()
            raise


def reviewed_head(root, commit):
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("a reviewed full 40-hex commit is required")
    descriptor = open_directory(root)
    os.close(descriptor)
    top = os.fsdecode(_git(root, "rev-parse", "--show-toplevel", limit=4096)).rstrip("\n")
    if Path(top) != Path(root).absolute():
        raise ValueError("package root must be the Git checkout root")
    if _git(root, "rev-parse", "--verify", "HEAD", limit=128).strip().decode("ascii") != commit.lower():
        raise ValueError("HEAD does not match the supplied reviewed commit")
    if _git(root, "cat-file", "-t", commit, limit=64).strip() != b"commit":
        raise ValueError("reviewed object is not a commit")


def committed_files(root, commit):
    """Read exact blob bytes, not a worktree or git-archive/export-subst representation."""
    reviewed_head(root, commit)
    entries, total = {}, 0
    tree = _git(root, "ls-tree", "-rzl", "--full-tree", commit)
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if repository_only(path):
            continue
        if not runtime_path(path):
            raise ValueError(f"non-runtime committed path: {path}")
        mode, kind, object_id, size = metadata.split()
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise ValueError(f"nonregular committed package file: {path}")
        cap = MAX_MANIFEST_BYTES if path == MANIFEST else MAX_FILE_BYTES
        if not size.isdigit() or len(size) > 12 or int(size) > cap:
            raise ValueError(f"oversized committed file: {path}")
        if path in entries or len(entries) >= MAX_FILES:
            raise ValueError("duplicate or excessive committed package members")
        if not re.fullmatch(rb"[0-9a-f]{40}", object_id):
            raise ValueError("unsupported Git object identity")
        total += int(size)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("committed package exceeds total byte limit")
        entries[path] = (object_id.decode("ascii"), int(size))
    files = {}
    for path, (object_id, size) in entries.items():
        raw = _git(root, "cat-file", "blob", object_id, limit=size)
        if len(raw) != size:
            raise ValueError(f"incomplete committed file: {path}")
        files[path] = raw
    validate_files(files)
    return files


def verify_package(files):
    report = verify_files(files)
    content = verify_content(files)
    if content["version"] != report["version"]:
        raise ValueError("manifest version does not match SKILL.md")
    report["content"] = content
    return report


def _write_file(directory, name, raw):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(descriptor, 0o644)
    finally:
        os.close(descriptor)


def build_package(root):
    files = read_package(root, checkout=True, include_manifest=False)
    content = verify_content(files)
    raw = manifest_bytes(build_manifest(files, content["version"]))
    files[MANIFEST] = raw
    report = verify_files(files)
    report["content"] = content
    directory = open_directory(root)
    temporary = ".netstack-manifest-" + uuid.uuid4().hex
    try:
        try:
            before = os.stat(MANIFEST, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            before = None
        if before is not None and (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1):
            raise ValueError("manifest destination must be a single-link regular file")
        _write_file(directory, temporary, raw)
        os.replace(temporary, MANIFEST, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)
    report["status"] = "built"
    return report


def _destination(output):
    spelling = os.fspath(output)
    if ".." in spelling.split(os.sep):
        raise ValueError("destination must not contain parent traversal")
    destination = Path(spelling).absolute()
    if destination.name in {"", ".", ".."}:
        raise ValueError("destination must have a new name")
    parent = open_directory(destination.parent)
    try:
        try:
            os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return destination, parent
        raise FileExistsError("destination already exists: " + str(destination))
    except BaseException:
        os.close(parent)
        raise


def _remove_contents(directory):
    """Remove only our exclusively created tree, without following substituted links."""
    with os.scandir(directory) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    _remove_contents(child)
                finally:
                    os.close(child)
                os.rmdir(entry.name, dir_fd=directory)
            else:
                os.unlink(entry.name, dir_fd=directory)


def export_package(root, commit, output):
    files = committed_files(root, commit)
    report = verify_package(files)
    destination, parent = _destination(output)
    receipt = destination.with_name(destination.name + ".receipt.json")
    temporary = ".netstack-receipt-" + uuid.uuid4().hex
    report.update(status="exported", commit=commit.lower(), output=str(destination),
                  receipt=str(receipt))
    identity = {key: report[key] for key in
                ("commit", "version", "manifest_sha256", "runtime_sha256", "note")}
    directory = None
    created = False
    receipt_created = False
    try:
        try:
            os.stat(receipt.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("receipt destination already exists: " + str(receipt))
        reviewed_head(root, commit)
        os.mkdir(destination.name, mode=0o700, dir_fd=parent)
        created = True
        directory = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        # Publish the complete receipt before SKILL.md makes the package discoverable.
        for path in sorted(files, key=lambda path: (path == "SKILL.md", path)):
            if path == "SKILL.md":
                raw = (json.dumps(identity, indent=2) + "\n").encode("utf-8")
                _write_file(parent, temporary, raw)
                os.link(temporary, receipt.name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
                receipt_created = True
                os.unlink(temporary, dir_fd=parent)
            descriptor = os.dup(directory)
            try:
                parts = path.split("/")
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = child
                _write_file(descriptor, parts[-1], files[path])
            finally:
                os.close(descriptor)
        os.fchmod(directory, 0o755)
    except BaseException:
        if receipt_created:
            os.unlink(receipt.name, dir_fd=parent)
        if directory is not None:
            _remove_contents(directory)
        if created:
            os.rmdir(destination.name, dir_fd=parent)
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return report


def archive_bytes(files):
    """Stable ZIP_STORED bytes across Python/zlib/platform versions; no clock or host metadata."""
    validate_files(files)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for path in sorted(files):
            member = zipfile.ZipInfo("netstack/" + path, date_time=(1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.create_version = 20
            member.extract_version = 20
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            member.compress_type = zipfile.ZIP_STORED
            member.flag_bits = 0
            member.internal_attr = 0
            member.extra = b""
            member.comment = b""
            archive.writestr(member, files[path])
    return buffer.getvalue()


def archive_package(root, commit, output):
    files = committed_files(root, commit)
    report = verify_package(files)
    raw = archive_bytes(files)
    destination, parent = _destination(output)
    temporary = ".netstack-archive-" + uuid.uuid4().hex
    try:
        _write_file(parent, temporary, raw)
        reviewed_head(root, commit)
        # A same-directory hard link publishes atomically and refuses any existing target.
        os.link(temporary, destination.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)
    report.update(status="archived", commit=commit.lower(), output=str(destination),
                  archive_sha256=hashlib.sha256(raw).hexdigest())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify", "export", "archive"))
    parser.add_argument("--root", type=Path, default=ROOT, help="Checkout root (default: this tool's checkout)")
    parser.add_argument("--commit", help="Reviewed full 40-hex commit; must equal HEAD")
    parser.add_argument("--output", type=Path, help="New destination; its real parent directory must exist")
    args = parser.parse_args(argv)
    if args.action in {"export", "archive"}:
        if args.commit is None or args.output is None:
            parser.error("export/archive require --commit and --output")
    elif args.commit is not None or args.output is not None:
        parser.error("--commit and --output are only valid for export/archive")
    try:
        if args.action == "build":
            report = build_package(args.root)
        elif args.action == "verify":
            report = verify_package(read_package(args.root, checkout=True))
        elif args.action == "export":
            report = export_package(args.root, args.commit, args.output)
        else:
            report = archive_package(args.root, args.commit, args.output)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
