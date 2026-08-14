from __future__ import annotations

import json
import py_compile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"
FOUNDATION = ROOT / "build" / "foundation.json"


class FoundationTests(unittest.TestCase):
    def test_foundation_metadata(self):
        data = json.loads(FOUNDATION.read_text(encoding="utf-8-sig"))
        self.assertEqual(data["format"], "SRSTUDIO_NEXT_FOUNDATION_1")
        self.assertEqual(data["target_major"], "5.0.0")
        self.assertEqual(data["baseline"], "4.0.16-hybrid.stable4")
        self.assertFalse(data["public_release"])

    def test_required_runtime_files(self):
        required = [
            "SR_Studio_Gerador.py",
            "AtacadoModule.py",
            "ManualModule.py",
            "PromotionBuilder.py",
            "PromotionLibrary.py",
            "ProductOrganizer.py",
            "CISSProductSync.py",
            "SRIAEngine.py",
            "Encartes3Engine.py",
            "Encartes10_beta16.js",
            "Encartes11.css",
            "assets/SR_logo.png",
            "assets/SR_Studio.ico",
            "modelos/ATACADO.pptx",
            "version.json",
            "requirements.txt",
        ]
        missing = [item for item in required if not (APP / item).exists()]
        self.assertEqual(missing, [], f"Arquivos ausentes: {missing}")

    def test_baseline_version(self):
        version = json.loads((APP / "version.json").read_text(encoding="utf-8-sig"))
        dist = version.get("distribution_version") or version.get("version")
        self.assertEqual(dist, "4.0.16-hybrid.stable4")

    def test_python_sources_compile(self):
        for path in APP.glob("*.py"):
            py_compile.compile(str(path), doraise=True)

    def test_new_architecture_layers_exist(self):
        for layer in ("core", "services", "modules", "ui", "data"):
            self.assertTrue((APP / layer / "__init__.py").exists(), layer)


if __name__ == "__main__":
    unittest.main()
