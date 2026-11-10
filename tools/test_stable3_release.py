from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from stable3_release import build_bundle


class Stable3BundleTests(unittest.TestCase):
    def test_bundle_contains_tk_shell_qt_host_and_stable_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / "program"
            host = program / "Graphics2Host" / "_internal" / "srstudio" / "graphics2" / "qml"
            host.mkdir(parents=True)
            (program / "SR Studio 5.exe").write_bytes(b"shell")
            (program / "Graphics2Host" / "SRGraphicsEngine2Host.exe").write_bytes(b"host")
            (host / "GraphicsEditor.qml").write_text("ApplicationWindow {}", encoding="utf-8")
            previous = root / "previous.json"
            previous.write_text(json.dumps({"channel": "stable", "version": "5.0.0-hybrid.stable2",
                                            "min_launcher": "4.0.1-hybrid.base3.4", "delete": ["old.js"]}))
            archive = root / "stable3.zip"
            output = root / "stable3-manifest.json"

            manifest = build_bundle(program, archive, previous, output, "a" * 40)

            with ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                self.assertIn("files/SRStudio5/SR Studio 5.exe", names)
                self.assertIn("files/SRStudio5/Graphics2Host/SRGraphicsEngine2Host.exe", names)
                self.assertIn("files/SR_Studio_Gerador.py", names)
                identity = json.loads(bundle.read("files/version.json"))
                self.assertEqual(identity["channel"], "stable")
                self.assertEqual(identity["version"], "5.0.0-hybrid.stable3")
            self.assertEqual(manifest["promoted_from"], "5.0.0-hybrid.g2beta.65")
            self.assertEqual(manifest["source_commit"], "a" * 40)
            self.assertEqual(manifest["delete"], ["old.js"])
            self.assertEqual(json.loads(output.read_text())["sha256"], manifest["sha256"])

    def test_refuses_incomplete_host_or_unexpected_previous_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / "program"
            program.mkdir()
            (program / "SR Studio 5.exe").write_bytes(b"shell")
            previous = root / "previous.json"
            previous.write_text(json.dumps({"channel": "stable", "version": "5.0.0-hybrid.stable2"}))
            with self.assertRaisesRegex(ValueError, "Graphics2Host"):
                build_bundle(program, root / "stable3.zip", previous, root / "manifest.json", "b" * 40)
            (program / "Graphics2Host").mkdir()
            (program / "Graphics2Host" / "SRGraphicsEngine2Host.exe").write_bytes(b"host")
            (program / "Graphics2Host" / "_internal" / "srstudio" / "graphics2" / "qml").mkdir(parents=True)
            (program / "Graphics2Host" / "_internal" / "srstudio" / "graphics2" / "qml" / "GraphicsEditor.qml").write_text("x")
            previous.write_text(json.dumps({"channel": "stable", "version": "5.0.0-hybrid.stable1"}))
            with self.assertRaisesRegex(ValueError, "stable2"):
                build_bundle(program, root / "stable3.zip", previous, root / "manifest.json", "b" * 40)
