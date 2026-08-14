import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Beta41Tests(unittest.TestCase):
    def test_menu_has_scroll_and_compact_rows(self):
        text=(ROOT/'src/sr_studio/ui/studio5_fidelity.py').read_text(encoding='utf-8-sig')
        self.assertIn('nav_scroll=ttk.Scrollbar',text)
        self.assertIn('nav_canvas.configure(yscrollcommand=nav_scroll.set)',text)
        self.assertIn('nav_canvas.bind("<MouseWheel>",_scroll_nav)',text)
        self.assertIn('row.pack(fill="x",padx=12,pady=0)',text)
        self.assertIn('VectorIcon(self,icon_name,"#DCE6FF",22',text)

    def test_review_refreshes_after_mapping(self):
        text=(ROOT/'src/sr_studio/SR_Studio_Gerador.py').read_text(encoding='utf-8-sig')
        self.assertIn('def _refresh_review_initial(self):',text)
        self.assertIn('self.after_idle(self._refresh_review_initial)',text)
        self.assertIn('self.after(90,self._refresh_review_initial)',text)
        self.assertIn('self.tree.update_idletasks()',text)

    def test_encartes_version_label(self):
        text=(ROOT/'src/sr_studio/Encartes13_fidelity.js').read_text(encoding='utf-8-sig')
        self.assertIn("5.0.0 • Beta 4.1",text)
        self.assertIn("beta41",text)


if __name__=='__main__':
    unittest.main()
