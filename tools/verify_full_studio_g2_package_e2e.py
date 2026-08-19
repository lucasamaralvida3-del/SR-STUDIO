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


def _wait_until(predicate, *, timeout: float, detail: str, interval: float = 0.25):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # diagnostics are emitted after timeout
            last_error = exc
        time.sleep(interval)
    suffix = f"; last_error={last_error}" if last_error else ""
    raise AssertionError(f"timeout waiting for {detail}{suffix}")


def _window_pid(handle: int) -> int:
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(int(handle), ctypes.byref(pid))
    return int(pid.value)


def _live_window_by_title(fragment: str, *, timeout: float = 25.0):
    """Resolve a live top-level Win32 window instead of retaining a PyInstaller/UIA wrapper."""

    wanted = fragment.casefold()

    def locate():
        try:
            windows = Desktop(backend="win32").windows(visible_only=True)
        except Exception:
            return None
        candidates = []
        for window in windows:
            try:
                title = str(window.window_text() or "").strip()
                handle = int(window.handle)
            except Exception:
                continue
            if wanted not in title.casefold() or not ctypes.windll.user32.IsWindow(handle):
                continue
            candidates.append((title, window))
        if not candidates:
            return None
        # Prefer the full professional shell over splash/auxiliary windows.
        candidates.sort(key=lambda item: ("professional" not in item[0].casefold(), len(item[0])))
        return candidates[0][1]

    return _wait_until(locate, timeout=timeout, detail=f"live Win32 window containing {fragment!r}")


def _shell_window(*, timeout: float = 25.0):
    return _live_window_by_title("SR Studio 5", timeout=timeout)


def _failure_window(*, timeout: float = 12.0):
    return _live_window_by_title("Studio de Encartes G2 — erro", timeout=timeout)


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


def _dump_controls(window, path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        descendants = window.descendants()
    except Exception as exc:
        rows.append({"error": repr(exc)})
        descendants = []
    for control in descendants:
        try:
            info = control.element_info
            rows.append(
                {
                    "name": str(control.window_text() or ""),
                    "control_type": str(getattr(info, "control_type", "") or ""),
                    "automation_id": str(getattr(info, "automation_id", "") or ""),
                    "class_name": str(getattr(info, "class_name", "") or ""),
                    "enabled": bool(control.is_enabled()),
                    "visible": bool(control.is_visible()),
                }
            )
        except Exception:
            continue
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _click_shell_studio(output_dir: Path) -> tuple[str, int]:
    """Click the real Tk sidebar button without calling navigate() directly."""

    shell_window = _shell_window()
    handle = int(shell_window.handle)
    _dump_controls(shell_window, output_dir / "shell-controls-win32.json")
    try:
        _click_named(shell_window, "Studio de Encartes")
        return "win32-name", handle
    except Exception:
        pass

    left, top, right, bottom = _win32_rect(handle)
    width = right - left
    height = bottom - top
    assert width >= 800 and height >= 500, (left, top, right, bottom)
    ctypes.windll.user32.ShowWindow(handle, 9)  # SW_RESTORE
    ctypes.windll.user32.SetForegroundWindow(handle)
    time.sleep(0.35)

    # The shell uses a fixed 244px sidebar. Encartes Studio is the second row
    # under WORKSPACE. This remains a real physical click on SR Studio 5.exe.
    x = left + min(122, max(70, width // 12))
    y = top + min(314, max(250, int(height * 0.39)))
    mouse.click(button="left", coords=(x, y))
    return f"physical-win32-coordinate:{x},{y}", handle


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
    from srstudio.app.turbo_posters import SRStudioTurboPosters

    source = inspect.getsource(SRStudioTurboPosters)
    assert '_open_legacy_encartes_fallback' not in source
    assert 'super().navigate("Encartes Studio")' not in source
    assert "Abrir editor legado" not in source
    assert "StudioEditorExperience" not in source


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
        actual_shell_pid = _window_pid(int(shell_window.handle))
        result["failure_shell_pid"] = actual_shell_pid
        result["failure_shell_title"] = str(shell_window.window_text() or "")
        result["failure_shell_rect"] = list(_win32_rect(int(shell_window.handle)))

        click_method, _ = _click_shell_studio(output_dir)
        result["failure_click_method"] = click_method
        result["failure_studio_nav_clicked"] = True

        error_window = _failure_window()
        _save_win32_handle(int(error_window.handle), output_dir / "g2-error-visible.png")
        result["g2_error_visible"] = True
        result["g2_error_title"] = str(error_window.window_text() or "")

        spawned = _descendant_process(
            actual_shell_pid or shell_process.pid,
            "SRGraphicsEngine2Host.exe",
            not_before=started,
        )
        assert spawned is None, f"G2 child unexpectedly spawned during missing-host gate: {spawned}"
        result["g2_child_opened_on_failure"] = False
        result["legacy_studio_opened"] = False
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
        actual_shell_pid = _window_pid(int(shell_window.handle))
        result["shell_pid"] = actual_shell_pid
        result["shell_title"] = str(shell_window.window_text() or "")
        result["shell_rect"] = list(_win32_rect(int(shell_window.handle)))
        result["shell_controls"] = len(_dump_controls(shell_window, output_dir / "shell-controls.json"))
        _save_win32_handle(int(shell_window.handle), output_dir / "shell-before-studio-click.png")

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
        assert result.get("g2_error_visible") is True
        assert result.get("legacy_studio_opened") is False

        _run_success_gate(
            package_root=package_root,
            output_dir=output_dir,
            shell_exe=shell_exe,
            result=result,
        )

        result["pass"] = True
        (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("FULL FROZEN PACKAGE E2E: PASS")
        print("G2_ERROR_VISIBLE=PASS")
        print("LEGACY_STUDIO_OPENED=FALSE")
        print(f"G2_IDENTITY={result['g2_title']}")
        print(f"SHELL_CLICK_METHOD={result['studio_nav_click_method']}")
        print(f"CHANGED_PIXELS={result['visual']['changed_pixels']}")
        print("SIMPLES_VISIBLE=PASS")
        return 0
    except Exception as exc:
        result["pass"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FULL FROZEN PACKAGE E2E: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
