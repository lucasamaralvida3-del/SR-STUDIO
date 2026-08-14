import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sr_studio"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class VisualBeta2Tests(unittest.TestCase):
    def test_editor_loads_visual_layer(self):
        index = (SRC / "Encartes3_index.html").read_text(encoding="utf-8")
        self.assertIn("Encartes12_visual.css", index)
        self.assertIn("Encartes12_visual.js", index)
        css = (SRC / "Encartes12_visual.css").read_text(encoding="utf-8")
        self.assertIn(".sr5-rail", css)
        self.assertIn("grid-template-columns:82px", css)
        js = (SRC / "Encartes12_visual.js").read_text(encoding="utf-8")
        self.assertIn("Nova interface visual Beta 2 ativa", js)
        self.assertIn("Importar Planilha", js)
        self.assertIn("Importar PPTX", js)

    def test_desktop_visual_patch_is_installed(self):
        import SR_Studio_Gerador as app
        self.assertTrue(getattr(app.App, "_SR5_VISUAL_INSTALLED", False))
        self.assertEqual(app.App.build_layout.__module__, "ui.studio5_visual")
        self.assertEqual(app.App.show_home.__module__, "ui.studio5_visual")

    def test_visual_files_are_source_only(self):
        for name in ["ui/studio5_visual.py", "Encartes12_visual.css", "Encartes12_visual.js"]:
            self.assertTrue((SRC / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
