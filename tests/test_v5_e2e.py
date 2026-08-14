from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP = Path(os.environ.get("SR_STUDIO_APP_UNDER_TEST") or (ROOT / "src" / "sr_studio")).resolve()
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

# Garante que o schema legado do Banco de Produtos exista antes dos serviços V5.
import ProductOrganizer  # noqa: F401,E402

from services import project_store  # noqa: E402
from services.campaign_wizard import build_campaign  # noqa: E402
from services.export_profiles import export_images, list_profiles as list_export_profiles  # noqa: E402
from services.product_catalog import quality_summary  # noqa: E402
from services.spreadsheet_profiles import (  # noqa: E402
    delete_profile as delete_sheet_profile,
    inspect_workbook,
    read_rows,
    save_profile as save_sheet_profile,
)
from services.template_registry import (  # noqa: E402
    analyze_template,
    delete_template,
    detected_mapping,
    load_learned_template,
    save_template,
)
from services.update_rollback import create_app_snapshot, restore_snapshot  # noqa: E402
from services.validation_center import validate_project  # noqa: E402


class SRStudioV5EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="srstudio-v5-e2e-")
        cls.work = Path(cls.tmp.name)
        cls.created_projects: list[str] = []
        cls.sheet_profiles: list[str] = []
        cls.templates: list[str] = []

    @classmethod
    def tearDownClass(cls):
        for pid in cls.created_projects:
            try:
                project_store.delete_project(pid, permanent=True)
            except Exception:
                pass
        for sid in cls.sheet_profiles:
            try:
                delete_sheet_profile(sid)
            except Exception:
                pass
        for tid in cls.templates:
            try:
                delete_template(tid)
            except Exception:
                pass
        cls.tmp.cleanup()

    def _sample_sheet(self) -> Path:
        path = self.work / "campanha_teste.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "PROMOCAO"
        ws.append(["CÓDIGO", "DESCRIÇÃO PRODUTO", "PREÇO PROMOÇÃO", "PREÇO APP", "ENTRADA", "LIMITE", "CATEGORIA", "DESTAQUE"])
        ws.append(["1001", "CAFÉ TESTE 500G", 19.98, 18.98, "UN", "6UN", "MERCEARIA", "SIM"])
        ws.append(["1002", "AÇÚCAR TESTE 5KG", 17.49, "", "UN", "", "MERCEARIA", ""])
        ws.append(["1003", "TOMATE TESTE", 7.99, "", "KG", "", "HORTIFRUTI", ""])
        wb.save(path)
        return path

    def test_01_spreadsheet_profile_and_campaign(self):
        sheet = self._sample_sheet()
        info = inspect_workbook(sheet)
        best = info["best"]
        self.assertEqual(best["name"], "PROMOCAO")
        self.assertEqual(best["suggested_mapping"].get("highlight"), "DESTAQUE")
        profile = save_sheet_profile(
            "E2E CISS",
            best["name"],
            best["header_row"],
            best["headers"],
            best["suggested_mapping"],
        )
        self.sheet_profiles.append(profile["id"])
        rows = read_rows(sheet, profile)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]["highlight"])
        self.assertEqual(rows[2]["unit"], "KG")

        result = build_campaign(
            project_name="Campanha E2E 5.0",
            campaign="TESTE AUTOMÁTICO",
            spreadsheet_path=sheet,
            spreadsheet_profile=profile,
            products_per_page=2,
            group_by_category=True,
        )
        project = result["project"]
        self.created_projects.append(project["project_id"])
        self.assertEqual(result["products"], 3)
        self.assertEqual(result["highlighted"], 1)
        self.assertEqual(result["categories"], 2)
        self.assertGreaterEqual(result["pages"], 2)
        products = project["state"]["encartes_state"]["products"]
        self.assertTrue(products[0]["highlight"])
        pages = project["state"]["encartes_state"]["pages"]
        self.assertEqual(pages[0].get("category"), "MERCEARIA")

        validation = validate_project(project["project_id"])
        self.assertEqual(validation["products"], 3)
        self.assertGreaterEqual(validation["pages"], 2)
        self.assertIn(validation["status"], {"PRONTO_PARA_IMPRIMIR", "CORRECAO_NECESSARIA"})

        package = project_store.export_project(project["project_id"], self.work / "campanha.srstudio")
        self.assertTrue(package.is_file())
        imported = project_store.import_project(package, "Campanha E2E Importada")
        self.created_projects.append(imported["project_id"])
        self.assertNotEqual(imported["project_id"], project["project_id"])
        self.assertEqual(len(imported["state"]["encartes_state"]["products"]), 3)

    def test_02_real_pptx_template_learning(self):
        models = sorted((APP / "modelos").glob("*.pptx"))
        self.assertTrue(models, "Nenhum PPTX real disponível para o teste")
        source = models[0]
        analysis = analyze_template(source)
        self.assertGreaterEqual(analysis["page_count"], 1)
        mapping = detected_mapping(analysis)
        profile = save_template("Modelo E2E", "TESTE", source, analysis, mapping)
        self.templates.append(profile["id"])
        learned = load_learned_template(profile["id"])
        self.assertEqual(learned["profile"]["id"], profile["id"])
        self.assertTrue(learned["parsed"].get("pages"))

    def test_03_export_profiles_render_real_files(self):
        src = self.work / "pagina_base.png"
        Image.new("RGB", (640, 900), "white").save(src)
        profiles = {p["name"]: p for p in list_export_profiles()}
        for name, expected, suffix in [
            ("Instagram Feed 1080x1350", (1080, 1350), ".png"),
            ("Instagram Story 1080x1920", (1080, 1920), ".png"),
            ("WhatsApp 1080x1350", (1080, 1350), ".jpg"),
        ]:
            out = export_images([src], profiles[name], self.work / ("export_" + name.split()[0].lower()), "pagina")
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].suffix.lower(), suffix)
            with Image.open(out[0]) as im:
                self.assertEqual(im.size, expected)
        pdf = export_images([src], profiles["PDF A4"], self.work / "export_pdf", "encarte")
        self.assertEqual(len(pdf), 1)
        self.assertEqual(pdf[0].suffix.lower(), ".pdf")
        self.assertGreater(pdf[0].stat().st_size, 100)

    def test_04_product_bank_health_contract(self):
        summary = quality_summary()
        for key in ("total", "ok", "without_image", "low_resolution", "without_commercial_name", "without_category"):
            self.assertIn(key, summary)
            self.assertGreaterEqual(int(summary[key]), 0)

    def test_05_safe_snapshot_and_rollback(self):
        app_copy = self.work / "rollback_app"
        app_copy.mkdir(exist_ok=True)
        marker = app_copy / "marker.txt"
        marker.write_text("VERSAO A", encoding="utf-8")
        snap = create_app_snapshot("E2E antes da alteração", source_dir=app_copy)
        marker.write_text("VERSAO B", encoding="utf-8")
        result = restore_snapshot(snap["id"], app_dir=app_copy)
        self.assertGreaterEqual(result["restored"], 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "VERSAO A")
        self.assertTrue(result.get("guard_snapshot"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
