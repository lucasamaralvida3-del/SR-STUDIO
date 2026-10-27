"""Minimal release-promotion contract tests; no network and no dependencies."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from promote_g2_beta59_launcher import prepare, safe_member


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
                source_assets = Path(__file__).resolve().parents[1] / "src/srstudio/assets/campaigns"
                for image_path in source_assets.rglob("*"):
                    if image_path.is_file():
                        zipf.write(image_path,
                            "Graphics2Host/_internal/srstudio/assets/campaigns/"
                            + image_path.relative_to(source_assets).as_posix())
            old = root / "manifest.json"
            old.write_text('{"channel":"beta","version":"5.0.0-hybrid.g2beta.58","min_launcher":"4.0.1-hybrid.base2.6"}')
            target = root / "launcher.zip"
            manifest_file = root / "beta59.json"
            data = prepare(source, target, old, manifest_file)
            self.assertEqual(data["version"], "5.0.0-hybrid.g2beta.59")
            self.assertEqual(data["bundle"]["member_prefix"], "files/")
            self.assertIn("Beta 59", data["release_label"])
            self.assertEqual(data["bundle"]["size"], target.stat().st_size)
            self.assertEqual(data["entrypoint"], "SRStudio5/SR Studio 5.exe")
            with ZipFile(target) as z:
                self.assertIn("files/SRStudio5/SR Studio 5.exe", z.namelist())
                self.assertIn("files/SRStudio5/Graphics2Host/SRGraphicsEngine2Host.exe", z.namelist())
                self.assertIn("files/version.json", z.namelist())
                self.assertIn(
                    "files/SRStudio5/Graphics2Host/_internal/srstudio/assets/campaigns/catalog.json",
                    z.namelist())

    def test_missing_embedded_promotion_images_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incomplete.zip"
            with ZipFile(source, "w") as zipf:
                for name in (
                    "SR Studio 5.exe",
                    "Graphics2Host/SRGraphicsEngine2Host.exe",
                    "Graphics2Host/_internal/srstudio/graphics2/qml/GraphicsEditor.qml",
                    "Graphics2Host/_internal/srstudio/assets/campaigns/catalog.json",
                ):
                    zipf.writestr(name, "{}" if name.endswith(".json") else "stub")
            manifest = root / "old.json"
            manifest.write_text('{"channel":"beta","version":"5.0.0-hybrid.g2beta.58"}')
            with self.assertRaises(ValueError):
                prepare(source, root / "out.zip", manifest, root / "new.json")

    def test_requires_complete_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.zip"
            with ZipFile(source, "w") as zipf:
                zipf.writestr("SR Studio 5.exe", b"stub")
            manifest = root / "manifest.json"
            manifest.write_text('{"channel":"beta","version":"5.0.0-hybrid.g2beta.58"}')
            with self.assertRaises(ValueError):
                prepare(source, root / "launcher.zip", manifest, root / "beta59.json")


if __name__ == "__main__":
    unittest.main()
