from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "sr_studio" / "SR_Studio_Gerador.py"

text = MAIN.read_text(encoding="utf-8")
marker = '\n\nif __name__=="__main__":\n'
install = '''\n\n# SR Studio 5.0 Beta 2 — nova identidade visual.\n# O patch é aplicado depois da definição completa de App, preservando o núcleo funcional.\nfrom ui.studio5_visual import install_studio5_visual as _install_studio5_visual\n_install_studio5_visual(App)\n'''

if "_install_studio5_visual(App)" not in text:
    if marker not in text:
        raise SystemExit("Marcador __main__ não encontrado em SR_Studio_Gerador.py")
    text = text.replace(marker, install + marker, 1)
    MAIN.write_text(text, encoding="utf-8")

print("VISUAL_BETA2_PATCH_OK")
