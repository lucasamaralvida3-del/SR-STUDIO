from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.spreadsheet_profiles import inspect_workbook, read_rows, save_profile, delete_profile  # noqa: E402
from services.template_registry import analyze_template, detected_mapping, save_template, delete_template, load_learned_template  # noqa: E402


class SpreadsheetImporterTests(unittest.TestCase):
    def test_detect_header_profile_and_read_rows(self):
        with tempfile.TemporaryDirectory(prefix="srstudio-v5-xlsx-") as td:
            path = Path(td) / "promocao.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "PROMOÇÃO"
            ws.append(["RELATÓRIO DE PROMOÇÃO SR"])
            ws.append([])
            ws.append(["CÓDIGO", "DESCRIÇÃO PRODUTO", "PREÇO PROMOÇÃO", "PREÇO APP", "ENTRADA", "LIMITE", "CATEGORIA", "DESTAQUE"])
            ws.append([101, "CAFE TESTE 500G", 12.99, 11.49, "UN", "6UN", "MERCEARIA", "SIM"])
            ws.append([202, "BATATA TESTE", 4.89, "", "KG", "", "HORTIFRUTI", "NÃO"])
            wb.save(path)

            info = inspect_workbook(path)
            best = info["best"]
            self.assertEqual(best["name"], "PROMOÇÃO")
            self.assertEqual(best["header_row"], 3)
            mapping = best["suggested_mapping"]
            for field in ("code", "name", "promo_price", "app_price", "entry", "limit", "category", "highlight"):
                self.assertIn(field, mapping)

            profile = save_profile("Teste Importador CI", best["name"], best["header_row"], best["headers"], mapping)
            try:
                rows = read_rows(path, profile)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["code"], "101")
                self.assertEqual(rows[0]["name"], "CAFE TESTE 500G")
                self.assertEqual(rows[0]["unit"], "UN")
                self.assertEqual(rows[0]["limit"], "6UN")
                self.assertTrue(rows[0]["highlight"])
                self.assertEqual(rows[1]["unit"], "KG")
                self.assertFalse(rows[1]["highlight"])
            finally:
                delete_profile(profile["id"])


class PPTXImporterTests(unittest.TestCase):
    def test_analyze_save_and_reload_learned_template(self):
        source = APP / "modelos" / "ATACADO.pptx"
        self.assertTrue(source.is_file())
        analysis = analyze_template(source)
        self.assertGreaterEqual(analysis["page_count"], 1)
        self.assertGreater(len(analysis["shapes"]), 0)
        mapping = detected_mapping(analysis)

        profile = save_template("ATACADO CI 5.0", "ATACADO", source, analysis=analysis, mapping=mapping)
        try:
            self.assertTrue(Path(profile["template_path"]).is_file())
            learned = load_learned_template(profile["id"])
            parsed = learned["parsed"]
            self.assertGreaterEqual(int(parsed.get("pageCount") or 0), 1)
            self.assertTrue(parsed.get("pages"))
            # A reconstrução deve sempre deixar a chave templateSlots disponível por página,
            # mesmo que um modelo específico ainda não tenha slots reconhecidos automaticamente.
            for page in parsed["pages"]:
                self.assertIn("templateSlots", page)
        finally:
            delete_template(profile["id"])


if __name__ == "__main__":
    unittest.main()
