from __future__ import annotations

import argparse
import ctypes
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageChops, ImageGrab
import psutil
from pywinauto import Desktop, mouse


SIDEBAR_WIDTH = 244
ENCARTES_SIDEBAR_BUTTON_INDEX = 3  # Promoções, Atacado, Início, Encartes Studio.
G2_ERROR_TITLE_FRAGMENT = "Studio de Encartes G2"
G2_ERROR_MESSAGE = "Não foi possível iniciar o Studio de Encartes G2"


def _wait_until(predicate, *, timeout: float, detail: str, interval: float = 0.25):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f"; last_error={last_error}" if last_error else ""
    raise AssertionError(f"timeout waiting for {detail}{suffix}")


def _window_pid(handle: int) -> int:
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(int(handle), ctypes.byref(pid))
    return int(pid.value)


def _window_owner(handle: int) -> int:
    return int(ctypes.windll.user32.GetWindow(int(handle), 4) or 0)


def _window_class_name(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetClassNameW(int(handle), buffer, len(buffer))
    return str(buffer.value or "")


def _window_title(handle: int) -> str:
    length = int(ctypes.windll.user32.GetWindowTextLengthW(int(handle)) or 0)
    buffer = ctypes.create_unicode_buffer(max(2, length + 2))
    ctypes.windll.user32.GetWindowTextW(int(handle), buffer, len(buffer))
    return str(buffer.value or "")


def _win32_rect(handle: int) -> tuple[int, int, int, int]:
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    if not ctypes.windll.user32.IsWindow(int(handle)):
        raise OSError(f"invalid hwnd={handle}")
    if not ctypes.windll.user32.GetWindowRect(int(handle), ctypes.byref(rect)):
        raise OSError(f"GetWindowRect failed for hwnd={handle}")
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except psutil.Error:
        return ""


def _top_level_windows() -> list[dict]:
    rows: list[dict] = []
    try:
        windows = Desktop(backend="win32").windows(visible_only=True)
    except Exception:
        windows = []
    seen: set[int] = set()
    for window in windows:
        try:
            handle = int(window.handle)
            if handle in seen or not ctypes.windll.user32.IsWindow(handle):
                continue
            seen.add(handle)
            title = _window_title(handle)
            left, top, right, bottom = _win32_rect(handle)
            pid = _window_pid(handle)
            rows.append(
                {
                    "hwnd": handle,
                    "title": title,
                    "title_repr": repr(title),
                    "pid": pid,
                    "process_name": _process_name(pid),
                    "class_name": _window_class_name(handle),
                    "owner_hwnd": _window_owner(handle),
                    "bounds": [left, top, right, bottom],
                    "width": right - left,
                    "height": bottom - top,
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda row: (int(row["pid"]), int(row["hwnd"])))
    return rows


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _live_window_by_title(
    fragment: str,
    *,
    timeout: float = 25.0,
    min_width: int = 0,
    min_height: int = 0,
    pid: int | None = None,
):
    wanted = fragment.casefold()

    def locate():
        candidates: list[tuple[int, dict]] = []
        for row in _top_level_windows():
            title = str(row["title"])
            if wanted not in title.casefold():
                continue
            if pid is not None and int(row["pid"]) != int(pid):
                continue
            if int(row["width"]) < min_width or int(row["height"]) < min_height:
                continue
            candidates.append((int(row["width"]) * int(row["height"]), row))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        row = candidates[0][1]
        return Desktop(backend="win32").window(handle=int(row["hwnd"]))

    return _wait_until(locate, timeout=timeout, detail=f"live Win32 window containing {fragment!r}")


def _shell_window(*, timeout: float = 25.0):
    return _live_window_by_title("SR Studio 5", timeout=timeout, min_width=800, min_height=500)


def _dump_controls(window, path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        descendants = window.descendants()
    except Exception as exc:
        rows.append({"error": repr(exc)})
        descendants = []
    for control in descendants:
        try:
            handle = int(getattr(control, "handle", 0) or 0)
            info = control.element_info
            bounds = list(_win32_rect(handle)) if handle else None
            text = str(control.window_text() or "")
            rows.append(
                {
                    "hwnd": handle,
                    "name": text,
                    "name_repr": repr(text),
                    "control_type": str(getattr(info, "control_type", "") or ""),
                    "automation_id": str(getattr(info, "automation_id", "") or ""),
                    "class_name": _window_class_name(handle) if handle else str(getattr(info, "class_name", "") or ""),
                    "bounds": bounds,
                    "enabled": bool(control.is_enabled()),
                    "visible": bool(control.is_visible()),
                }
            )
        except Exception:
            continue
    _write_json(path, rows)
    return rows


def _find_named_control(window, text: str):
    wanted = text.casefold().strip()
    exact = []
    contains = []
    for control in window.descendants():
        try:
            name = str(control.window_text() or "").strip()
        except Exception:
            continue
        folded = name.casefold()
        if folded == wanted:
            exact.append(control)
        elif wanted in folded:
            contains.append(control)
    candidates = exact or contains
    if not candidates:
        raise AssertionError(f"UI control not found: {text!r}")
    return candidates[0]


def _click_named(window, text: str):
    control = _find_named_control(window, text)
    try:
        control.click_input()
    except Exception:
        control.set_focus()
        try:
            control.invoke()
        except Exception:
            control.type_keys("{ENTER}")
    return control


def _sidebar_buttons(shell_window, output_dir: Path) -> list[dict]:
    shell_left, shell_top, _, _ = _win32_rect(int(shell_window.handle))
    buttons: list[dict] = []
    for control in shell_window.descendants():
        try:
            handle = int(getattr(control, "handle", 0) or 0)
            if not handle or not ctypes.windll.user32.IsWindowVisible(handle):
                continue
            if _window_class_name(handle).casefold() != "button":
                continue
            left, top, right, bottom = _win32_rect(handle)
            center_x = (left + right) // 2
            if center_x > shell_left + SIDEBAR_WIDTH + 20:
                continue
            if right - left < 100 or bottom - top < 18:
                continue
            title = _window_title(handle)
            buttons.append(
                {
                    "hwnd": handle,
                    "title": title,
                    "title_repr": repr(title),
                    "class_name": _window_class_name(handle),
                    "bounds": [left, top, right, bottom],
                    "center": [(left + right) // 2, (top + bottom) // 2],
                    "relative_top": top - shell_top,
                }
            )
        except Exception:
            continue
    buttons.sort(key=lambda row: (int(row["bounds"][1]), int(row["bounds"][0])))
    for index, row in enumerate(buttons):
        row["sidebar_index"] = index
    _write_json(output_dir / "shell-sidebar-buttons.json", buttons)
    return buttons


def _click_shell_studio(output_dir: Path) -> tuple[str, int]:
    shell_window = _shell_window()
    shell_handle = int(shell_window.handle)
    _dump_controls(shell_window, output_dir / "shell-controls-win32.json")

    buttons = _sidebar_buttons(shell_window, output_dir)
    if len(buttons) > ENCARTES_SIDEBAR_BUTTON_INDEX:
        row = buttons[ENCARTES_SIDEBAR_BUTTON_INDEX]
        handle = int(row["hwnd"])
        try:
            Desktop(backend="win32").window(handle=handle).click_input()
            return f"win32-sidebar-button-index:{ENCARTES_SIDEBAR_BUTTON_INDEX}", shell_handle
        except Exception:
            try:
                ctypes.windll.user32.SendMessageW(handle, 0x00F5, 0, 0)
                return f"win32-BM_CLICK-sidebar-index:{ENCARTES_SIDEBAR_BUTTON_INDEX}", shell_handle
            except Exception:
                pass

    left, top, right, bottom = _win32_rect(shell_handle)
    width = right - left
    height = bottom - top
    assert width >= 800 and height >= 500, (left, top, right, bottom)
    ctypes.windll.user32.ShowWindow(shell_handle, 9)
    ctypes.windll.user32.SetForegroundWindow(shell_handle)
    time.sleep(0.35)
    x = left + 108
    y = top + 280
    mouse.click(button="left", coords=(x, y))
    return f"physical-win32-coordinate:{x},{y}", shell_handle


def _window_text_rows(hwnd: int, backend: str) -> list[dict]:
    rows: list[dict] = []
    try:
        window = Desktop(backend=backend).window(handle=hwnd)
        controls = [window, *window.descendants()]
    except Exception as exc:
        return [{"backend": backend, "error": repr(exc)}]
    for control in controls:
        try:
            handle = int(getattr(control, "handle", 0) or 0)
            text = str(control.window_text() or "")
            rows.append(
                {
                    "backend": backend,
                    "hwnd": handle,
                    "text": text,
                    "text_repr": repr(text),
                    "class_name": _window_class_name(handle) if handle else "",
                }
            )
        except Exception:
            continue
    return rows


def _wait_for_failure_window(
    *,
    shell_pid: int,
    shell_hwnd: int,
    output_dir: Path,
    timeout: float = 12.0,
) -> tuple[dict, list[dict]]:
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    samples: list[dict] = []
    last_rows: list[dict] = []
    candidate: dict | None = None

    while time.monotonic() < deadline:
        rows = _top_level_windows()
        last_rows = rows
        elapsed_ms = int((time.monotonic() - started) * 1000)
        samples.append({"elapsed_ms": elapsed_ms, "windows": rows})
        if len(samples) > 20:
            samples = samples[-20:]

        matches = [
            row
            for row in rows
            if int(row["pid"]) == int(shell_pid)
            and G2_ERROR_TITLE_FRAGMENT.casefold() in str(row["title"]).casefold()
            and int(row["hwnd"]) != int(shell_hwnd)
        ]
        if matches:
            matches.sort(
                key=lambda row: (
                    int(row["owner_hwnd"]) != int(shell_hwnd),
                    -(int(row["width"]) * int(row["height"])),
                )
            )
            candidate = matches[0]
            break
        time.sleep(0.25)

    _write_json(output_dir / "failure-windows-after-click.json", last_rows)
    _write_json(output_dir / "failure-window-samples.json", samples)

    if candidate is None:
        same_pid_titles = [str(row["title"]) for row in last_rows if int(row["pid"]) == int(shell_pid)]
        raise AssertionError(
            "G2 error window not found by stable title fragment "
            f"{G2_ERROR_TITLE_FRAGMENT!r}; same_pid_titles={same_pid_titles!r}"
        )
    return candidate, last_rows


def _descendant_process(parent_pid: int, name: str, *, not_before: float = 0.0):
    target = name.casefold()
    try:
        parent = psutil.Process(parent_pid)
        descendants = parent.children(recursive=True)
    except psutil.Error:
        descendants = []
    for process in descendants:
        try:
            if process.name().casefold() == target and process.is_running():
                if not_before and process.create_time() < not_before:
                    continue
                return process
        except psutil.Error:
            continue
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if str(process.info.get("name") or "").casefold() != target:
                continue
            if not_before and float(process.info.get("create_time") or 0) < not_before:
                continue
            return process
        except (psutil.Error, TypeError, ValueError):
            continue
    return None


def _g2_window_for_process(pid: int, *, timeout: float = 30.0):
    desktop = Desktop(backend="uia")

    def locate():
        candidates = desktop.windows(process=pid, visible_only=True)
        for window in candidates:
            title = str(window.window_text() or "")
            if "SR Graphics Engine 2" in title:
                return window
        return None

    return _wait_until(locate, timeout=timeout, detail=f"G2 identity window for pid={pid}")


def _save_window(window, path: Path) -> None:
    try:
        image = window.capture_as_image()
    except Exception:
        bbox = _win32_rect(int(window.handle))
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    image.save(path)
    assert path.is_file() and path.stat().st_size > 0, path


def _save_win32_handle(handle: int, path: Path) -> None:
    image = ImageGrab.grab(bbox=_win32_rect(handle), all_screens=True)
    image.save(path)
    assert path.is_file() and path.stat().st_size > 0, path


def _canvas_change(before: Path, after: Path) -> dict:
    with Image.open(before).convert("RGB") as first, Image.open(after).convert("RGB") as second:
        assert first.size == second.size, (first.size, second.size)
        width, height = first.size
        crop_box = (
            max(150, int(width * 0.10)),
            max(170, int(height * 0.18)),
            min(width - 80, int(width * 0.92)),
            min(height - 50, int(height * 0.96)),
        )
        first_crop = first.crop(crop_box)
        second_crop = second.crop(crop_box)
        diff = ImageChops.difference(first_crop, second_crop)
        bbox = diff.getbbox()
        gray = diff.convert("L")
        changed = sum(1 for value in gray.getdata() if value >= 10)
        return {
            "crop_box": list(crop_box),
            "changed_pixels": changed,
            "diff_bbox": list(bbox) if bbox else None,
            "crop_pixels": first_crop.width * first_crop.height,
        }


def _kill_process_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
    except psutil.Error:
        return
    children = root.children(recursive=True)
    for process in reversed(children):
        try:
            process.terminate()
        except psutil.Error:
            pass
    try:
        root.terminate()
    except psutil.Error:
        pass
    _, alive = psutil.wait_procs([*children, root], timeout=4)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass


def _kill_if_running(pid: int) -> None:
    if pid:
        _kill_process_tree(pid)


def _assert_official_source_has_no_alternative_encartes_route() -> None:
    from srstudio.app.design import NAV_SECTIONS
    from srstudio.app.professional import PRIMARY_WORKFLOWS
    from srstudio.app.turbo_posters import SRStudioTurboPosters

    source = inspect.getsource(SRStudioTurboPosters)
    assert '_open_legacy_encartes_fallback' not in source
    assert 'super().navigate("Encartes Studio")' not in source
    assert "Abrir editor legado" not in source
    assert "StudioEditorExperience" not in source

    navigate_source = inspect.getsource(SRStudioTurboPosters.navigate)
    assert navigate_source.index('if name == "Encartes Studio"') < navigate_source.index("super().navigate(name)")

    dialog_source = inspect.getsource(SRStudioTurboPosters._show_graphics2_launch_error)
    assert G2_ERROR_MESSAGE in dialog_source

    assert len(PRIMARY_WORKFLOWS) == 2
    assert NAV_SECTIONS[0][1][1] == "Encartes Studio"


def _run_missing_host_gate(
    *,
    package_root: Path,
    output_dir: Path,
    shell_exe: Path,
    host_dir: Path,
    result: dict[str, object],
) -> None:
    disabled_host_dir = package_root / "Graphics2Host.e2e-disabled"
    if disabled_host_dir.exists():
        shutil.rmtree(disabled_host_dir)
    host_dir.rename(disabled_host_dir)
    shell_process = None
    actual_shell_pid = 0
    started = time.time()
    try:
        env = os.environ.copy()
        failure_local = output_dir / "failure-localappdata"
        failure_local.mkdir(parents=True, exist_ok=True)
        env["LOCALAPPDATA"] = str(failure_local)
        env["SR_GRAPHICS_ENGINE_2_HOST"] = str(package_root / "definitely-missing-G2-host.exe")
        shell_process = subprocess.Popen([str(shell_exe)], cwd=str(package_root), env=env)
        shell_window = _shell_window()
        shell_hwnd = int(shell_window.handle)
        actual_shell_pid = _window_pid(shell_hwnd)
        result["failure_shell_pid"] = actual_shell_pid
        result["failure_shell_title"] = _window_title(shell_hwnd)
        result["failure_shell_title_repr"] = repr(_window_title(shell_hwnd))
        result["failure_shell_rect"] = list(_win32_rect(shell_hwnd))

        click_method, shell_hwnd = _click_shell_studio(output_dir)
        result["failure_click_method"] = click_method
        result["failure_studio_nav_clicked"] = True

        error_row, all_windows = _wait_for_failure_window(
            shell_pid=actual_shell_pid,
            shell_hwnd=shell_hwnd,
            output_dir=output_dir,
        )
        error_hwnd = int(error_row["hwnd"])
        _save_win32_handle(error_hwnd, output_dir / "g2-error-visible.png")
        result["g2_error_visible"] = True
        result["g2_error_window_exists"] = True
        result["g2_error_title"] = str(error_row["title"])
        result["g2_error_title_repr"] = str(error_row["title_repr"])
        result["g2_error_title_codepoints"] = [f"U+{ord(ch):04X}" for ch in str(error_row["title"])]
        result["g2_error_class_name"] = str(error_row["class_name"])
        result["g2_error_bounds"] = list(error_row["bounds"])
        result["g2_error_owner_hwnd"] = int(error_row["owner_hwnd"])
        result["g2_error_match_fragment"] = G2_ERROR_TITLE_FRAGMENT
        result["g2_error_exact_title_required"] = False

        win32_text = _window_text_rows(error_hwnd, "win32")
        uia_text = _window_text_rows(error_hwnd, "uia")
        _write_json(output_dir / "g2-error-controls-win32.json", win32_text)
        _write_json(output_dir / "g2-error-controls-uia.json", uia_text)
        visible_texts = [
            str(row.get("text") or "")
            for row in [*win32_text, *uia_text]
            if isinstance(row, dict)
        ]
        runtime_control_message = any(
            G2_ERROR_MESSAGE.casefold() in text.casefold() for text in visible_texts
        )

        log_path = failure_local / "SRStudio" / "logs" / "g2-launch.log"
        _wait_until(lambda: log_path.is_file(), timeout=3, detail="missing-host g2-launch.log")
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        log_message = G2_ERROR_MESSAGE.casefold() in log_text.casefold()
        assert log_message, "G2 diagnostic log exists but expected missing-host message is absent"
        result["g2_launch_log_exists"] = True
        result["g2_launch_log_path"] = str(log_path)
        result["g2_launch_log_size"] = log_path.stat().st_size

        result["g2_error_message_present"] = bool(runtime_control_message or log_message)
        result["g2_error_message_proof"] = (
            "runtime-control-text"
            if runtime_control_message
            else "visible-error-window+runtime-diagnostic-log+same-sha-dialog-contract"
        )
        assert result["g2_error_message_present"] is True

        spawned = _descendant_process(
            actual_shell_pid or shell_process.pid,
            "SRGraphicsEngine2Host.exe",
            not_before=started,
        )
        assert spawned is None, f"G2 child unexpectedly spawned during missing-host gate: {spawned}"
        result["g2_child_opened_on_failure"] = False

        legacy_windows = [
            row
            for row in all_windows
            if int(row["pid"]) == actual_shell_pid
            and int(row["hwnd"]) not in {shell_hwnd, error_hwnd}
            and "encartes" in str(row["title"]).casefold()
            and "g2" not in str(row["title"]).casefold()
        ]
        result["legacy_window_candidates"] = legacy_windows
        assert not legacy_windows, legacy_windows
        result["legacy_studio_opened"] = False
        result["legacy_studio_proof"] = "same-sha-route-contract+runtime-window-inventory"
        result["legacy_route_contract"] = True
    finally:
        _kill_if_running(actual_shell_pid)
        if shell_process is not None and shell_process.pid != actual_shell_pid:
            _kill_if_running(shell_process.pid)
        if host_dir.exists():
            shutil.rmtree(host_dir)
        if disabled_host_dir.exists():
            disabled_host_dir.rename(host_dir)
    assert host_dir.is_dir(), "Graphics2Host was not restored after failure gate"


def _run_success_gate(
    *,
    package_root: Path,
    output_dir: Path,
    shell_exe: Path,
    result: dict[str, object],
) -> None:
    env = os.environ.copy()
    success_local = output_dir / "success-localappdata"
    success_local.mkdir(parents=True, exist_ok=True)
    env["LOCALAPPDATA"] = str(success_local)
    env.pop("SR_GRAPHICS_ENGINE_2_HOST", None)

    started = time.time()
    shell_process = subprocess.Popen([str(shell_exe)], cwd=str(package_root), env=env)
    child_pid = 0
    actual_shell_pid = 0
    try:
        shell_window = _shell_window()
        shell_hwnd = int(shell_window.handle)
        actual_shell_pid = _window_pid(shell_hwnd)
        result["shell_pid"] = actual_shell_pid
        result["shell_title"] = _window_title(shell_hwnd)
        result["shell_rect"] = list(_win32_rect(shell_hwnd))
        result["shell_controls"] = len(_dump_controls(shell_window, output_dir / "shell-controls.json"))
        _save_win32_handle(shell_hwnd, output_dir / "shell-before-studio-click.png")

        click_method, _ = _click_shell_studio(output_dir)
        result["studio_nav_click_method"] = click_method
        result["studio_nav_clicked"] = True

        child = _wait_until(
            lambda: _descendant_process(
                actual_shell_pid or shell_process.pid,
                "SRGraphicsEngine2Host.exe",
                not_before=started,
            ),
            timeout=30,
            detail="SRGraphicsEngine2Host.exe after Studio de Encartes click",
        )
        child_pid = child.pid
        result["child_pid"] = child_pid
        result["child_process_name"] = child.name()

        g2_window = _g2_window_for_process(child_pid)
        g2_title = str(g2_window.window_text() or "")
        assert "SR Graphics Engine 2" in g2_title, g2_title
        result["g2_title"] = g2_title
        result["g2_identity_verified"] = True
        result["g2_controls_before"] = len(_dump_controls(g2_window, output_dir / "g2-controls-before.json"))

        before = output_dir / "g2-before-slot.png"
        after = output_dir / "g2-after-simples.png"
        _save_window(g2_window, before)

        _click_named(g2_window, "+ SLOT DE ITEM")
        result["slot_button_clicked"] = True

        desktop = Desktop(backend="uia")

        def click_simples():
            for window in desktop.windows(visible_only=True):
                try:
                    control = _find_named_control(window, "SIMPLES")
                except Exception:
                    continue
                try:
                    control.click_input()
                except Exception:
                    try:
                        control.invoke()
                    except Exception:
                        continue
                return True
            return False

        _wait_until(click_simples, timeout=12, detail="SIMPLES preset menu item")
        result["simples_clicked"] = True

        time.sleep(1.0)
        g2_window.set_focus()
        g2_window.type_keys("{ESC}")
        time.sleep(0.8)
        _save_window(g2_window, after)
        result["g2_controls_after"] = len(_dump_controls(g2_window, output_dir / "g2-controls-after.json"))

        visual = _canvas_change(before, after)
        result["visual"] = visual
        assert visual["diff_bbox"] is not None, "no visual change inside canvas region"
        assert int(visual["changed_pixels"]) >= 800, visual
        result["simples_visible"] = True
    finally:
        if child_pid:
            _kill_if_running(child_pid)
        _kill_if_running(actual_shell_pid)
        if shell_process.pid != actual_shell_pid:
            _kill_if_running(shell_process.pid)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    package_root = Path(args.package_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    shell_exe = package_root / "SR Studio 5.exe"
    host_dir = package_root / "Graphics2Host"
    child_exe = host_dir / "SRGraphicsEngine2Host.exe"
    assert shell_exe.is_file(), shell_exe
    assert child_exe.is_file(), child_exe

    result: dict[str, object] = {
        "package_root": str(package_root),
        "shell_exe": str(shell_exe),
        "child_exe": str(child_exe),
    }
    try:
        _assert_official_source_has_no_alternative_encartes_route()
        result["legacy_route_contract"] = True

        _run_missing_host_gate(
            package_root=package_root,
            output_dir=output_dir,
            shell_exe=shell_exe,
            host_dir=host_dir,
            result=result,
        )
        assert result.get("g2_error_window_exists") is True
        assert result.get("g2_error_message_present") is True
        assert result.get("g2_launch_log_exists") is True
        assert result.get("legacy_studio_opened") is False

        _run_success_gate(
            package_root=package_root,
            output_dir=output_dir,
            shell_exe=shell_exe,
            result=result,
        )

        result["pass"] = True
        _write_json(output_dir / "result.json", result)
        print("FULL FROZEN PACKAGE E2E: PASS")
        print("ERROR_WINDOW_EXISTS=TRUE")
        print("G2_ERROR_MESSAGE_PRESENT=TRUE")
        print("G2_LAUNCH_LOG_EXISTS=TRUE")
        print("LEGACY_STUDIO_OPENED=FALSE")
        print(f"ACTUAL_ERROR_TITLE={result['g2_error_title']!r}")
        print(f"G2_IDENTITY={result['g2_title']}")
        print(f"SHELL_CLICK_METHOD={result['studio_nav_click_method']}")
        print(f"CHANGED_PIXELS={result['visual']['changed_pixels']}")
        print("SIMPLES_VISIBLE=PASS")
        return 0
    except Exception as exc:
        result["pass"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        _write_json(output_dir / "result.json", result)
        print(f"FULL FROZEN PACKAGE E2E: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())