from __future__ import annotations

import math
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from ui import studio5_visual as visual


# SR Studio 5.0 Beta 4 — Fidelidade Visual
# Esta camada mantém o núcleo da Beta 3 e substitui apenas o shell/dashboard.

ICON_BLUE = "#2E67E7"
ICON_SOFT = "#EAF1FF"
SIDEBAR_BG = "#123BA8"
SIDEBAR_ACTIVE = "#2B59D0"
SIDEBAR_HOVER = "#214BB8"
APP_BG = "#F3F6FB"
CARD = "#FFFFFF"
TEXT = "#15213B"
MUTED = "#77849A"
LINE = "#E4EAF3"


NAV_GROUPS = [
    ("PRINCIPAL", [
        ("home", "home", "Início"),
        ("studio5", "bolt", "Central 5.0"),
        ("encartes", "layout", "Encartes Studio"),
        ("products", "box", "Banco de Produtos"),
        ("studio5_sheets", "sheet", "Planilhas"),
        ("modelos", "layers", "Modelos"),
        ("studio5_validation", "check", "Validação"),
        ("studio5_export", "export", "Exportação"),
    ]),
    ("FERRAMENTAS SR", [
        ("sria", "spark", "SR IA"),
        ("builder", "wand", "Montador"),
        ("promo", "tag", "Promoções"),
        ("promo_list", "list", "Lista de Promoções"),
        ("atacado", "cart", "Atacado"),
        ("manual", "plus", "Geração Manual"),
    ]),
    ("OPERAÇÃO", [
        ("queue", "queue", "Fila"),
        ("reprint", "refresh", "Reimpressão"),
        ("historico", "clock", "Histórico"),
        ("config", "settings", "Configurações"),
    ]),
]


def _draw_icon(c: tk.Canvas, name: str, color: str, size: int = 22):
    """Ícones vetoriais desenhados no Canvas; não perdem definição com DPI."""
    c.delete("all")
    w = h = size + 8
    cx = w / 2
    cy = h / 2
    s = size / 24.0
    lw = max(1.6, 1.8 * s)

    def line(points, **kw):
        c.create_line(*[v * s + 4 for v in points], fill=color, width=lw,
                      capstyle=tk.ROUND, joinstyle=tk.ROUND, **kw)

    def rect(x1, y1, x2, y2, **kw):
        c.create_rectangle(x1*s+4, y1*s+4, x2*s+4, y2*s+4,
                           outline=color, width=lw, **kw)

    if name == "home":
        line([3, 11, 12, 4, 21, 11])
        line([6, 10, 6, 20, 18, 20, 18, 10])
        line([10, 20, 10, 14, 14, 14, 14, 20])
    elif name == "bolt":
        line([13, 2, 6, 13, 11, 13, 9, 22, 18, 10, 13, 10, 13, 2])
    elif name == "layout":
        rect(3, 4, 21, 20)
        line([3, 9, 21, 9]); line([9, 9, 9, 20])
    elif name == "box":
        line([12, 3, 21, 8, 12, 13, 3, 8, 12, 3])
        line([3, 8, 3, 17, 12, 22, 21, 17, 21, 8])
        line([12, 13, 12, 22])
    elif name == "sheet":
        rect(4, 3, 20, 21)
        line([4, 8, 20, 8]); line([4, 13, 20, 13]); line([4, 17, 20, 17])
        line([10, 8, 10, 21]); line([15, 8, 15, 21])
    elif name == "layers":
        line([12, 4, 21, 9, 12, 14, 3, 9, 12, 4])
        line([3, 13, 12, 18, 21, 13]); line([3, 17, 12, 22, 21, 17])
    elif name == "check":
        c.create_oval(4*s+4, 4*s+4, 20*s+4, 20*s+4, outline=color, width=lw)
        line([8, 12, 11, 15, 17, 9])
    elif name == "export":
        rect(4, 10, 20, 21)
        line([12, 16, 12, 3]); line([7, 8, 12, 3, 17, 8])
    elif name == "spark":
        line([12, 2, 14, 9, 21, 12, 14, 15, 12, 22, 10, 15, 3, 12, 10, 9, 12, 2])
    elif name == "wand":
        line([5, 20, 18, 7]); line([15, 4, 20, 9]);
        line([5, 4, 5, 8]); line([3, 6, 7, 6]); line([19, 15, 19, 20]); line([16.5, 17.5, 21.5, 17.5])
    elif name == "tag":
        line([3, 10, 10, 3, 20, 3, 21, 13, 14, 20, 3, 10])
        c.create_oval(14*s+4, 6*s+4, 17*s+4, 9*s+4, outline=color, width=lw)
    elif name == "list":
        for y in (6, 12, 18):
            c.create_oval(3*s+4, (y-1)*s+4, 5*s+4, (y+1)*s+4, fill=color, outline=color)
            line([8, y, 21, y])
    elif name == "cart":
        line([3, 5, 6, 5, 8, 16, 19, 16, 21, 8, 7, 8])
        c.create_oval(8*s+4, 18*s+4, 11*s+4, 21*s+4, outline=color, width=lw)
        c.create_oval(16*s+4, 18*s+4, 19*s+4, 21*s+4, outline=color, width=lw)
    elif name == "plus":
        c.create_oval(4*s+4, 4*s+4, 20*s+4, 20*s+4, outline=color, width=lw)
        line([12, 8, 12, 16]); line([8, 12, 16, 12])
    elif name == "queue":
        for y in (6, 12, 18): line([5, y, 19, y])
    elif name == "refresh":
        c.create_arc(4*s+4, 4*s+4, 20*s+4, 20*s+4, start=35, extent=265, style="arc", outline=color, width=lw)
        line([18, 4, 20, 9, 15, 8])
    elif name == "clock":
        c.create_oval(4*s+4, 4*s+4, 20*s+4, 20*s+4, outline=color, width=lw)
        line([12, 7, 12, 12, 16, 14])
    elif name == "settings":
        c.create_oval(8*s+4, 8*s+4, 16*s+4, 16*s+4, outline=color, width=lw)
        for a in range(0, 360, 45):
            r1, r2 = 7.0, 10.0
            x1 = 12 + math.cos(math.radians(a))*r1; y1 = 12 + math.sin(math.radians(a))*r1
            x2 = 12 + math.cos(math.radians(a))*r2; y2 = 12 + math.sin(math.radians(a))*r2
            line([x1, y1, x2, y2])
    elif name == "search":
        c.create_oval(5*s+4, 5*s+4, 16*s+4, 16*s+4, outline=color, width=lw)
        line([15, 15, 21, 21])
    elif name == "help":
        c.create_oval(4*s+4, 4*s+4, 20*s+4, 20*s+4, outline=color, width=lw)
        c.create_text(cx, cy-1, text="?", fill=color, font=("Segoe UI", max(9, int(size*.55)), "bold"))
    else:
        c.create_oval(8, 8, w-8, h-8, outline=color, width=lw)


class VectorIcon(tk.Canvas):
    def __init__(self, parent, name, color, size=22, bg=None):
        super().__init__(parent, width=size+8, height=size+8, bg=bg or parent.cget("bg"),
                         highlightthickness=0, bd=0)
        self.name = name; self.icon_color = color; self.icon_size = size
        _draw_icon(self, name, color, size)

    def recolor(self, color, bg=None):
        self.icon_color = color
        if bg is not None: self.configure(bg=bg)
        _draw_icon(self, self.name, color, self.icon_size)


class NavRow(tk.Frame):
    def __init__(self, parent, key, icon_name, label, command, pal, collapsed=False):
        super().__init__(parent, bg=pal["SIDEBAR"], bd=0, cursor="hand2")
        self.key=key; self.label_text=label; self.pal=pal; self.command=command
        self.selected=False; self.collapsed=collapsed
        self.indicator=tk.Frame(self,bg=pal["SIDEBAR"],width=4,bd=0)
        self.indicator.pack(side="left",fill="y")
        self.icon=VectorIcon(self,icon_name,"#DCE6FF",21,bg=pal["SIDEBAR"])
        self.icon.pack(side="left",padx=(11,9),pady=8)
        self.label=tk.Label(self,text=label,bg=pal["SIDEBAR"],fg="#DCE6FF",font=("Segoe UI",9,"bold"),anchor="w",cursor="hand2")
        if not collapsed:self.label.pack(side="left",fill="x",expand=True,padx=(0,8))
        for w in (self,self.icon,self.label,self.indicator):
            w.bind("<Button-1>",lambda e:self.command())
            w.bind("<Enter>",self._enter);w.bind("<Leave>",self._leave)

    def _paint(self,bg,fg,indicator):
        super().configure(bg=bg)
        self.indicator.configure(bg=indicator)
        self.icon.recolor(fg,bg)
        self.label.configure(bg=bg,fg=fg)

    def _enter(self,_=None):
        if not self.selected:self._paint(SIDEBAR_HOVER,"#FFFFFF",SIDEBAR_HOVER)
    def _leave(self,_=None):
        if not self.selected:self._paint(self.pal["SIDEBAR"],"#DCE6FF",self.pal["SIDEBAR"])

    def configure(self,cnf=None,**kw):
        bg=kw.pop("bg",None);fg=kw.pop("fg",None)
        kw.pop("activebackground",None);kw.pop("activeforeground",None);kw.pop("text",None);kw.pop("anchor",None)
        if bg is not None:
            self.selected = bg == self.pal.get("SIDEBAR_HOVER") or bg == SIDEBAR_ACTIVE
            target_bg = SIDEBAR_ACTIVE if self.selected else self.pal["SIDEBAR"]
            target_fg = "#FFFFFF" if self.selected else (fg or "#DCE6FF")
            self._paint(target_bg,target_fg,"#FFFFFF" if self.selected else target_bg)
        elif fg is not None:
            self.icon.recolor(fg);self.label.configure(fg=fg)
        if kw: super().configure(cnf or {},**kw)
        return self
    config=configure

    def set_collapsed(self,value):
        self.collapsed=bool(value)
        if self.collapsed:
            try:self.label.pack_forget()
            except Exception:pass
            self.icon.pack_configure(padx=(20,12))
        else:
            self.icon.pack_configure(padx=(11,9))
            if not self.label.winfo_ismapped():self.label.pack(side="left",fill="x",expand=True,padx=(0,8))


def _card(parent,pal,padx=0,pady=0):
    outer=tk.Frame(parent,bg="#DDE5F0",bd=0)
    inner=tk.Frame(outer,bg=pal["CARD"],bd=0,highlightbackground=pal["LINE"],highlightthickness=1)
    inner.pack(fill="both",expand=True,padx=(0,1),pady=(0,1))
    return outer,inner


def _button(parent,text,command,pal,primary=False):
    return tk.Button(parent,text=text,command=command,bg=pal["BLUE"] if primary else pal["CARD"],
                     fg="#FFFFFF" if primary else pal["TEXT"],activebackground=pal["BLUE2"] if primary else pal["LIGHT_BLUE"],
                     activeforeground="#FFFFFF" if primary else pal["BLUE"],relief="flat",bd=0,
                     highlightbackground=pal["BLUE"] if primary else pal["LINE"],highlightthickness=1,
                     padx=16,pady=9,font=("Segoe UI",9,"bold"),cursor="hand2")


def _build_layout(self):
    pal=visual._install_palette(self)
    pal.update({"APP_BG":APP_BG,"CARD":CARD,"TEXT":TEXT,"MUTED":MUTED,"LINE":LINE,
                "SIDEBAR":SIDEBAR_BG,"SIDEBAR_HOVER":SIDEBAR_ACTIVE,"TOPBAR":"#FFFFFF",
                "LIGHT_BLUE":"#EEF4FF","LIGHT_BLUE_TXT":"#2457C6","BLUE":"#1D4ED8","BLUE2":"#3B82F6"})
    self.palette=pal
    self.configure(bg=pal["APP_BG"])
    visual._configure_ttk(self)

    self.sidebar=tk.Frame(self,bg=pal["SIDEBAR"],width=88 if self.sidebar_collapsed else 264,bd=0)
    self.sidebar.pack(side="left",fill="y");self.sidebar.pack_propagate(False)

    brand=tk.Frame(self.sidebar,bg=pal["SIDEBAR"],height=112)
    brand.pack(fill="x",padx=16,pady=(8,2));brand.pack_propagate(False)
    self.logo_img=None
    try:
        module=sys.modules.get(self.__class__.__module__)
        self.logo_img=module._brand_photo(self,58) if module else None
    except Exception:pass
    logo_wrap=tk.Frame(brand,bg="#FFFFFF",bd=0,width=64,height=64)
    logo_wrap.pack(side="left" if not self.sidebar_collapsed else "top",pady=16);logo_wrap.pack_propagate(False)
    self.logo_label=tk.Label(logo_wrap,image=self.logo_img if self.logo_img else "",text="" if self.logo_img else "SR",
                             bg="#FFFFFF",fg=pal["BLUE"],font=("Segoe UI",18,"bold"),bd=0)
    self.logo_label.pack(expand=True)
    self.brand_text=tk.Label(brand,text="" if self.sidebar_collapsed else "SR Studio 5.0",bg=pal["SIDEBAR"],fg="#FFFFFF",
                             font=("Segoe UI Variable Display",14,"bold"),anchor="w")
    self.brand_subtitle=tk.Label(brand,text="" if self.sidebar_collapsed else "ENCARTES INTELLIGENCE",bg=pal["SIDEBAR"],fg="#9DB8F5",
                                 font=("Segoe UI",7,"bold"),anchor="w")
    if not self.sidebar_collapsed:
        textwrap=tk.Frame(brand,bg=pal["SIDEBAR"]);textwrap.pack(side="left",padx=(12,0))
        self.brand_text.master=textwrap; self.brand_subtitle.master=textwrap
        # recria para manter parent correto
        self.brand_text=tk.Label(textwrap,text="SR Studio 5.0",bg=pal["SIDEBAR"],fg="#FFFFFF",font=("Segoe UI Variable Display",14,"bold"),anchor="w")
        self.brand_text.pack(anchor="w")
        self.brand_subtitle=tk.Label(textwrap,text="ENCARTES INTELLIGENCE",bg=pal["SIDEBAR"],fg="#9DB8F5",font=("Segoe UI",7,"bold"),anchor="w")
        self.brand_subtitle.pack(anchor="w",pady=(2,0))

    nav_canvas=tk.Canvas(self.sidebar,bg=pal["SIDEBAR"],highlightthickness=0,bd=0)
    nav_canvas.pack(fill="both",expand=True)
    self.nav_holder=tk.Frame(nav_canvas,bg=pal["SIDEBAR"])
    nav_window=nav_canvas.create_window((0,0),window=self.nav_holder,anchor="nw")
    self.nav_holder.bind("<Configure>",lambda e:nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))
    nav_canvas.bind("<Configure>",lambda e:nav_canvas.itemconfigure(nav_window,width=e.width))

    self.nav_defs=[];self.nav_buttons={};self.nav_group_labels=[]
    for group,items in NAV_GROUPS:
        gl=tk.Label(self.nav_holder,text="" if self.sidebar_collapsed else group,bg=pal["SIDEBAR"],fg="#85A7F4",font=("Segoe UI",7,"bold"),anchor="w")
        gl.pack(fill="x",padx=24,pady=(13,5));self.nav_group_labels.append((gl,group))
        for key,icon,label in items:
            row=NavRow(self.nav_holder,key,icon,label,lambda k=key:self.navigate(k),pal,self.sidebar_collapsed)
            row.pack(fill="x",padx=12,pady=2)
            self.nav_buttons[key]=row;self.nav_defs.append((key,icon,label))

    foot=tk.Frame(self.sidebar,bg=pal["SIDEBAR"]);foot.pack(side="bottom",fill="x",padx=12,pady=10)
    self.footer_credit=tk.Label(foot,text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas",bg=pal["SIDEBAR"],fg="#9DB8F5",font=("Segoe UI",7))
    self.footer_credit.pack(pady=(0,6))
    self.collapse_btn=tk.Button(foot,text="»" if self.sidebar_collapsed else "«  Recolher menu",command=self.toggle_sidebar,bg="#0E3295",fg="#DCE6FF",
                                activebackground=SIDEBAR_ACTIVE,activeforeground="#FFFFFF",relief="flat",bd=0,font=("Segoe UI",8,"bold"),pady=8,cursor="hand2")
    self.collapse_btn.pack(fill="x")

    self.main=tk.Frame(self,bg=pal["APP_BG"]);self.main.pack(side="left",fill="both",expand=True)
    self.topbar=tk.Frame(self.main,bg="#FFFFFF",height=78,bd=0,highlightbackground=pal["LINE"],highlightthickness=1)
    self.topbar.pack(fill="x");self.topbar.pack_propagate(False)

    title_wrap=tk.Frame(self.topbar,bg="#FFFFFF");title_wrap.pack(side="left",padx=(26,22))
    tk.Label(title_wrap,text="SR Studio /",bg="#FFFFFF",fg=pal["MUTED"],font=("Segoe UI",7,"bold")).pack(anchor="w")
    self.page_title=tk.Label(title_wrap,text="Início",bg="#FFFFFF",fg=pal["TEXT"],font=("Segoe UI Variable Display",16,"bold"))
    self.page_title.pack(anchor="w",pady=(1,0))

    self.global_search_var=tk.StringVar()
    search_wrap=tk.Frame(self.topbar,bg="#F7F9FC",highlightbackground=pal["LINE"],highlightthickness=1,bd=0)
    search_wrap.pack(side="left",fill="x",expand=True,padx=(0,20),pady=15)
    si=VectorIcon(search_wrap,"search",pal["MUTED"],18,bg="#F7F9FC");si.pack(side="left",padx=(10,4))
    self.global_search_entry=tk.Entry(search_wrap,textvariable=self.global_search_var,bg="#F7F9FC",fg=pal["TEXT"],insertbackground=pal["TEXT"],
                                      relief="flat",bd=0,font=("Segoe UI",9))
    self.global_search_entry.pack(side="left",fill="x",expand=True,ipady=7,padx=(0,8))
    self.global_search_entry.bind("<Return>",lambda e:self.open_global_search())
    tk.Label(search_wrap,text="Ctrl + F",bg="#FFFFFF",fg=pal["MUTED"],font=("Segoe UI",7,"bold"),padx=7,pady=4).pack(side="right",padx=7)

    right=tk.Frame(self.topbar,bg="#FFFFFF");right.pack(side="right",padx=(0,16))
    help_wrap=tk.Frame(right,bg="#FFFFFF",width=34,height=34);help_wrap.pack(side="right",padx=6);help_wrap.pack_propagate(False)
    hi=VectorIcon(help_wrap,"help",pal["MUTED"],18,bg="#FFFFFF");hi.pack(expand=True)
    for w in (help_wrap,hi):w.bind("<Button-1>",lambda e:messagebox.showinfo("SR Studio 5.0","Central de ajuda e atalhos do SR Studio.",parent=self))

    profile=tk.Frame(right,bg="#F7F9FC",highlightbackground=pal["LINE"],highlightthickness=1,bd=0)
    profile.pack(side="right",padx=8,pady=14)
    avatar=tk.Canvas(profile,width=34,height=34,bg="#F7F9FC",highlightthickness=0)
    avatar.pack(side="left",padx=(7,8),pady=5);avatar.create_oval(2,2,32,32,fill=pal["BLUE"],outline="");avatar.create_text(17,17,text="SR",fill="#FFFFFF",font=("Segoe UI",8,"bold"))
    ptxt=tk.Frame(profile,bg="#F7F9FC");ptxt.pack(side="left",padx=(0,10))
    tk.Label(ptxt,text="Equipe SR",bg="#F7F9FC",fg=pal["TEXT"],font=("Segoe UI",8,"bold")).pack(anchor="w")
    tk.Label(ptxt,text="Produção",bg="#F7F9FC",fg=pal["MUTED"],font=("Segoe UI",7)).pack(anchor="w")

    self.health_frame=tk.Frame(right,bg="#FFFFFF");self.health_frame.pack(side="right",padx=5)
    self.health_labels={}
    for key in ("powerpoint","models","memory","backup"):
        d=tk.Label(self.health_frame,text="●",bg="#FFFFFF",fg=pal["MUTED"],font=("Segoe UI",8,"bold"));d.pack(side="left",padx=1);self.health_labels[key]=d
    self.version_label=tk.Label(right,text=f"v{getattr(sys.modules.get(self.__class__.__module__),'APP_DISPLAY_VERSION','5.0')}",bg="#FFFFFF",fg=pal["MUTED"],font=("Segoe UI",8,"bold"))
    self.version_label.pack(side="right",padx=6)

    self.content=tk.Frame(self.main,bg=pal["APP_BG"]);self.content.pack(fill="both",expand=True)
    cached_health=self.startup_cache.get("health",{}) if isinstance(getattr(self,"startup_cache",{}),dict) else {}
    if cached_health:
        self.after(80,lambda h=dict(cached_health):self._apply_health(h));self.after(10000,self.refresh_health_async)
    else:self.after(250,self.refresh_health_async)
    visual._style_nav(self,"home")


def _toggle_sidebar(self):
    self.sidebar_collapsed=not self.sidebar_collapsed
    self.sidebar.config(width=88 if self.sidebar_collapsed else 264)
    for row in self.nav_buttons.values():
        try:row.set_collapsed(self.sidebar_collapsed)
        except Exception:pass
    for widget,label in getattr(self,"nav_group_labels",[]):
        widget.config(text="" if self.sidebar_collapsed else label)
    try:
        if self.sidebar_collapsed:
            self.brand_text.pack_forget();self.brand_subtitle.pack_forget()
        else:
            # A reconstrução completa preserva alinhamento correto ao expandir.
            pass
    except Exception:pass
    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")
    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")
    try:self.ui_settings["sidebar_collapsed"]=self.sidebar_collapsed
    except Exception:pass


def _metric(parent,pal,icon,title,value,subtitle,accent):
    outer,card=_card(parent,pal)
    top=tk.Frame(card,bg=pal["CARD"]);top.pack(fill="x",padx=17,pady=(15,5))
    badge=tk.Canvas(top,width=40,height=40,bg=pal["CARD"],highlightthickness=0);badge.pack(side="left")
    badge.create_oval(2,2,38,38,fill="#EEF4FF",outline="")
    temp=tk.Canvas(badge,width=30,height=30,bg="#EEF4FF",highlightthickness=0);temp.place(x=5,y=5);_draw_icon(temp,icon,accent,18)
    tk.Label(top,text=title,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",8,"bold")).pack(side="left",padx=9)
    tk.Label(card,text=str(value),bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI Variable Display",24,"bold")).pack(anchor="w",padx=17)
    tk.Label(card,text=subtitle,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",8),wraplength=210,justify="left").pack(anchor="w",padx=17,pady=(0,15))
    return outer


def _show_home(self):
    try:self.clear_content()
    except Exception:
        for w in self.content.winfo_children():w.destroy()
    pal=self.palette;self.page_title.config(text="Início");visual._style_nav(self,"home")

    canvas=tk.Canvas(self.content,bg=pal["APP_BG"],highlightthickness=0)
    sb=ttk.Scrollbar(self.content,orient="vertical",command=canvas.yview);canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left",fill="both",expand=True);sb.pack(side="right",fill="y")
    frame=tk.Frame(canvas,bg=pal["APP_BG"]);win=canvas.create_window((0,0),window=frame,anchor="nw")
    frame.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")));canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))

    hero=tk.Canvas(frame,height=190,bg=pal["APP_BG"],highlightthickness=0)
    hero.pack(fill="x",padx=28,pady=(24,14))
    def draw_hero(_=None):
        hero.delete("bg")
        w=max(800,hero.winfo_width());h=190
        hero.create_rectangle(0,0,w,h,fill="#173FAE",outline="",tags="bg")
        hero.create_oval(w-330,-120,w+80,250,fill="#2458D6",outline="",tags="bg")
        hero.create_oval(w-230,-80,w+30,180,fill="#356DE8",outline="",tags="bg")
        hero.tag_lower("bg")
    hero.bind("<Configure>",draw_hero);draw_hero()
    hero.create_text(30,34,text="BEM-VINDO AO",fill="#AFC5FF",font=("Segoe UI",8,"bold"),anchor="nw")
    hero.create_text(30,56,text="SR Studio 5.0",fill="#FFFFFF",font=("Segoe UI Variable Display",25,"bold"),anchor="nw")
    hero.create_text(30,92,text="Crie, organize, valide e exporte suas campanhas em um só lugar.",fill="#DCE6FF",font=("Segoe UI",10),anchor="nw")
    actions=tk.Frame(hero,bg="#173FAE");hero.create_window(30,128,window=actions,anchor="nw")
    _button(actions,"+  Novo Projeto",lambda:(self.navigate("studio5"),self.after(100,lambda:(visual._select_studio5_tab(self,1),getattr(visual._find_studio5_panel(self),"new_project",lambda:None)()))),pal,True).pack(side="left")
    b2=_button(actions,"Importar Planilha",lambda:self.navigate("studio5_sheets"),pal,False);b2.config(bg="#FFFFFF",fg="#173FAE");b2.pack(side="left",padx=8)
    b3=_button(actions,"Abrir Encartes",lambda:self.navigate("encartes"),pal,False);b3.config(bg="#FFFFFF",fg="#173FAE");b3.pack(side="left")
    try:
        module=sys.modules.get(self.__class__.__module__);self._home_logo_hd=module._brand_photo(self,92) if module else None
        if self._home_logo_hd:hero.create_image(hero.winfo_reqwidth()-110,95,image=self._home_logo_hd,anchor="center")
    except Exception:pass

    try:
        from services import project_store
        from services.product_catalog import quality_summary
        from services.template_registry import list_templates
        projects=project_store.list_projects();summary=project_store.project_summary();quality=quality_summary();template_count=len(list_templates())
    except Exception:
        projects=[];summary={"active":0,"recoverable":0};quality={"total":0,"ok":0,"without_image":0,"low_resolution":0};template_count=0

    metrics=tk.Frame(frame,bg=pal["APP_BG"]);metrics.pack(fill="x",padx=28,pady=(0,14))
    for i in range(4):metrics.grid_columnconfigure(i,weight=1,uniform="m")
    specs=[
        ("layout","Projetos",summary.get("active",len(projects)),"ativos na Central 5.0",pal["BLUE"]),
        ("box","Produtos",quality.get("total",0),f"{quality.get('without_image',0)} sem imagem",pal["BLUE2"]),
        ("layers","Modelos",template_count,"modelos Canva / PPTX",pal.get("PURPLE_TXT","#7657D8")),
        ("refresh","Recuperação",summary.get("recoverable",0),"autosaves disponíveis",pal.get("GREEN_TXT","#159455")),
    ]
    for i,s in enumerate(specs):
        card=_metric(metrics,pal,*s);card.grid(row=0,column=i,sticky="nsew",padx=(0 if i==0 else 6,0 if i==3 else 6))

    grid=tk.Frame(frame,bg=pal["APP_BG"]);grid.pack(fill="both",expand=True,padx=28,pady=(0,20))
    grid.grid_columnconfigure(0,weight=1,uniform="dash");grid.grid_columnconfigure(1,weight=1,uniform="dash");grid.grid_columnconfigure(2,weight=1,uniform="dash")

    o1,recent=_card(grid,pal);o1.grid(row=0,column=0,sticky="nsew",padx=(0,7))
    tk.Label(recent,text="Projetos recentes",bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI Variable Display",12,"bold")).pack(anchor="w",padx=17,pady=(16,7))
    if projects:
        for p in projects[:4]:
            r=tk.Frame(recent,bg=pal["CARD"]);r.pack(fill="x",padx=17,pady=5)
            ic=VectorIcon(r,"layout",pal["BLUE"],17,bg="#EEF4FF");ic.pack(side="left",padx=(0,9))
            t=tk.Frame(r,bg=pal["CARD"]);t.pack(side="left",fill="x",expand=True)
            tk.Label(t,text=p.get("name") or "Projeto",bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI",8,"bold"),anchor="w").pack(fill="x")
            tk.Label(t,text=str(p.get("updated_at") or "")[:16].replace("T","  "),bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",7),anchor="w").pack(fill="x")
    else:
        tk.Label(recent,text="Nenhum projeto ainda.\nUse Novo Projeto para começar.",bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",9),justify="left").pack(anchor="w",padx=17,pady=18)

    o2,campaign=_card(grid,pal);o2.grid(row=0,column=1,sticky="nsew",padx=7)
    tk.Label(campaign,text="Produção rápida",bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI Variable Display",12,"bold")).pack(anchor="w",padx=17,pady=(16,8))
    for icon,label,desc,cmd in [
        ("sheet","Importar planilha","Reconheça sua estrutura e salve o perfil.",lambda:self.navigate("studio5_sheets")),
        ("layout","Abrir Encartes","Edite visualmente sua campanha.",lambda:self.navigate("encartes")),
        ("check","Validar projeto","Revise antes de exportar.",lambda:self.navigate("studio5_validation")),
    ]:
        r=tk.Frame(campaign,bg=pal["CARD"],cursor="hand2");r.pack(fill="x",padx=17,pady=5)
        ic=VectorIcon(r,icon,pal["BLUE"],17,bg="#EEF4FF");ic.pack(side="left",padx=(0,9))
        t=tk.Frame(r,bg=pal["CARD"]);t.pack(side="left",fill="x",expand=True)
        tk.Label(t,text=label,bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI",8,"bold"),anchor="w").pack(fill="x")
        tk.Label(t,text=desc,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",7),anchor="w").pack(fill="x")
        for w in (r,ic,t):w.bind("<Button-1>",lambda e,f=cmd:f())

    o3,quality_card=_card(grid,pal);o3.grid(row=0,column=2,sticky="nsew",padx=(7,0))
    tk.Label(quality_card,text="Qualidade do banco",bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI Variable Display",12,"bold")).pack(anchor="w",padx=17,pady=(16,8))
    total=int(quality.get("total",0) or 0);ok=int(quality.get("ok",0) or 0);pct=int(ok/total*100) if total else 0
    ring=tk.Canvas(quality_card,width=126,height=126,bg=pal["CARD"],highlightthickness=0);ring.pack(pady=2)
    ring.create_arc(12,12,114,114,start=90,extent=-359,style="arc",outline="#E7EDF6",width=11)
    ring.create_arc(12,12,114,114,start=90,extent=-359*pct/100,style="arc",outline=pal.get("GREEN_TXT","#159455"),width=11)
    ring.create_text(63,57,text=f"{pct}%",fill=pal["TEXT"],font=("Segoe UI Variable Display",17,"bold"));ring.create_text(63,78,text="completos",fill=pal["MUTED"],font=("Segoe UI",7,"bold"))
    legend=tk.Frame(quality_card,bg=pal["CARD"]);legend.pack(fill="x",padx=17,pady=(0,14))
    for name,val,color in [("Completos",ok,pal.get("GREEN_TXT","#159455")),("Sem imagem",quality.get("without_image",0),pal.get("ORANGE_TXT","#C87800")),("Baixa resolução",quality.get("low_resolution",0),pal.get("RED_TXT","#C43B3B"))]:
        r=tk.Frame(legend,bg=pal["CARD"]);r.pack(fill="x",pady=3);tk.Label(r,text="●",bg=pal["CARD"],fg=color,font=("Segoe UI",7)).pack(side="left");tk.Label(r,text=name,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",8)).pack(side="left",padx=5);tk.Label(r,text=str(val),bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI",8,"bold")).pack(side="right")


def install_studio5_fidelity(app_cls):
    if getattr(app_cls,"_SR5_FIDELITY_INSTALLED",False):return app_cls
    app_cls._SR5_FIDELITY_INSTALLED=True
    app_cls.build_layout=_build_layout
    app_cls.toggle_sidebar=_toggle_sidebar
    app_cls.show_home=_show_home
    return app_cls
