from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

# Inicializa o schema legado que o Banco Central 5.0 estende.
import ProductOrganizer  # noqa: F401,E402

from services import project_store  # noqa: E402
from services.export_profiles import list_profiles as list_export_profiles  # noqa: E402
from services.spreadsheet_profiles import suggest_mapping, header_signature  # noqa: E402
from services.validation_center import validate_project_payload  # noqa: E402


class V5ProjectTests(unittest.TestCase):
    def tearDown(self):
        for project_id in getattr(self, "created", []):
            try:
                project_store.delete_project(project_id, permanent=True)
            except Exception:
                pass

    def _project(self):
        self.created = getattr(self, "created", [])
        item = project_store.create_project("Teste V5", "TESTE")
        self.created.append(item["project_id"])
        return item

    def test_project_save_autosave_recovery_and_version(self):
        item = self._project()
        item["state"]["products"] = [{"id": "p1", "name": "CAFÉ TESTE", "price": "9,99"}]
        saved = project_store.save_project(item)
        self.assertGreaterEqual(saved["revision"], 2)
        time.sleep(0.05)
        auto = dict(saved)
        auto["state"] = dict(saved["state"])
        auto["state"]["products"] = [{"id": "p1", "name": "CAFÉ ALTERADO", "price": "8,99"}]
        project_store.save_project(auto, autosave=True)
        self.assertTrue(project_store.autosave_status(item["project_id"])["recoverable"])
        recovered = project_store.load_project(item["project_id"], prefer_autosave=True)
        self.assertEqual(recovered["state"]["products"][0]["name"], "CAFÉ ALTERADO")
        version = project_store.snapshot_project(item["project_id"], "Teste manual")
        self.assertEqual(version["label"], "Teste manual")
        self.assertTrue(project_store.list_versions(item["project_id"]))

    def test_duplicate_project(self):
        item = self._project()
        copy = project_store.duplicate_project(item["project_id"], "Cópia V5")
        self.created.append(copy["project_id"])
        self.assertNotEqual(copy["project_id"], item["project_id"])
        self.assertEqual(copy["name"], "Cópia V5")


class V5SpreadsheetTests(unittest.TestCase):
    def test_suggest_mapping_common_ciss_headers(self):
        headers = ["CÓDIGO", "DESCRIÇÃO PRODUTO", "PREÇO PROMOÇÃO", "PREÇO APP", "ENTRADA", "LIMITE", "CATEGORIA"]
        mapping = suggest_mapping(headers)
        self.assertEqual(mapping.get("code"), "CÓDIGO")
        self.assertEqual(mapping.get("name"), "DESCRIÇÃO PRODUTO")
        self.assertEqual(mapping.get("promo_price"), "PREÇO PROMOÇÃO")
        self.assertEqual(mapping.get("app_price"), "PREÇO APP")
        self.assertEqual(mapping.get("entry"), "ENTRADA")
        self.assertEqual(mapping.get("limit"), "LIMITE")
        self.assertTrue(header_signature(headers))


class V5ValidationTests(unittest.TestCase):
    def test_invalid_project_is_blocked(self):
        payload = {
            "state": {
                "encartes_state": {
                    "products": [{"id": "p1", "name": "PRODUTO TESTE", "price": "0,00", "unit": "UN", "image": "", "bankFound": False}],
                    "pages": [{"id": "pg1", "name": "Página 1", "width": 794, "height": 1123, "elements": [{"id": "e1", "productId": "p1", "x": 0, "y": 0, "w": 200, "h": 200}], "templateSlots": []}],
                }
            }
        }
        result = validate_project_payload(payload)
        self.assertFalse(result["ready"])
        codes = {x["code"] for x in result["issues"]}
        self.assertIn("PRECO_INVALIDO", codes)
        self.assertIn("SEM_IMAGEM", codes)


class V5ExportTests(unittest.TestCase):
    def test_builtin_export_profiles(self):
        names = {x["name"] for x in list_export_profiles()}
        self.assertIn("PDF A4", names)
        self.assertIn("PDF A3", names)
        self.assertIn("Instagram Feed 1080x1350", names)
        self.assertIn("Instagram Story 1080x1920", names)
        self.assertIn("WhatsApp 1080x1350", names)


class V5BridgeStaticTests(unittest.TestCase):
    def test_editor_bridge_is_wired(self):
        index = (APP / "Encartes3_index.html").read_text(encoding="utf-8")
        bridge = (APP / "Encartes11_v5.js").read_text(encoding="utf-8")
        engine = (APP / "Encartes3Engine.py").read_text(encoding="utf-8")
        self.assertIn("Encartes11_v5.js", index)
        self.assertIn("v5project", bridge)
        self.assertIn("/api/v5/project/save", bridge)
        self.assertIn("/api/v5/project/save", engine)
        self.assertIn("/api/v5/project", engine)


if __name__ == "__main__":
    unittest.main()
