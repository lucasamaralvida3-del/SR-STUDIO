from __future__ import annotations

import os


def enable_hidpi() -> bool:
    """Ativa DPI awareness antes da criação da primeira janela Tk no Windows."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        # Windows 10/11: Per Monitor V2. Evita que o Windows amplie a janela
        # inteira como bitmap, principal causa de texto/logo/ícones borrados.
        try:
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return True
        except Exception:
            pass

        # Windows 8.1+: Per Monitor.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return True
        except Exception:
            pass

        # Fallback antigo.
        try:
            user32.SetProcessDPIAware()
            return True
        except Exception:
            return False
    except Exception:
        return False
