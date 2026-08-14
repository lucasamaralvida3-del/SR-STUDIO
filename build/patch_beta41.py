from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FID = ROOT / 'src' / 'sr_studio' / 'ui' / 'studio5_fidelity.py'
MAIN = ROOT / 'src' / 'sr_studio' / 'SR_Studio_Gerador.py'
ENC = ROOT / 'src' / 'sr_studio' / 'Encartes13_fidelity.js'


def replace_once(text, old, new, label):
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'Âncora não encontrada: {label}')
    return text.replace(old, new, 1)


def patch_fidelity():
    text = FID.read_text(encoding='utf-8-sig')

    text = replace_once(
        text,
        '        self.icon=VectorIcon(self,icon_name,"#DCE6FF",21,bg=pal["SIDEBAR"])\n        self.icon.pack(side="left",padx=(11,9),pady=8)\n',
        '        self.icon=VectorIcon(self,icon_name,"#DCE6FF",22,bg=pal["SIDEBAR"])\n        self.icon.pack(side="left",padx=(11,9),pady=5)\n',
        'ícones laterais compactos e nítidos',
    )

    text = replace_once(
        text,
        '    brand=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],height=112)\n    brand.pack(fill="x",padx=16,pady=(8,2));brand.pack_propagate(False)\n',
        '    brand=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],height=94)\n    brand.pack(fill="x",padx=16,pady=(5,0));brand.pack_propagate(False)\n',
        'altura da marca lateral',
    )

    old_nav = '''    nav_canvas=tk.Canvas(self.sidebar,bg=pal["SIDEBAR"],highlightthickness=0,bd=0)\n    nav_canvas.pack(fill="both",expand=True)\n    self.nav_holder=tk.Frame(nav_canvas,bg=pal["SIDEBAR"])\n    nav_window=nav_canvas.create_window((0,0),window=self.nav_holder,anchor="nw")\n    self.nav_holder.bind("<Configure>",lambda e:nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))\n    nav_canvas.bind("<Configure>",lambda e:nav_canvas.itemconfigure(nav_window,width=e.width))\n'''
    new_nav = '''    nav_wrap=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],bd=0)\n    nav_wrap.pack(fill="both",expand=True)\n    nav_canvas=tk.Canvas(nav_wrap,bg=pal["SIDEBAR"],highlightthickness=0,bd=0)\n    nav_scroll=ttk.Scrollbar(nav_wrap,orient="vertical",command=nav_canvas.yview)\n    nav_canvas.configure(yscrollcommand=nav_scroll.set)\n    nav_canvas.pack(side="left",fill="both",expand=True)\n    nav_scroll.pack(side="right",fill="y")\n    self.nav_canvas=nav_canvas;self.nav_scroll=nav_scroll\n    self.nav_holder=tk.Frame(nav_canvas,bg=pal["SIDEBAR"])\n    nav_window=nav_canvas.create_window((0,0),window=self.nav_holder,anchor="nw")\n    self.nav_holder.bind("<Configure>",lambda e:nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))\n    nav_canvas.bind("<Configure>",lambda e:nav_canvas.itemconfigure(nav_window,width=e.width))\n    def _scroll_nav(event):\n        try:\n            direction=-1 if getattr(event,"delta",0)>0 else 1\n            nav_canvas.yview_scroll(direction,"units")\n        except Exception:pass\n        return "break"\n    nav_canvas.bind("<MouseWheel>",_scroll_nav)\n    self.nav_holder.bind("<MouseWheel>",_scroll_nav)\n'''
    text = replace_once(text, old_nav, new_nav, 'menu com scrollbar')

    text = replace_once(
        text,
        '        gl.pack(fill="x",padx=24,pady=(13,5));self.nav_group_labels.append((gl,group))\n',
        '        gl.pack(fill="x",padx=24,pady=(8,3));self.nav_group_labels.append((gl,group))\n        gl.bind("<MouseWheel>",_scroll_nav)\n',
        'grupos compactos',
    )

    text = replace_once(
        text,
        '            row.pack(fill="x",padx=12,pady=2)\n            self.nav_buttons[key]=row;self.nav_defs.append((key,icon,label))\n',
        '            row.pack(fill="x",padx=12,pady=0)\n            for _w in (row,row.icon,row.label,row.indicator):_w.bind("<MouseWheel>",_scroll_nav)\n            self.nav_buttons[key]=row;self.nav_defs.append((key,icon,label))\n',
        'linhas do menu compactas',
    )

    text = replace_once(
        text,
        '    foot=tk.Frame(self.sidebar,bg=pal["SIDEBAR"]);foot.pack(side="bottom",fill="x",padx=12,pady=10)\n',
        '    foot=tk.Frame(self.sidebar,bg=pal["SIDEBAR"]);foot.pack(side="bottom",fill="x",padx=12,pady=5)\n',
        'rodapé do menu compacto',
    )

    marker = '    visual._style_nav(self,"home")\n'
    enhanced = '''    visual._style_nav(self,"home")\n    # Garante que o item ativo fique sempre acessível, inclusive em telas menores.\n    self.after_idle(lambda: nav_canvas.yview_moveto(0.0))\n'''
    text = replace_once(text, marker, enhanced, 'posição inicial do menu')
    FID.write_text(text, encoding='utf-8')


def patch_review():
    text = MAIN.read_text(encoding='utf-8-sig')
    old = '''        self.build(); self.refresh_tree(); self.update_counter()\n        if focus_job_id is not None and self.tree.exists(str(focus_job_id)):\n            self.tree.selection_set(str(focus_job_id));self.tree.see(str(focus_job_id));self.details()\n'''
    new = '''        self.build()\n        # Beta 4.1: a Treeview precisa receber a primeira carga depois de ser mapeada.\n        # Em alguns PCs/DPIs, inserir tudo antes do primeiro idle deixava a tabela visualmente vazia\n        # até o usuário clicar em um filtro ou opção da tela.\n        self.update_idletasks()\n        self._initial_focus_job_id=focus_job_id\n        self._refresh_review_initial()\n        self.after_idle(self._refresh_review_initial)\n        self.after(90,self._refresh_review_initial)\n'''
    text = replace_once(text, old, new, 'inicialização da revisão')

    anchor = '    def build(self):\n'
    method = '''    def _refresh_review_initial(self):\n        try:\n            self.refresh_tree()\n            visible=self.visible_jobs()\n            target=getattr(self,"_initial_focus_job_id",None)\n            iid=str(target) if target is not None else (str(visible[0].get("id")) if visible else "")\n            if iid and self.tree.exists(iid):\n                if not self.tree.selection():self.tree.selection_set(iid)\n                self.tree.focus(iid);self.tree.see(iid)\n                self.details()\n            self.update_counter()\n            self.tree.update_idletasks()\n        except (tk.TclError,AttributeError):\n            pass\n\n    def build(self):\n'''
    # somente dentro da classe ReviewWindow: usa a ocorrência logo após o bloco recém-alterado
    pos = text.find(new)
    if pos < 0: raise SystemExit('Bloco ReviewWindow não localizado após patch')
    pos2 = text.find(anchor, pos)
    if pos2 < 0: raise SystemExit('Método build da ReviewWindow não localizado')
    text = text[:pos2] + method + text[pos2+len(anchor):]

    old_end = '''        restore=[x for x in selected if self.tree.exists(x)]\n        if restore:self.tree.selection_set(restore)\n        self.update_counter()\n'''
    new_end = '''        restore=[x for x in selected if self.tree.exists(x)]\n        if restore:self.tree.selection_set(restore)\n        self.update_counter()\n        try:self.tree.update_idletasks()\n        except tk.TclError:pass\n'''
    text = replace_once(text, old_end, new_end, 'repintura da tabela de revisão')
    MAIN.write_text(text, encoding='utf-8')


def patch_encartes_version():
    text = ENC.read_text(encoding='utf-8-sig')
    text = text.replace("A.VERSION='5.0.0 • Beta 4';", "A.VERSION='5.0.0 • Beta 4.1';")
    text = text.replace("assets/SR_logo.png?v=5.0.0-beta4", "assets/SR_logo.png?v=5.0.0-beta4.1")
    text = text.replace("dataset.srFidelity='beta4'", "dataset.srFidelity='beta41'")
    text = text.replace("Fidelidade Visual Beta 4 ativa.", "Fidelidade Visual Beta 4.1 ativa.")
    ENC.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    patch_fidelity()
    patch_review()
    patch_encartes_version()
    print('BETA41_PATCH_OK')
