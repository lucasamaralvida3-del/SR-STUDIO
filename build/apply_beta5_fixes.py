from __future__ import annotations

import argparse
import ast
import io
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"


def patch_sidebar() -> None:
    path = APP / "ui" / "studio5_visual.py"
    text = path.read_text(encoding="utf-8-sig")

    old = '''    nav_canvas = tk.Canvas(self.sidebar, bg=pal["SIDEBAR"], highlightthickness=0, bd=0)\n    nav_scroll = ttk.Scrollbar(self.sidebar, orient="vertical", command=nav_canvas.yview)\n    nav_canvas.configure(yscrollcommand=nav_scroll.set)\n    nav_canvas.pack(fill="both", expand=True, padx=(0, 0))\n    self.nav_holder = tk.Frame(nav_canvas, bg=pal["SIDEBAR"])\n'''
    if "SR5_BETA5_NAV_MOUSEWHEEL" not in text:
        if old not in text:
            raise RuntimeError("Bloco original do menu lateral não encontrado")
        new = '''    # Beta 5: navegação lateral realmente rolável em telas menores.\n    nav_stage = tk.Frame(self.sidebar, bg=pal["SIDEBAR"], bd=0)\n    nav_stage.pack(fill="both", expand=True)\n    nav_canvas = tk.Canvas(nav_stage, bg=pal["SIDEBAR"], highlightthickness=0, bd=0)\n    nav_scroll = ttk.Scrollbar(nav_stage, orient="vertical", command=nav_canvas.yview)\n    nav_canvas.configure(yscrollcommand=nav_scroll.set)\n    nav_scroll.pack(side="right", fill="y", pady=(2, 2))\n    nav_canvas.pack(side="left", fill="both", expand=True, padx=(0, 0))\n    self.nav_canvas = nav_canvas\n    self.nav_scroll = nav_scroll\n    self.nav_holder = tk.Frame(nav_canvas, bg=pal["SIDEBAR"])\n'''
        text = text.replace(old, new, 1)

        anchor = '''    nav_canvas.bind("<Configure>", lambda e: nav_canvas.itemconfigure(nav_window, width=e.width))\n'''
        if anchor not in text:
            raise RuntimeError("Âncora de configuração do Canvas não encontrada")
        add = '''    nav_canvas.bind("<Configure>", lambda e: nav_canvas.itemconfigure(nav_window, width=e.width))\n    # SR5_BETA5_NAV_MOUSEWHEEL: rolagem pelo mouse em toda a área do menu.\n    def _sr5_nav_wheel(event):\n        try:\n            steps = int(-1 * (event.delta / 120))\n            nav_canvas.yview_scroll(steps if steps else (-1 if event.delta > 0 else 1), "units")\n            return "break"\n        except Exception:\n            return None\n    def _sr5_nav_bind(_event=None):\n        nav_canvas.bind_all("<MouseWheel>", _sr5_nav_wheel)\n    def _sr5_nav_unbind(_event=None):\n        try:\n            nav_canvas.unbind_all("<MouseWheel>")\n        except Exception:\n            pass\n    nav_canvas.bind("<Enter>", _sr5_nav_bind)\n    nav_canvas.bind("<Leave>", _sr5_nav_unbind)\n    self.nav_holder.bind("<Enter>", _sr5_nav_bind)\n    self.nav_holder.bind("<Leave>", _sr5_nav_unbind)\n'''
        text = text.replace(anchor, add, 1)

        # Densidade menor para caber melhor em 1080p sem perder legibilidade.
        text = text.replace('height=100)', 'height=82)', 1)
        text = text.replace('pady=(13, 5)', 'pady=(9, 4)')
        text = text.replace('padx=18, pady=9, cursor="hand2"', 'padx=16, pady=6, cursor="hand2"')

    if "self.quick_config_btn" not in text:
        anchor = '''    self.footer_credit = tk.Label(foot, text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas", bg=pal["SIDEBAR"], fg="#9DB8F5", font=("Segoe UI", 7))\n    self.footer_credit.pack(pady=(0, 5))\n'''
        if anchor not in text:
            raise RuntimeError("Rodapé do menu não encontrado")
        replacement = anchor + '''    # Configurações permanece acessível mesmo quando a lista do menu precisa rolar.\n    self.quick_config_btn = tk.Button(\n        foot, text="⚙" if self.sidebar_collapsed else "⚙  Configurações",\n        command=lambda: self.navigate("config"), bg=pal["SIDEBAR"], fg="#DCE6FF",\n        activebackground=pal["SIDEBAR_HOVER"], activeforeground="white",\n        relief="flat", bd=0, font=("Segoe UI Symbol", 8, "bold"), pady=6, cursor="hand2"\n    )\n    self.quick_config_btn.pack(fill="x", pady=(0, 5))\n'''
        text = text.replace(anchor, replacement, 1)

        toggle = '''    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")\n    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")\n'''
        if toggle in text:
            text = text.replace(toggle, '''    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")\n    try:\n        self.quick_config_btn.config(text="⚙" if self.sidebar_collapsed else "⚙  Configurações")\n    except Exception:\n        pass\n    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")\n''', 1)

    path.write_text(text, encoding="utf-8")


def _pick_review_refresh(text: str) -> str:
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PreGenerationDialog"), None)
    if cls is None:
        raise RuntimeError("PreGenerationDialog não encontrado")
    lines = text.splitlines()
    candidates: list[tuple[int, str]] = []
    for method in cls.body:
        if not isinstance(method, ast.FunctionDef) or method.name == "__init__":
            continue
        required = len(method.args.args) - len(method.args.defaults)
        if required > 1:
            continue
        src = "\n".join(lines[method.lineno - 1:method.end_lineno])
        name = method.name.lower()
        score = 0
        for key, value in [
            ("refresh", 20), ("rebuild", 18), ("render", 16), ("populate", 16),
            ("update", 8), ("load", 8), ("filter", 6), ("rows", 5),
            ("table", 5), ("tree", 5),
        ]:
            if key in name:
                score += value
        if ".insert(" in src:
            score += 8
        if ".delete(" in src:
            score += 6
        if "tree" in src.lower() or "list" in src.lower():
            score += 4
        if score:
            candidates.append((score, method.name))
    if not candidates:
        raise RuntimeError("Método de atualização da revisão não identificado")
    candidates.sort(reverse=True)
    return candidates[0][1]


def patch_pre_generation_dialog() -> None:
    path = APP / "SRStudio21.py"
    text = path.read_text(encoding="utf-8-sig")
    marker = "SR5_BETA5_INITIAL_REVIEW_REFRESH"
    if marker in text:
        return

    target = _pick_review_refresh(text)
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PreGenerationDialog")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    lines = text.splitlines()

    insert_at = None
    for index in range(init.lineno - 1, init.end_lineno):
        if "wait_window(" in lines[index]:
            insert_at = index
            break
    if insert_at is None:
        # Última instrução do __init__; o after executará quando o loop do Tk receber controle.
        insert_at = init.end_lineno - 1

    indent = " " * 8
    block = [
        indent + "# SR5_BETA5_INITIAL_REVIEW_REFRESH: popular a revisão já na primeira abertura.",
        indent + "def _sr5_initial_review_refresh():",
        indent + "    try:",
        indent + f"        self.{target}()",
        indent + "        self.update_idletasks()",
        indent + "    except Exception:",
        indent + "        pass",
        indent + "self.after_idle(_sr5_initial_review_refresh)",
        indent + "self.after(100, _sr5_initial_review_refresh)",
    ]
    lines[insert_at:insert_at] = block
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("REVIEW_REFRESH_METHOD", target)


def rebuild_official_brand(logo_zip: Path) -> None:
    if not logo_zip.exists():
        raise FileNotFoundError(logo_zip)
    with zipfile.ZipFile(logo_zip) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith("files/assets/sr_logo.png")]
        if not names:
            names = [n for n in archive.namelist() if n.lower().endswith("assets/sr_logo.png")]
        if not names:
            raise RuntimeError("Logo oficial não encontrada no pacote Stable 3")
        raw = archive.read(names[0])

    # Leitura estrita: não aceitamos mais PNG truncado como fonte da marca.
    image = Image.open(io.BytesIO(raw))
    image.load()
    image = image.convert("RGBA")

    probe = image.convert("RGB").resize((96, 96), Image.Resampling.LANCZOS)
    pixels = list(probe.getdata())
    total = len(pixels)
    black = sum(1 for r, g, b in pixels if r < 25 and g < 25 and b < 25) / total
    white = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235) / total
    blue = sum(1 for r, g, b in pixels if b > 110 and b > r * 1.15 and b > g * 1.05) / total
    if black >= 0.12 or white <= 0.08 or blue <= 0.08:
        raise RuntimeError(f"Logo oficial reprovada na validação visual: black={black:.3f}, white={white:.3f}, blue={blue:.3f}")

    hd = image.resize((2048, 2048), Image.Resampling.LANCZOS)
    hd = hd.filter(ImageFilter.UnsharpMask(radius=0.9, percent=105, threshold=3))
    assets = APP / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    logo = assets / "SR_logo.png"
    icon = assets / "SR_Studio.ico"
    hd.save(logo, "PNG", optimize=True)
    hd.save(icon, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)])

    # Validação do arquivo final sem tolerância a truncamento.
    check = Image.open(logo)
    check.load()
    if check.size != (2048, 2048):
        raise RuntimeError(f"Logo final com tamanho incorreto: {check.size}")
    print("BRAND_BETA5_OK", logo.stat().st_size, icon.stat().st_size, f"black={black:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logo-zip", required=True, type=Path)
    args = parser.parse_args()
    patch_sidebar()
    patch_pre_generation_dialog()
    rebuild_official_brand(args.logo_zip)
    print("BETA5_FIXES_APPLIED")


if __name__ == "__main__":
    main()
