from __future__ import annotations

import math
import tkinter as tk


BG_TOP = "#071A3A"
BG_BOTTOM = "#0B2F78"
BLUE = "#2563EB"
BLUE2 = "#6EA8FF"
TEXT = "#F8FAFF"
MUTED = "#A8BCE0"
GREEN = "#69E1A4"
ORANGE = "#FFD07A"
TRACK = "#244A88"
LINE = "#2A5BAA"


def _hex_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(v))):02x}" for v in rgb)


def _mix(a: str, b: str, t: float):
    ar, ag, ab = _hex_rgb(a)
    br, bg, bb = _hex_rgb(b)
    return _rgb_hex((ar + (br-ar)*t, ag + (bg-ag)*t, ab + (bb-ab)*t))


def _draw_gradient(canvas: tk.Canvas, width: int, height: int):
    steps = 72
    for i in range(steps):
        t = i / max(1, steps-1)
        y0 = int(height * i / steps)
        y1 = int(height * (i+1) / steps) + 1
        canvas.create_rectangle(0, y0, width, y1, fill=_mix(BG_TOP, BG_BOTTOM, t), outline="", tags=("background",))


def _build_canvas(self, brand_photo, display_version: str):
    # A intro foi desenhada para ser curta e cinematográfica, sem atrasar o boot real.
    self.minimum_duration = {"Rápida": 2.35, "Normal": 3.45, "Estendida": 4.60}.get(self.duration_mode, 3.45)
    if self.reduced:
        self.minimum_duration = min(self.minimum_duration, 2.15)

    self.width = 720
    self.height = 460
    try:
        sw = self.root.winfo_screenwidth(); sh = self.root.winfo_screenheight()
        x = max(0, (sw-self.width)//2); y = max(0, (sh-self.height)//2)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
    except Exception:
        pass
    self.root.configure(bg=BG_TOP)

    c = tk.Canvas(self.root, width=self.width, height=self.height, bg=BG_TOP, highlightthickness=0, bd=0)
    c.pack(fill="both", expand=True)
    self.canvas = c
    _draw_gradient(c, self.width, self.height)

    # Malha e cartões decorativos: lembram o dashboard/editor sem simular um loading falso.
    for x in range(0, self.width, 72):
        c.create_line(x, 0, x, self.height, fill="#0E3774", width=1, tags=("background",))
    for y in range(0, self.height, 72):
        c.create_line(0, y, self.width, y, fill="#0E3774", width=1, tags=("background",))

    deco = [
        (24, 70, 196, 157), (524, 84, 698, 178),
        (37, 248, 185, 323), (542, 252, 684, 326),
    ]
    for i, (x0, y0, x1, y1) in enumerate(deco):
        c.create_rectangle(x0, y0, x1, y1, fill="#0A2860", outline="#19458F", width=1, tags=("deco", "background"))
        c.create_line(x0+14, y0+18, x1-18, y0+18, fill="#2A5BAA", width=3, tags=("deco", "background"))
        c.create_line(x0+14, y0+34, x1-48, y0+34, fill="#173D7E", width=2, tags=("deco", "background"))
        if i % 2 == 0:
            c.create_rectangle(x0+14, y1-30, x0+42, y1-13, fill="#1D4ED8", outline="", tags=("deco", "background"))
            c.create_rectangle(x0+48, y1-44, x0+76, y1-13, fill="#2E74EF", outline="", tags=("deco", "background"))
            c.create_rectangle(x0+82, y1-56, x0+110, y1-13, fill="#61A0FF", outline="", tags=("deco", "background"))

    # Partículas discretas; coordenadas determinísticas para manter o visual consistente.
    particle_positions = [
        (86, 48), (145, 204), (231, 63), (278, 343), (454, 52), (612, 43),
        (667, 219), (503, 350), (111, 372), (586, 377), (329, 42), (406, 392),
    ]
    self._particles = []
    for i, (x, y) in enumerate(particle_positions):
        r = 1 if i % 3 else 2
        pid = c.create_oval(x-r, y-r, x+r, y+r, fill="#5D93EF", outline="", tags=("particle", "background"))
        self._particles.append({"id": pid, "x": float(x), "y": float(y), "base_y": float(y), "speed": .18 + (i % 4)*.035, "phase": i*.65})

    # Halo central e órbita viva ao redor da marca.
    cx, cy = self.width//2, 137
    self._logo_center = (cx, cy)
    c.create_oval(cx-76, cy-76, cx+76, cy+76, outline="#1E56AE", width=1, tags=("hero",))
    c.create_oval(cx-61, cy-61, cx+61, cy+61, outline="#3676DD", width=1, tags=("hero",))
    self._halo_id = c.create_oval(cx-52, cy-52, cx+52, cy+52, outline="#6EA8FF", width=2, tags=("hero",))
    self._orbit_ids = []
    for _ in range(3):
        self._orbit_ids.append(c.create_oval(cx-3, cy-3, cx+3, cy+3, fill=BLUE2, outline="", tags=("hero",)))

    sizes = [66, 72, 78, 84, 90, 96]
    self._logo_frames = []
    for size in sizes:
        try:
            img = brand_photo(self.root, size)
        except Exception:
            img = None
        if img is not None:
            self._logo_frames.append(img)
    self._logo_index = 0
    if self._logo_frames:
        self.logo = self._logo_frames[0]
        self._logo_item = c.create_image(cx, cy+18, image=self.logo, tags=("hero", "logo"))
    else:
        self._logo_item = c.create_rectangle(cx-44, cy-44, cx+44, cy+44, fill=BLUE, outline="", tags=("hero", "logo"))
        c.create_text(cx, cy, text="SR", fill="white", font=("Segoe UI", 27, "bold"), tags=("hero", "logo"))

    # Linha luminosa que cruza o halo e dá sensação de energia, não de spinner.
    self._sweep_id = c.create_line(cx-70, cy+54, cx-42, cy-54, fill="#93BBFF", width=2, state="hidden", tags=("hero",))

    self._title_full = "SR STUDIO 5.0"
    self._title_item = c.create_text(cx, 242, text="", fill=TEXT, font=("Segoe UI", 25, "bold"), tags=("hero",))
    self._accent_item = c.create_line(cx, 264, cx, 264, fill=BLUE2, width=3, tags=("hero",))
    self._subtitle_item = c.create_text(cx, 283, text="ENCARTES INTELLIGENCE", fill="#7699CE", font=("Segoe UI", 9, "bold"), tags=("hero",))

    # Versão dentro de uma cápsula discreta.
    c.create_rectangle(cx-80, 302, cx+80, 329, fill="#0B2B68", outline="#275BAB", width=1, tags=("hero",))
    self._version_item = c.create_text(cx, 315, text=f"VERSÃO {display_version}", fill=MUTED, font=("Segoe UI", 8, "bold"), tags=("hero",))

    # Status real do boot, abaixo da parte cinematográfica.
    self._stage_item = c.create_text(86, 360, text=self.stage_var.get(), fill=TEXT, anchor="w", font=("Segoe UI", 9, "bold"))
    self._percent_item = c.create_text(634, 360, text="0%", fill=MUTED, anchor="e", font=("Segoe UI", 8, "bold"))
    self._progress_x0, self._progress_x1, self._progress_y = 86, 634, 380
    c.create_line(self._progress_x0, self._progress_y, self._progress_x1, self._progress_y, fill=TRACK, width=5, capstyle="round")
    self._progress_item = c.create_line(self._progress_x0, self._progress_y, self._progress_x0, self._progress_y, fill=BLUE2, width=5, capstyle="round")
    self._target_progress = 0.0
    self._shown_progress = 0.0

    # Cada ponto corresponde a uma verificação real executada por start_checks().
    self._step_nodes = []
    node_y = 396
    for i in range(len(self.STEPS)):
        x = self._progress_x0 + (self._progress_x1-self._progress_x0) * i / max(1, len(self.STEPS)-1)
        nid = c.create_oval(x-3, node_y-3, x+3, node_y+3, fill="#315D9D", outline="")
        self._step_nodes.append(nid)

    c.create_text(86, 427, text="INICIALIZAÇÃO SEGURA • LOCAL FIRST", fill="#7397CC", anchor="w", font=("Segoe UI", 7, "bold"))
    c.create_text(634, 427, text="Feito por Lucas", fill="#7397CC", anchor="e", font=("Segoe UI", 7))

    self.step_labels = []
    self._startup_anim_tick = 0
    self._animation_active = True
    self._ready = False
    self._animate_startup_badge()


def install_startup_splash_v5(splash_cls, brand_photo, display_version: str):
    """Aplica a intro 5.0 sem reescrever o boot funcional da classe original."""
    if getattr(splash_cls, "_SR5_SPLASH_INSTALLED", False):
        return splash_cls
    splash_cls._SR5_SPLASH_INSTALLED = True

    old_build = splash_cls._build
    old_update = splash_cls.update_step
    old_set_step = splash_cls._set_step
    old_complete = splash_cls.complete
    old_fade_in = splash_cls._fade_in
    old_fade_out = splash_cls._fade_out

    def build(self):
        try:
            _build_canvas(self, brand_photo, display_version)
        except Exception:
            # Fallback deliberado: uma falha estética nunca impede o Studio de abrir.
            self._sr5_splash_fallback = True
            old_build(self)

    def animate(self):
        if getattr(self, "_sr5_splash_fallback", False):
            try:
                return self.root.after(320, animate, self)
            except Exception:
                return
        if not getattr(self, "_animation_active", False):
            return
        try:
            c = self.canvas
            tick = int(getattr(self, "_startup_anim_tick", 0))
            self._startup_anim_tick = tick + 1
            reduced = bool(getattr(self, "reduced", False))

            # Logo: zoom real por frames + subida suave.
            if self._logo_frames:
                target_idx = len(self._logo_frames)-1 if reduced else min(len(self._logo_frames)-1, max(0, tick//4))
                if target_idx != self._logo_index:
                    self._logo_index = target_idx
                    self.logo = self._logo_frames[target_idx]
                    c.itemconfigure(self._logo_item, image=self.logo)
                cx, cy = self._logo_center
                y = cy if reduced else cy + max(0.0, 18.0 - tick*1.15)
                c.coords(self._logo_item, cx, y)

            # Órbita contínua e halo pulsante.
            cx, cy = self._logo_center
            for i, oid in enumerate(self._orbit_ids):
                a = (tick*.055 + i*2.094) % (math.pi*2)
                r = 67 + 3*math.sin(tick*.08+i)
                x = cx + math.cos(a)*r; y = cy + math.sin(a)*r
                c.coords(oid, x-3, y-3, x+3, y+3)
            pulse = 50 + 4*math.sin(tick*.10)
            c.coords(self._halo_id, cx-pulse, cy-pulse, cx+pulse, cy+pulse)

            # Título aparece letra a letra, depois a linha de identidade se abre.
            chars = len(self._title_full) if reduced else max(0, min(len(self._title_full), int((tick-10)/1.25)))
            c.itemconfigure(self._title_item, text=self._title_full[:chars])
            accent = 86 if reduced else max(0, min(86, (tick-22)*5))
            c.coords(self._accent_item, cx-accent, 264, cx+accent, 264)
            if tick > 22 or reduced:
                subtitle_t = min(1.0, (tick-22)/16) if not reduced else 1.0
                c.itemconfigure(self._subtitle_item, fill=_mix("#315B99", BLUE2, subtitle_t))

            # Sweep periódico de luz sobre a marca.
            phase = tick % 96
            if 30 <= phase <= 55 and not reduced:
                c.itemconfigure(self._sweep_id, state="normal")
                sx = cx-74 + (phase-30)*5.8
                c.coords(self._sweep_id, sx-18, cy+53, sx+10, cy-53)
            else:
                c.itemconfigure(self._sweep_id, state="hidden")

            # Partículas flutuam lentamente; não dependem do progresso.
            if not reduced:
                for p in self._particles:
                    p["x"] += p["speed"]
                    if p["x"] > self.width+4:
                        p["x"] = -4
                    y = p["base_y"] + math.sin(tick*.035+p["phase"])*5
                    r = 1.5
                    c.coords(p["id"], p["x"]-r, y-r, p["x"]+r, y+r)

            # Progresso suavizado seguindo o trabalho real.
            target = float(getattr(self, "_target_progress", 0.0))
            shown = float(getattr(self, "_shown_progress", 0.0))
            if reduced:
                shown = target
            else:
                delta = target-shown
                shown += delta*.16 if abs(delta) > .8 else delta
            shown = max(0.0, min(100.0, shown))
            self._shown_progress = shown
            px = self._progress_x0 + (self._progress_x1-self._progress_x0)*(shown/100.0)
            c.coords(self._progress_item, self._progress_x0, self._progress_y, px, self._progress_y)
            c.itemconfigure(self._percent_item, text=f"{int(round(shown))}%")

            delay = 80 if reduced else 34
            self.root.after(delay, self._animate_startup_badge)
        except Exception:
            # Uma frame perdida não deve interromper o boot.
            try: self.root.after(100, self._animate_startup_badge)
            except Exception: pass

    def set_step(self, index, status="active"):
        if getattr(self, "_sr5_splash_fallback", False):
            return old_set_step(self, index, status)
        try:
            for i, node in enumerate(self._step_nodes):
                if i < index:
                    color = GREEN
                elif i == index:
                    color = ORANGE if status == "warning" else GREEN if status == "ok" else BLUE2
                else:
                    color = "#315D9D"
                self.canvas.itemconfigure(node, fill=color)
        except Exception:
            pass

    def update_step(self, index, text, percent, warning=False):
        if getattr(self, "_sr5_splash_fallback", False):
            return old_update(self, index, text, percent, warning)
        if self.finished:
            return
        self.stage_var.set(text)
        self.percent_var.set(f"{int(percent)}%")
        self._target_progress = float(percent)
        try:
            self.canvas.itemconfigure(self._stage_item, text=text, fill=ORANGE if warning else TEXT)
        except Exception:
            pass
        self._set_step(index, "warning" if warning else "active")
        try: self.root.update_idletasks()
        except Exception: pass

    def fade_in(self, alpha=0.0):
        if getattr(self, "_sr5_splash_fallback", False):
            return old_fade_in(self, alpha)
        if not self.visible or self.reduced or self.finished:
            try: self.root.attributes("-alpha", 1.0)
            except Exception: pass
            return
        alpha = min(1.0, alpha + .075)
        try: self.root.attributes("-alpha", alpha)
        except Exception: return
        if alpha < 1.0:
            self.root.after(16, lambda: self._fade_in(alpha))

    def fade_out(self, alpha=1.0):
        if getattr(self, "_sr5_splash_fallback", False):
            return old_fade_out(self, alpha)
        if self.reduced or not self.visible:
            self._animation_active = False
            self.root.destroy()
            return
        alpha = max(0.0, alpha-.07)
        try:
            self.root.attributes("-alpha", alpha)
            self.canvas.move("hero", 0, -0.7)
        except Exception:
            try: self.root.destroy()
            except Exception: pass
            return
        if alpha <= 0:
            self._animation_active = False
            self.root.destroy()
        else:
            self.root.after(16, lambda: self._fade_out(alpha))

    def complete(self):
        if getattr(self, "_sr5_splash_fallback", False):
            return old_complete(self)
        if self.finished:
            return
        self._target_progress = 100.0
        self.percent_var.set("100%")
        self.stage_var.set("Tudo pronto • abrindo o Studio")
        try:
            self.canvas.itemconfigure(self._stage_item, text="Tudo pronto • abrindo o Studio", fill=GREEN)
            for node in self._step_nodes:
                self.canvas.itemconfigure(node, fill=GREEN)
            self.canvas.itemconfigure(self._progress_item, fill=GREEN)
        except Exception:
            pass
        self.finished = True
        self._ready = True

        if not self.visible:
            self._animation_active = False
            self.root.destroy()
            return

        import time
        elapsed = time.time()-self.started
        wait = max(420, int(max(0.0, self.minimum_duration-elapsed)*1000))
        self.root.after(wait, self._fade_out)

    splash_cls._build = build
    splash_cls._animate_startup_badge = animate
    splash_cls._set_step = set_step
    splash_cls.update_step = update_step
    splash_cls._fade_in = fade_in
    splash_cls._fade_out = fade_out
    splash_cls.complete = complete
    return splash_cls
