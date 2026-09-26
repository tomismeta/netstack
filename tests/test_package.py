"""Offline package boundaries and exact reviewed-commit exports; no live snapshots."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "maintenance"))
import netstack_package as integrity
import package as packaging


def small_package():
    files = {path: (path + "\n").encode() for path in integrity.REQUIRED}
    files["assets/example.json"] = b'{"synthetic": true}\n'
    files["references/example.md"] = b"# Synthetic example\n"
    files[integrity.MANIFEST] = integrity.manifest_bytes(integrity.build_manifest(files, "0.4.0"))
    return files


def write_files(root, files):
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


class ManifestBoundaries(unittest.TestCase):
    def setUp(self):
        self.files = small_package()

    def replace_manifest(self, manifest):
        files = dict(self.files)
        files[integrity.MANIFEST] = integrity.manifest_bytes(manifest)
        return files

    def test_digest_keeps_original_sorted_path_nul_scope(self):
        report = integrity.verify_files(self.files)
        runtime = sorted(path for path in self.files if path == "SKILL.md"
                         or path.startswith(("assets/", "references/", "scripts/")))
        expected = hashlib.sha256(b"".join(path.encode() + b"\0" + self.files[path]
                                           for path in runtime)).hexdigest()
        self.assertEqual(report["runtime_sha256"], expected)
        self.assertEqual(report["manifest_sha256"], hashlib.sha256(self.files[integrity.MANIFEST]).hexdigest())
        files = dict(self.files, **{"README.md": b"different root readme", "LICENSE": b"different root license"})
        changed = integrity.build_manifest(files, "0.4.0")
        self.assertEqual(changed["runtime_bundle"]["sha256"], expected)
        with self.assertRaises(ValueError):
            integrity.verify_files(files)

    def test_tampered_missing_and_extra_members_fail(self):
        for operation in ("tampered", "missing", "extra"):
            with self.subTest(operation=operation):
                files = dict(self.files)
                if operation == "tampered":
                    files["assets/example.json"] = b"{}"
                elif operation == "missing":
                    del files["assets/example.json"]
                else:
                    files["assets/extra.json"] = b"{}"
                with self.assertRaises(ValueError):
                    integrity.verify_files(files)

    def test_manifest_counts_schema_hashes_and_scope_are_enforced(self):
        original = json.loads(self.files[integrity.MANIFEST])
        mutations = [lambda m: m.update(files=m["files"] + 1),
                     lambda m: m.update(total_distributable_files=True),
                     lambda m: m.update(skill="other"),
                     lambda m: m.update(unexpected=1),
                     lambda m: m.update(version=4),
                     lambda m: m["runtime_bundle"].update(files=True),
                     lambda m: m["runtime_bundle"].update(sha256="0" * 64),
                     lambda m: m["runtime_bundle"].update(scope="all files"),
                     lambda m: m["runtime_bundle"].update(digest_algorithm="SHA-1"),
                     lambda m: m["manifest_sha256"].update({"LICENSE": "not a digest"}),
                     lambda m: m["manifest_sha256"].update({integrity.MANIFEST: "0" * 64})]
        for mutate in mutations:
            manifest = deepcopy(original)
            mutate(manifest)
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    integrity.verify_files(self.replace_manifest(manifest))

    def test_duplicate_manifest_keys_fail_even_if_last_value_is_valid(self):
        for key in (b'"skill": "netstack"', b'"LICENSE": '):
            files = dict(self.files)
            if key.startswith(b'"skill"'):
                files[integrity.MANIFEST] = files[integrity.MANIFEST].replace(key, b'"skill":"other",' + key, 1)
            else:
                files[integrity.MANIFEST] = files[integrity.MANIFEST].replace(key, b'"LICENSE":"' + b"0" * 64 + b'",' + key, 1)
            with self.assertRaises(ValueError):
                integrity.verify_files(files)

    def test_unsafe_paths_aliases_and_repository_members_fail(self):
        unsafe = ["../escape", "/absolute", "assets/../escape", "assets//empty", "assets/./same",
                  "assets\\outside", "assets/stream:alias", "assets/trailing.", "assets/CON.txt",
                  "assets/caf\u00e9.json", "assets/line\nbreak", "assets/" + "x" * 256,
                  "assets/" + "/".join(["nested"] * 8), "tests/test_secret.py", ".omp/config.yml"]
        for path in unsafe:
            with self.subTest(path=path):
                files = dict(self.files)
                files[path] = b"unexpected"
                with self.assertRaises(ValueError):
                    integrity.build_manifest(files, "0.4.0")
        for addition in ({"assets/Example.json": b"case alias"},
                         {"assets/Folder/a.json": b"{}", "assets/folder/b.json": b"{}"},
                         {"assets/example.json/child": b"file-directory conflict"}):
            with self.subTest(addition=addition):
                with self.assertRaises(ValueError):
                    integrity.build_manifest({**self.files, **addition}, "0.4.0")

    def test_per_file_total_member_and_json_limits_fail_closed(self):
        files = dict(self.files, **{"assets/large.txt": b"x" * (integrity.MAX_FILE_BYTES + 1)})
        with self.assertRaises(ValueError):
            integrity.build_manifest(files, "0.4.0")
        with patch.object(integrity, "MAX_TOTAL_BYTES", 10):
            with self.assertRaises(ValueError):
                integrity.verify_files(self.files)
        with patch.object(integrity, "MAX_FILES", len(self.files) - 1):
            with self.assertRaises(ValueError):
                integrity.verify_files(self.files)
        for raw in (b'{"x":1,"x":2}', b"NaN", b"1e999", b"9" * 129,
                    b"[" * 33 + b"0" + b"]" * 33, b'"\xff"'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    integrity.loads_json_bytes(raw)


class FilesystemBoundaries(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent / "netstack"
        self.root.mkdir()
        self.files = small_package()
        write_files(self.root, self.files)

    def test_checkout_ignores_repository_artifacts_but_installed_rejects_them(self):
        for name in (".git", ".omp", ".github", "tests", "maintenance", "handoffs"):
            (self.root / name).mkdir()
            (self.root / name / "local-only").write_bytes(b"never distribute")
        (self.root / "netstack-handoff.md").write_bytes(b"local handoff")
        (self.root / "scripts/__pycache__").mkdir()
        (self.root / "scripts/__pycache__/cache.pyc").write_bytes(b"not runtime")
        self.assertEqual(integrity.read_package(self.root, checkout=True), self.files)
        with self.assertRaises(ValueError):
            integrity.read_package(self.root)

    def test_installed_empty_directory_and_unlisted_file_fail(self):
        (self.root / "assets/empty").mkdir()
        with self.assertRaises(ValueError):
            integrity.read_package(self.root)
        (self.root / "assets/empty").rmdir()
        (self.root / "assets/extra.txt").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            integrity.verify_files(integrity.read_package(self.root))

    def test_symlinked_root_ancestor_file_and_directory_fail(self):
        alias = self.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        for root in (alias, alias / "assets"):
            with self.subTest(root=root):
                with self.assertRaises((OSError, ValueError)):
                    integrity.read_package(root)
        victim = self.root / "assets/example.json"
        victim.unlink()
        victim.symlink_to(self.root / "README.md")
        with self.assertRaises((OSError, ValueError)):
            integrity.read_package(self.root)
        victim.unlink()
        victim.write_bytes(self.files["assets/example.json"])
        (self.root / "assets/linked").symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            integrity.read_package(self.root)

    def test_fifo_hardlink_and_sparse_oversized_file_fail_without_reading(self):
        victim = self.root / "assets/example.json"
        victim.unlink()
        os.mkfifo(victim)
        with self.assertRaises(ValueError):
            integrity.read_package(self.root)
        victim.unlink()
        os.link(self.root / "README.md", victim)
        with self.assertRaises(ValueError):
            integrity.read_package(self.root)
        victim.unlink()
        with victim.open("wb") as stream:
            stream.truncate(integrity.MAX_FILE_BYTES + 1)
        with self.assertRaises(ValueError):
            integrity.read_package(self.root)

    def test_installed_cli_verifies_without_loading_analytics_and_never_repairs(self):
        files = dict(self.files)
        for path in ("scripts/verify.py", "scripts/netstack_package.py"):
            files[path] = (ROOT / path).read_bytes()
        files["scripts/analytics.py"] = b"raise RuntimeError('analytics must not run')\n"
        files[integrity.MANIFEST] = integrity.manifest_bytes(integrity.build_manifest(files, "0.4.0"))
        write_files(self.root, files)
        command = [sys.executable, "-I", "-B", str(self.root / "scripts/verify.py")]
        result = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["runtime_sha256"], json.loads(files[integrity.MANIFEST])["runtime_bundle"]["sha256"])
        (self.root / "assets/example.json").write_bytes(b"tampered")
        result = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertEqual((self.root / integrity.MANIFEST).read_bytes(), files[integrity.MANIFEST])
        self.assertFalse((self.root / "scripts/__pycache__").exists())


class ReviewedCommitExports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = integrity.read_package(ROOT, checkout=True, include_manifest=False)
        cls.version = packaging.verify_content(cls.source)["version"]
        # git archive would expand this marker; our export must preserve the blob.
        cls.source["README.md"] += b"\nSynthetic archive probe: $Format:%H$\n"
        cls.source[integrity.MANIFEST] = integrity.manifest_bytes(integrity.build_manifest(cls.source, cls.version))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent / "reviewed"
        self.root.mkdir()
        write_files(self.root, self.source)
        write_files(self.root, {".gitattributes": b"README.md export-subst\n", "tests/secret.txt": b"repository only\n",
                               ".github/workflows/test.yml": b"not runtime\n", "netstack-handoff.md": b"private notes\n"})
        self.git("init", "-q")
        self.commit = self.commit_files()

    def git(self, *arguments):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                           GIT_AUTHOR_NAME="Synthetic Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                           GIT_COMMITTER_NAME="Synthetic Test", GIT_COMMITTER_EMAIL="test@example.invalid")
        return subprocess.run(["git", "-C", str(self.root), "-c", "core.hooksPath=" + os.devnull,
                               "-c", "commit.gpgsign=false", *arguments], check=True, capture_output=True,
                              env=environment, timeout=10).stdout

    def commit_files(self):
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic package fixture")
        return self.git("rev-parse", "HEAD").decode().strip()

    def test_export_uses_reviewed_blobs_despite_dirty_worktree_and_attributes(self):
        (self.root / "README.md").write_bytes(b"dirty worktree must not ship")
        (self.root / "scripts/analytics.py").unlink()
        (self.root / "assets/untracked.txt").write_bytes(b"untracked must not ship")
        output = self.parent / "installed"
        report = packaging.export_package(self.root, self.commit, output)
        self.assertEqual(report["commit"], self.commit)
        self.assertEqual(integrity.read_package(output), self.source)
        self.assertEqual(integrity.verify_files(integrity.read_package(output))["manifest_sha256"], report["manifest_sha256"])
        self.assertFalse((output / "tests").exists())

    def test_export_receipt_binds_reviewed_commit_and_exact_installed_bytes(self):
        output = self.parent / "installed"
        report = packaging.export_package(self.root, self.commit, output)
        receipt_path = self.parent / "installed.receipt.json"
        self.assertEqual(report["receipt"], str(receipt_path))
        receipt = json.loads(receipt_path.read_bytes())
        self.assertEqual(receipt["status"], "exported")
        self.assertEqual(receipt["commit"], self.commit)
        self.assertEqual(receipt["version"], self.version)
        self.assertEqual(receipt["output"], str(output))
        self.assertEqual(receipt["manifest_sha256"],
                         hashlib.sha256((output / integrity.MANIFEST).read_bytes()).hexdigest())
        runtime = sorted(path for path in self.source if path == "SKILL.md"
                         or path.startswith(("assets/", "references/", "scripts/")))
        digest = hashlib.sha256(b"".join(path.encode() + b"\0" + (output / path).read_bytes()
                                        for path in runtime)).hexdigest()
        self.assertEqual(receipt["runtime_sha256"], digest)
        self.assertEqual(integrity.read_package(output), self.source)

    def test_existing_receipt_file_directory_and_symlinks_refuse_export(self):
        output = self.parent / "installed"
        receipt = self.parent / "installed.receipt.json"
        victim = self.parent / "keep"
        victim.write_bytes(b"preserve")
        for kind in ("file", "directory", "symlink", "dangling"):
            with self.subTest(kind=kind):
                if kind == "file":
                    receipt.write_bytes(b"old receipt")
                elif kind == "directory":
                    receipt.mkdir()
                else:
                    receipt.symlink_to(victim if kind == "symlink" else self.parent / "absent")
                with self.assertRaises(FileExistsError):
                    packaging.export_package(self.root, self.commit, output)
                self.assertFalse(output.exists())
                self.assertEqual(victim.read_bytes(), b"preserve")
                if kind == "file":
                    self.assertEqual(receipt.read_bytes(), b"old receipt")
                elif kind in {"symlink", "dangling"}:
                    self.assertTrue(receipt.is_symlink())
                if kind == "directory":
                    receipt.rmdir()
                else:
                    receipt.unlink()
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()), ["keep", "reviewed"])

    def test_receipt_publication_race_preserves_competing_symlink_and_cleans_export(self):
        output = self.parent / "installed"
        receipt = self.parent / "installed.receipt.json"
        victim = self.parent / "keep"
        victim.write_bytes(b"preserve")
        original = packaging._write_file

        def competing_receipt(directory, name, raw):
            original(directory, name, raw)
            if name.startswith(".netstack-receipt-"):
                receipt.symlink_to(victim)

        with patch.object(packaging, "_write_file", side_effect=competing_receipt):
            with self.assertRaises(FileExistsError):
                packaging.export_package(self.root, self.commit, output)
        self.assertFalse(output.exists())
        self.assertTrue(receipt.is_symlink())
        self.assertEqual(victim.read_bytes(), b"preserve")
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()),
                         ["installed.receipt.json", "keep", "reviewed"])

    def test_partial_receipt_write_removes_staging_and_export(self):
        output = self.parent / "installed"
        original = packaging._write_file

        def disk_failure(directory, name, raw):
            if name.startswith(".netstack-receipt-"):
                original(directory, name, raw[:100])
                raise OSError("synthetic partial receipt write failure")
            original(directory, name, raw)

        with patch.object(packaging, "_write_file", side_effect=disk_failure):
            with self.assertRaises(OSError):
                packaging.export_package(self.root, self.commit, output)
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()), ["reviewed"])

    def test_archives_are_exact_sorted_normalized_and_worktree_independent(self):
        first, second = self.parent / "one.zip", self.parent / "two.zip"
        packaging.archive_package(self.root, self.commit, first)
        (self.root / "README.md").write_bytes(b"dirty archive input must be ignored")
        packaging.archive_package(self.root, self.commit, second)
        raw = first.read_bytes()
        self.assertEqual(raw, second.read_bytes())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(archive.namelist(), ["netstack/" + path for path in sorted(self.source)])
            extracted = {member.filename.removeprefix("netstack/"): archive.read(member) for member in archive.infolist()}
            self.assertEqual(extracted, self.source)
            for member in archive.infolist():
                self.assertEqual(member.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(member.create_system, 3)
                self.assertEqual(member.external_attr >> 16, stat.S_IFREG | 0o644)
                self.assertEqual(member.extra, b"")

    def test_existing_outputs_bad_commit_and_symlink_ancestors_are_not_overwritten(self):
        existing = self.parent / "existing"
        existing.mkdir()
        (existing / "keep").write_bytes(b"preserve")
        existing_zip = self.parent / "existing.zip"
        existing_zip.write_bytes(b"preserve zip")
        for action, output in ((packaging.export_package, existing), (packaging.archive_package, existing_zip)):
            with self.assertRaises(FileExistsError):
                action(self.root, self.commit, output)
        self.assertEqual((existing / "keep").read_bytes(), b"preserve")
        self.assertEqual(existing_zip.read_bytes(), b"preserve zip")
        for commit in (self.commit[:12], "0" * 40):
            for action in (packaging.export_package, packaging.archive_package):
                with self.assertRaises(ValueError):
                    action(self.root, commit, self.parent / "absent")
                self.assertFalse((self.parent / "absent").exists())
        alias = self.parent / "alias"
        alias.symlink_to(existing, target_is_directory=True)
        for action in (packaging.export_package, packaging.archive_package):
            with self.assertRaises((ValueError, OSError)):
                action(self.root, self.commit, alias / "absent")
        self.assertEqual(sorted(path.name for path in existing.iterdir()), ["keep"])

    def test_bad_committed_hash_or_symlink_cannot_produce_output(self):
        (self.root / "README.md").write_bytes(b"committed without updating manifest")
        commit = self.commit_files()
        for action in (packaging.export_package, packaging.archive_package):
            with self.assertRaises(ValueError):
                action(self.root, commit, self.parent / "absent")
            self.assertFalse((self.parent / "absent").exists())
        path = self.root / "README.md"
        path.unlink()
        path.symlink_to(self.root / "SKILL.md")
        commit = self.commit_files()
        with self.assertRaises(ValueError):
            packaging.export_package(self.root, commit, self.parent / "absent")
        self.assertFalse((self.parent / "absent").exists())

    def test_content_errors_fail_all_maintenance_actions_even_with_matching_hashes(self):
        files = dict(self.source)
        sources = json.loads(files["assets/sources.json"])
        sources["sources"].append(deepcopy(sources["sources"][0]))
        files["assets/sources.json"] = (json.dumps(sources) + "\n").encode()
        files[integrity.MANIFEST] = integrity.manifest_bytes(integrity.build_manifest(files, self.version))
        write_files(self.root, files)
        commit = self.commit_files()
        before = (self.root / integrity.MANIFEST).read_bytes()
        with self.assertRaises(ValueError):
            packaging.verify_package(files)
        with self.assertRaises(ValueError):
            packaging.build_package(self.root)
        self.assertEqual((self.root / integrity.MANIFEST).read_bytes(), before)
        for action in (packaging.export_package, packaging.archive_package):
            with self.assertRaises(ValueError):
                action(self.root, commit, self.parent / "absent")
            self.assertFalse((self.parent / "absent").exists())

    def test_failed_export_write_removes_partial_destination(self):
        output = self.parent / "incomplete"
        original = packaging._write_file

        def disk_failure(directory, name, raw):
            if name == "SKILL.md":
                self.assertTrue((self.parent / "incomplete.receipt.json").is_file())
                raise OSError("synthetic disk failure before discovery")
            original(directory, name, raw)

        with patch.object(packaging, "_write_file", side_effect=disk_failure):
            with self.assertRaises(OSError):
                packaging.export_package(self.root, self.commit, output)
        self.assertFalse(output.exists())
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()), ["reviewed"])

    def test_failed_archive_write_removes_staging_and_never_claims_destination(self):
        output = self.parent / "incomplete.zip"
        original = packaging._write_file

        def disk_failure(directory, name, raw):
            original(directory, name, raw[:100])
            raise OSError("synthetic archive write failure")

        with patch.object(packaging, "_write_file", side_effect=disk_failure):
            with self.assertRaises(OSError):
                packaging.archive_package(self.root, self.commit, output)
        self.assertFalse(output.exists())
        self.assertEqual(sorted(path.name for path in self.parent.iterdir()), ["reviewed"])


if __name__ == "__main__":
    unittest.main()
