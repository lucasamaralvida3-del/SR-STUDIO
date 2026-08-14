from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'/'sr_studio'


class FidelityVisualTests(unittest.TestCase):
    def test_hidpi_module(self):
        text=(SRC/'ui'/'hidpi.py').read_text(encoding='utf-8')
        self.assertIn('SetProcessDpiAwarenessContext',text)
        self.assertIn('SetProcessDpiAwareness',text)

    def test_fidelity_shell_exists(self):
        text=(SRC/'ui'/'studio5_fidelity.py').read_text(encoding='utf-8')
        for marker in ('class VectorIcon','class NavRow','def _build_layout','def _show_home','_SR5_FIDELITY_INSTALLED'):
            self.assertIn(marker,text)

    def test_encartes_fidelity_assets(self):
        css=(SRC/'Encartes13_fidelity.css').read_text(encoding='utf-8')
        js=(SRC/'Encartes13_fidelity.js').read_text(encoding='utf-8')
        self.assertIn('Fidelidade Visual',css)
        self.assertIn('<svg',js)
        self.assertIn('beta4',js)

    def test_brand_is_hd_after_build(self):
        logo=SRC/'assets'/'SR_logo.png'
        with Image.open(logo) as im:
            self.assertGreaterEqual(im.width,1024)
            self.assertGreaterEqual(im.height,1024)

    def test_app_and_editor_are_wired(self):
        main=(SRC/'SR_Studio_Gerador.py').read_text(encoding='utf-8-sig')
        index=(SRC/'Encartes3_index.html').read_text(encoding='utf-8-sig')
        self.assertIn('enable_hidpi()',main)
        self.assertIn('_install_studio5_fidelity(App)',main)
        self.assertIn('Encartes13_fidelity.css',index)
        self.assertIn('Encartes13_fidelity.js',index)


if __name__=='__main__':
    unittest.main()
