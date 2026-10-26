"""Minimal release-promotion contract tests; no network and no dependencies."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from promote_g2_beta48_launcher import prepare, safe_member


class LauncherPromotionTests(unittest.TestCase):
    def test_safe_archive_paths(self):
        for name in ("../evil.exe", "/absolute", "C:/windows", "a//b", "x/../../bad"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_member(name)
        self.assertEqual(safe_member("Graphics2Host\\runtime.exe"), "Graphics2Host/runtime.exe")

    def test_repack_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            with ZipFile(source, "w") as zipf:
                for item in (
                    "SR Studio 5.exe",
                    "Graphics2Host/SRGraphicsEngine2Host.exe",
                    "Graphics2Host/_internal/srstudio/graphics2/qml/GraphicsEditor.qml",
                    "Graphics2Host/_internal/test.dll",
                ):
                    zipf.writestr(item, item.encode())
            old = root / "manifest.json"
            old.write_text('{"channel":"beta","version":"5.0.0-hybrid.g2beta.47","min_launcher":"4.0.1-hybrid.base2.6"}')
            target = root / "launcher.zip"
            manifest_file = root / "beta48.json"
            data = prepare(source, target, old, manifest_file)
            self.assertEqual(data["version"], "5.0.0-hybrid.g2beta.48")
            self.assertEqual(data["bundle"]["member_prefix"], "files/")
            self.assertEqual(data["bundle"]["size"], target.stat().st_size)
            self.assertEqual(data["entrypoint"], "SRStudio5/SR Studio 5.exe")
            with ZipFile(target) as z:
                self.assertIn("files/SRStudio5/SR Studio 5.exe", z.namelist())
                self.assertIn("files/SRStudio5/Graphics2Host/SRGraphicsEngine2Host.exe", z.namelist())
                self.assertIn("files/version.json", z.namelist())

    def test_requires_complete_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            with ZipFile(source, "w") as zipf:
                zipf.writestr("SR Studio 5.exe", b"stub")
            manifest = root / "manifest.json"
            manifest.write_text('{"channel":"beta","version":"5.0.0-hybrid.g2beta.47"}')
            with self.assertRaises(ValueError):
                prepare(source, root / "launcher.zip", manifest, root / "beta48.json")


if __name__ == "__main__":
    unittest.main()
