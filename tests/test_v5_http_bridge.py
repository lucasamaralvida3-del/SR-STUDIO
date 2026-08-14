from __future__ import annotations

import json
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from Encartes3Engine import local_editor_url  # noqa: E402
from services import project_store  # noqa: E402


class V5HttpBridgeTests(unittest.TestCase):
    def setUp(self):
        self.project = project_store.create_project(
            "HTTP Bridge Test",
            "TESTE",
            {
                "products": [],
                "pages": [{"id": "pg1", "name": "Página 1", "width": 794, "height": 1123, "elements": [], "templateElements": [], "templateSlots": []}],
                "encartes_state": {
                    "products": [],
                    "pages": [{"id": "pg1", "name": "Página 1", "width": 794, "height": 1123, "elements": [], "templateElements": [], "templateSlots": []}],
                    "pageIndex": 0,
                    "selected": None,
                    "grid": True,
                    "snap": True,
                    "zoom": .75,
                    "categoryFilter": "TODAS",
                    "fonts": [],
                    "projectName": "HTTP Bridge Test",
                },
            },
        )
        self.project_id = self.project["project_id"]
        self.base = local_editor_url().rsplit("/", 1)[0]

    def tearDown(self):
        try:
            project_store.delete_project(self.project_id, permanent=True)
        except Exception:
            pass

    def _json(self, path: str, method: str = "GET", data=None):
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=body, method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_load_autosave_and_manual_save(self):
        health = self._json("/api/encartes/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["version"], "5.0.0-next")

        loaded = self._json("/api/v5/project?id=" + self.project_id)
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["state"]["projectName"], "HTTP Bridge Test")

        state = loaded["state"]
        state["projectName"] = "HTTP Bridge Alterado"
        state["products"] = [{"id": "p1", "name": "CAFÉ TESTE", "price": "9,99", "unit": "UN"}]
        auto = self._json("/api/v5/project/save?id=" + self.project_id + "&autosave=1", "POST", {"state": state})
        self.assertTrue(auto["ok"])
        self.assertTrue(auto["autosave"])
        recovered = project_store.load_project(self.project_id, prefer_autosave=True)
        self.assertEqual(recovered["state"]["encartes_state"]["projectName"], "HTTP Bridge Alterado")

        manual = self._json("/api/v5/project/save?id=" + self.project_id + "&autosave=0", "POST", {"state": state})
        self.assertTrue(manual["ok"])
        self.assertFalse(manual["autosave"])
        saved = project_store.load_project(self.project_id)
        self.assertEqual(saved["name"], "HTTP Bridge Alterado")
        self.assertTrue(project_store.list_versions(self.project_id))


if __name__ == "__main__":
    unittest.main()
