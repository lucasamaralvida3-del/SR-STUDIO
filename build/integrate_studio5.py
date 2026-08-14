from __future__ import annotations

import argparse
from pathlib import Path


def apply(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    import_anchor = "from SRSpellCheck import correct_campaign_text\n"
    import_line = "from modules.Studio5Module import Studio5Panel\n"
    if import_line not in text:
        if import_anchor not in text:
            raise RuntimeError("Âncora de importação não encontrada")
        text = text.replace(import_anchor, import_anchor + import_line, 1)

    nav_old = '("home","⌂","Início"),("sria","✦","SR IA")'
    nav_new = '("home","⌂","Início"),("studio5","★","Central 5.0"),("sria","✦","SR IA")'
    if '("studio5","★","Central 5.0")' not in text:
        if nav_old not in text:
            raise RuntimeError("Âncora do menu lateral não encontrada")
        text = text.replace(nav_old, nav_new, 1)

    route_old = '        elif key == "config": self.show_config()\n        elif key == "home": self.show_home()'
    route_new = '        elif key == "studio5": self.show_studio5()\n        elif key == "config": self.show_config()\n        elif key == "home": self.show_home()'
    if 'elif key == "studio5": self.show_studio5()' not in text:
        if route_old not in text:
            raise RuntimeError("Âncora de navegação não encontrada")
        text = text.replace(route_old, route_new, 1)

    method = '''    def show_studio5(self):
        self.clear_content()
        self.page_title.config(text="Central SR Studio 5.0")
        pal=self.palette
        for k,b in self.nav_buttons.items():
            b.config(bg=pal["SIDEBAR_HOVER"] if k=="studio5" else pal["SIDEBAR"],
                     fg="white" if k=="studio5" else "#DCE7F7")
        self.studio5_panel=Studio5Panel(self.content,self,pal)
        self.studio5_panel.pack(fill="both",expand=True)

'''
    method_anchor = '    def show_encartes(self):\n'
    if '    def show_studio5(self):\n' not in text:
        if method_anchor not in text:
            raise RuntimeError("Âncora do Encartes não encontrada")
        text = text.replace(method_anchor, method + method_anchor, 1)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("src/sr_studio/SR_Studio_Gerador.py"))
    args = parser.parse_args()
    changed = apply(args.path)
    print("Central 5.0 integrada." if changed else "Central 5.0 já estava integrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
