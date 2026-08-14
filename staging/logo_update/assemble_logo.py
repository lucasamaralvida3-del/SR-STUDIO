from pathlib import Path
import json, shutil, sys

R=Path('work/files')
S=Path('staging/logo_update/source')
channel=(sys.argv[1] if len(sys.argv)>1 else 'stable').lower()

assets=R/'assets'; assets.mkdir(parents=True,exist_ok=True)
shutil.copy2(S/'SR_logo.png', assets/'SR_logo.png')
shutil.copy2(S/'SR_Studio.ico', assets/'SR_Studio.ico')

p=R/'SR_Studio_Gerador.py'
text=p.read_text(encoding='utf-8')

# Pillow para redimensionamento de alta qualidade, com fallback nativo do Tk.
anchor='from tkinter import ttk, filedialog, messagebox\n'
insert='''from tkinter import ttk, filedialog, messagebox\ntry:\n    from PIL import Image, ImageTk\nexcept Exception:\n    Image = None\n    ImageTk = None\n'''
if 'from PIL import Image, ImageTk' not in text:
    if anchor not in text: raise SystemExit('Import tkinter não localizado')
    text=text.replace(anchor,insert,1)

anchor='ASSETS = APP_DIR / "assets"\n'
brand='''ASSETS = APP_DIR / "assets"\nBRAND_LOGO = ASSETS / "SR_logo.png"\nBRAND_ICON = ASSETS / "SR_Studio.ico"\n\ndef _brand_photo(master, size):\n    """Carrega a logo oficial do SR Studio preservando proporção e suavidade."""\n    try:\n        if BRAND_LOGO.exists() and Image is not None and ImageTk is not None:\n            with Image.open(BRAND_LOGO) as src:\n                img=src.convert("RGBA").resize((int(size),int(size)),Image.Resampling.LANCZOS)\n            return ImageTk.PhotoImage(img, master=master)\n    except Exception:\n        pass\n    try:\n        raw=tk.PhotoImage(master=master,file=str(BRAND_LOGO))\n        scale=max(1,math.ceil(max(raw.width(),raw.height())/max(1,int(size))))\n        return raw.subsample(scale,scale)\n    except Exception:\n        return None\n\n'''
if 'BRAND_LOGO = ASSETS / "SR_logo.png"' not in text:
    if anchor not in text: raise SystemExit('ASSETS não localizado')
    text=text.replace(anchor,brand,1)

# Splash: deixa de desenhar SR em texto e passa a exibir a imagem oficial.
old='''        # O mesmo emblema "SR" da animação de atualização.\n        badge = tk.Label(card, text="SR", bg=BLUE, fg="white",\n                         font=("Segoe UI", 25, "bold"), width=4, height=1)\n        badge.pack(pady=(28,10))\n'''
new='''        # Logo oficial do SR Studio.\n        self.logo = _brand_photo(self.root, 78)\n        if self.logo is not None:\n            badge = tk.Label(card, image=self.logo, bg=CARD, bd=0, highlightthickness=0)\n        else:\n            badge = tk.Label(card, text="SR", bg=BLUE, fg="white",\n                             font=("Segoe UI", 25, "bold"), width=4, height=1)\n        badge.pack(pady=(22,8))\n'''
if old not in text: raise SystemExit('Bloco da logo do Splash não localizado')
text=text.replace(old,new,1)

# Menu: deixa de desenhar SR em texto e passa a usar a mesma imagem oficial.
old='''        # Emblema oficial do SR Studio 3.x: o mesmo usado na tela de atualização.\n        # Substitui a antiga imagem SR_logo.png no menu principal para unificar a identidade.\n        self.logo_source_img=None\n        self.logo_img=None\n        self.logo_label=tk.Label(brand,text="SR",bg=pal["BLUE"],fg="white",\n                                 font=("Segoe UI",22,"bold"),width=3,height=1,bd=0,relief="flat")\n        self.logo_label.pack(pady=(16,6))\n'''
new='''        # Logo oficial do projeto: mesma imagem usada na abertura.\n        self.logo_source_img=None\n        self.logo_img=_brand_photo(self, 58)\n        if self.logo_img is not None:\n            self.logo_label=tk.Label(brand,image=self.logo_img,bg=pal["SIDEBAR"],bd=0,highlightthickness=0)\n        else:\n            self.logo_label=tk.Label(brand,text="SR",bg=pal["BLUE"],fg="white",\n                                     font=("Segoe UI",22,"bold"),width=3,height=1,bd=0,relief="flat")\n        self.logo_label.pack(pady=(12,4))\n'''
if old not in text: raise SystemExit('Bloco da logo do menu não localizado')
text=text.replace(old,new,1)

# Ícone da janela principal.
old='''        self.title(f"SR Studio {APP_DISPLAY_VERSION}")\n        self.ui_settings = load_json(UI_SETTINGS_FILE, {})\n'''
new='''        self.title(f"SR Studio {APP_DISPLAY_VERSION}")\n        try:\n            if BRAND_ICON.exists(): self.iconbitmap(str(BRAND_ICON))\n        except Exception:\n            pass\n        try:\n            self.window_brand_icon=_brand_photo(self,64)\n            if self.window_brand_icon is not None: self.iconphoto(True,self.window_brand_icon)\n        except Exception:\n            self.window_brand_icon=None\n        self.ui_settings = load_json(UI_SETTINGS_FILE, {})\n'''
if old not in text: raise SystemExit('Inicialização da janela não localizada')
text=text.replace(old,new,1)

p.write_text(text,encoding='utf-8')

vpath=R/'version.json'
v=json.loads(vpath.read_text(encoding='utf-8'))
if channel=='stable':
    v.update(distribution_version='4.0.16-hybrid.stable3',product_version='4.0.16',channel='stable',release_label='Stable 3',updated_at='2026-08-14T11:17:00-03:00')
    display='4.0.16 • Stable 3'
    note='SR Studio 4.0.16 • Stable 3\nNova logo oficial aplicada na abertura, menu principal e ícone do aplicativo.\n'
else:
    v.update(distribution_version='4.0.16-hybrid.beta18',product_version='4.0.16',channel='beta',release_label='Beta 18',updated_at='2026-08-14T11:17:00-03:00')
    display='4.0.16 • Beta 18'
    note='SR Studio 4.0.16 • Beta 18\nSincronizada com Stable 3: nova logo oficial na abertura, menu principal e ícone do aplicativo.\n'
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text(note,encoding='utf-8')

# Encartes Studio mantém identificação coerente com o canal publicado.
js=R/'Encartes10_beta16.js'
if js.exists():
    s=js.read_text(encoding='utf-8')
    import re
    s,n=re.subn(r"A\.VERSION='4\.0\.16 • (?:Stable 2|Beta 17)'",f"A.VERSION='{display}'",s,count=1)
    if n==0:
        # tolera pacote Stable 2 em que o texto já esteja com outra etiqueta 4.0.16
        s,n=re.subn(r"A\.VERSION='4\.0\.16 • [^']+'",f"A.VERSION='{display}'",s,count=1)
    if n==0: raise SystemExit('Versão do Encartes10 não localizada')
    js.write_text(s,encoding='utf-8')

print('Logo oficial aplicada para',channel)
