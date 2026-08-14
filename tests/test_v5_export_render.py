from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services import project_store  # noqa: E402
from services.project_export import capture_project_pages, export_project  # noqa: E402


class V5ProjectExportTests(unittest.TestCase):
    def setUp(self):
        product = {
            "id": "p1",
            "name": "CAFÉ TESTE 500G",
            "code": "123",
            "price": "9,99",
            "app": "8,99",
            "unit": "UN",
            "limit": "",
            "category": "MERCEARIA",
            "image": "",
            "bankFound": False,
        }
        page = {
            "id": "pg1",
            "name": "Página 1",
            "width": 600,
            "height": 800,
            "category": "MERCEARIA",
            "templateElements": [],
            "templateSlots": [],
            "elements": [{"id": "e1", "productId": "p1", "slotId": None, "x": 80, "y": 120, "w": 440, "h": 420, "highlight": 1, "fontFamily": "Segoe UI"}],
        }
        enc = {
            "products": [product], "pages": [page], "pageIndex": 0, "selected": None,
            "grid": False, "snap": True, "zoom": 1, "categoryFilter": "TODAS", "fonts": [],
            "projectName": "Export Smoke Test", "partEditMode": True, "proSelection": [], "cropKey": None, "proGroups": {},
        }
        self.project = project_store.create_project("Export Smoke Test", "TESTE", {"products": [product], "pages": [page], "encartes_state": enc})
        self.project_id = self.project["project_id"]

    def tearDown(self):
        try:
            project_store.delete_project(self.project_id, permanent=True)
        except Exception:
            pass

    def test_capture_and_social_export(self):
        with tempfile.TemporaryDirectory(prefix="srstudio-v5-capture-") as td:
            root = Path(td)
            captures = capture_project_pages(self.project_id, root / "capture")
            self.assertEqual(len(captures), 1)
            self.assertTrue(captures[0].is_file())
            self.assertGreater(captures[0].stat().st_size, 1000)
            with Image.open(captures[0]) as im:
                self.assertGreaterEqual(im.width, 300)
                self.assertGreaterEqual(im.height, 300)

            profile = {
                "id": "test_social",
                "name": "Teste Social 320x400",
                "format": "PNG",
                "width_px": 320,
                "height_px": 400,
                "dpi": 96,
                "page_size": "",
                "options": {"fit": "contain"},
            }
            result = export_project(self.project_id, profile, root / "output", "teste")
            self.assertEqual(result["pages"], 1)
            self.assertEqual(len(result["files"]), 1)
            output = Path(result["files"][0])
            self.assertTrue(output.is_file())
            with Image.open(output) as im:
                self.assertEqual(im.size, (320, 400))


if __name__ == "__main__":
    unittest.main()
