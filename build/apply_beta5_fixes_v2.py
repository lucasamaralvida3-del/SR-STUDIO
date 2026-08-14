from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"


def patch_sidebar_fidelity() -> None:
    path = APP / "ui" / "studio5_fidelity.py"
    text = path.read_text(encoding="utf-8-sig")
    marker = "SR5_BETA5_FIDELITY_SCROLL"
    if marker not in text:
        old = '''    nav_canvas=tk.Canvas(self.sidebar,bg=pal["SIDEBAR"],highlightthickness=0,bd=0)\n    nav_canvas.pack(fill="both",expand=True)\n    self.nav_holder=tk.Frame(nav_canvas,bg=pal["SIDEBAR"])\n    nav_window=nav_canvas.create_window((0,0),window=self.nav_holder,anchor="nw")\n    self.nav_holder.bind("<Configure>",lambda e:nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))\n    nav_canvas.bind("<Configure>",lambda e:nav_canvas.itemconfigure(nav_window,width=e.width))\n'''
        if old not in text:
            raise RuntimeError("Bloco real do menu Fidelity não encontrado")
        new = '''    # SR5_BETA5_FIDELITY_SCROLL: menu final rolável em resoluções menores.\n    nav_stage=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],bd=0)\n    nav_stage.pack(fill="both",expand=True)\n    nav_canvas=tk.Canvas(nav_stage,bg=pal["SIDEBAR"],highlightthickness=0,bd=0)\n    nav_scroll=ttk.Scrollbar(nav_stage,orient="vertical",command=nav_canvas.yview)\n    nav_canvas.configure(yscrollcommand=nav_scroll.set)\n    nav_scroll.pack(side="right",fill="y")\n    nav_canvas.pack(side="left",fill="both",expand=True)\n    self.nav_canvas=nav_canvas\n    self.nav_scroll=nav_scroll\n    self.nav_holder=tk.Frame(nav_canvas,bg=pal["SIDEBAR"])\n    nav_window=nav_canvas.create_window((0,0),window=self.nav_holder,anchor="nw")\n    self.nav_holder.bind("<Configure>",lambda e:nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))\n    nav_canvas.bind("<Configure>",lambda e:nav_canvas.itemconfigure(nav_window,width=e.width))\n    def _sr5_nav_wheel(event):\n        try:\n            steps=int(-1*(event.delta/120))\n            nav_canvas.yview_scroll(steps if steps else (-1 if event.delta>0 else 1),"units")\n            return "break"\n        except Exception:\n            return None\n    def _sr5_bind_wheel(_event=None):\n        nav_canvas.bind_all("<MouseWheel>",_sr5_nav_wheel)\n    def _sr5_unbind_wheel(_event=None):\n        try:nav_canvas.unbind_all("<MouseWheel>")\n        except Exception:pass\n    for _w in (nav_canvas,self.nav_holder):\n        _w.bind("<Enter>",_sr5_bind_wheel)\n        _w.bind("<Leave>",_sr5_unbind_wheel)\n'''
        text = text.replace(old, new, 1)
        text = text.replace('brand=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],height=112)', 'brand=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],height=92)', 1)
        text = text.replace('gl.pack(fill="x",padx=24,pady=(13,5))', 'gl.pack(fill="x",padx=24,pady=(8,3))')
        text = text.replace('row.pack(fill="x",padx=12,pady=2)', 'row.pack(fill="x",padx=12,pady=1)')
        text = text.replace('self.icon.pack(side="left",padx=(11,9),pady=8)', 'self.icon.pack(side="left",padx=(11,9),pady=5)', 1)

    if "self.quick_config_btn" not in text:
        anchor = '''    self.footer_credit=tk.Label(foot,text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas",bg=pal["SIDEBAR"],fg="#9DB8F5",font=("Segoe UI",7))\n    self.footer_credit.pack(pady=(0,6))\n'''
        if anchor not in text:
            raise RuntimeError("Rodapé real do Fidelity não encontrado")
        extra = anchor + '''    self.quick_config_btn=tk.Button(foot,text="⚙" if self.sidebar_collapsed else "⚙  Configurações",command=lambda:self.navigate("config"),\n                                    bg="#0E3295",fg="#DCE6FF",activebackground=SIDEBAR_ACTIVE,activeforeground="#FFFFFF",\n                                    relief="flat",bd=0,font=("Segoe UI Symbol",8,"bold"),pady=7,cursor="hand2")\n    self.quick_config_btn.pack(fill="x",pady=(0,5))\n'''
        text = text.replace(anchor, extra, 1)
        toggle = '''    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")\n    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")\n'''
        if toggle in text:
            text = text.replace(toggle, '''    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")\n    try:self.quick_config_btn.config(text="⚙" if self.sidebar_collapsed else "⚙  Configurações")\n    except Exception:pass\n    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")\n''', 1)
    path.write_text(text, encoding="utf-8")


def patch_review_window() -> None:
    path = APP / "SR_Studio_Gerador.py"
    text = path.read_text(encoding="utf-8-sig")
    marker = "SR5_BETA5_REVIEW_FIRST_PAINT"
    if marker in text:
        return
    anchor = '''        self.build(); self.refresh_tree(); self.update_counter()\n'''
    if anchor not in text:
        raise RuntimeError("Inicialização da ReviewWindow não encontrada")
    replacement = anchor + '''        # SR5_BETA5_REVIEW_FIRST_PAINT: força a primeira pintura sem depender de clique/filtro.\n        def _sr5_first_review_paint():\n            try:\n                self.refresh_tree()\n                children=self.tree.get_children()\n                if children and not self.tree.selection():\n                    first=str(focus_job_id) if focus_job_id is not None and self.tree.exists(str(focus_job_id)) else str(children[0])\n                    if self.tree.exists(first):\n                        self.tree.selection_set(first);self.tree.see(first);self.details()\n                self.tree.update_idletasks();self.update_idletasks()\n            except Exception:\n                pass\n        self.after_idle(_sr5_first_review_paint)\n        self.after(140,_sr5_first_review_paint)\n'''
    text = text.replace(anchor, replacement, 1)
    path.write_text(text, encoding="utf-8")


def rebuild_brand_from_url(url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "SR-Studio-Beta5-Publisher", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    if len(raw) < 5000:
        raise RuntimeError(f"Fonte da logo muito pequena: {len(raw)} bytes")
    image = Image.open(io.BytesIO(raw)); image.load(); image = image.convert("RGBA")
    probe = image.convert("RGB").resize((96,96), Image.Resampling.LANCZOS)
    pixels=list(probe.getdata());total=len(pixels)
    black=sum(1 for r,g,b in pixels if r<25 and g<25 and b<25)/total
    white=sum(1 for r,g,b in pixels if r>235 and g>235 and b>235)/total
    blue=sum(1 for r,g,b in pixels if b>110 and b>r*1.15 and b>g*1.05)/total
    if black>=0.12 or white<=0.08 or blue<=0.08:
        raise RuntimeError(f"Logo oficial reprovada: black={black:.3f}, white={white:.3f}, blue={blue:.3f}")
    hd=image.resize((2048,2048),Image.Resampling.LANCZOS)
    hd=hd.filter(ImageFilter.UnsharpMask(radius=.8,percent=90,threshold=3))
    assets=APP/"assets";assets.mkdir(parents=True,exist_ok=True)
    logo=assets/"SR_logo.png";icon=assets/"SR_Studio.ico"
    hd.save(logo,"PNG",optimize=True)
    hd.save(icon,format="ICO",sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(96,96),(128,128),(256,256)])
    with Image.open(logo) as check:check.load();assert check.size==(2048,2048)
    if icon.stat().st_size<10000:raise RuntimeError("ICO final parece incompleto")
    print("BRAND_BETA5_V2_OK",len(raw),logo.stat().st_size,icon.stat().st_size,round(black,3),round(white,3),round(blue,3))


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--logo-url",required=True);args=parser.parse_args()
    patch_sidebar_fidelity();patch_review_window();rebuild_brand_from_url(args.logo_url)
    print("BETA5_FIXES_V2_APPLIED")


if __name__ == "__main__":
    main()
