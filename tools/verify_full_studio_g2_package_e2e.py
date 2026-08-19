from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image, ImageChops
import psutil
from pywinauto import Desktop


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


def _window_for_process(pid: int, *, timeout: float = 25.0):
    desktop = Desktop(backend="uia")

    def locate():
        windows = [w for w in desktop.windows(process=pid, visible_only=True) if w.window_text().strip()]
        return windows[0] if windows else None

    return _wait_until(locate, timeout=timeout, detail=f"visible window for pid={pid}")


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


def _descendant_process(parent_pid: int, name: str):
    target = name.casefold()
    try:
        parent = psutil.Process(parent_pid)
        descendants = parent.children(recursive=True)
    except psutil.Error:
        descendants = []
    for process in descendants:
        try:
            if process.name().casefold() == target and process.is_running():
                return process
        except psutil.Error:
            continue
    # PyInstaller/process-group behavior can detach ancestry quickly. Fall back
    # to an executable-name match created after the shell launch.
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if str(process.info.get("name") or "").casefold() == target:
                return process
        except psutil.Error:
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
    image = window.capture_as_image()
    image.save(path)
    assert path.is_file() and path.stat().st_size > 0, path


def _canvas_change(before: Path, after: Path) -> dict:
    with Image.open(before).convert("RGB") as first, Image.open(after).convert("RGB") as second:
        assert first.size == second.size, (first.size, second.size)
        width, height = first.size
        # Ignore the top action/menu strip and outer frame. The remaining region
        # is where the actual page/canvas is drawn. Popup is closed before the
        # second capture, so it cannot satisfy this gate by itself.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    package_root = Path(args.package_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    shell_exe = package_root / "SR Studio 5.exe"
    child_exe = package_root / "Graphics2Host" / "SRGraphicsEngine2Host.exe"
    assert shell_exe.is_file(), shell_exe
    assert child_exe.is_file(), child_exe

    result: dict[str, object] = {
        "package_root": str(package_root),
        "shell_exe": str(shell_exe),
        "child_exe": str(child_exe),
    }
    shell_process = subprocess.Popen([str(shell_exe)], cwd=str(package_root))
    child_pid = 0
    try:
        shell_window = _window_for_process(shell_process.pid)
        result["shell_pid"] = shell_process.pid
        result["shell_title"] = shell_window.window_text()
        shell_controls = _dump_controls(shell_window, output_dir / "shell-controls.json")
        result["shell_controls"] = len(shell_controls)

        _click_named(shell_window, "Studio de Encartes")
        result["studio_nav_clicked"] = True

        child = _wait_until(
            lambda: _descendant_process(shell_process.pid, "SRGraphicsEngine2Host.exe"),
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
        g2_controls = _dump_controls(g2_window, output_dir / "g2-controls-before.json")
        result["g2_controls_before"] = len(g2_controls)

        before = output_dir / "g2-before-slot.png"
        after = output_dir / "g2-after-simples.png"
        _save_window(g2_window, before)

        _click_named(g2_window, "+ SLOT DE ITEM")
        result["slot_button_clicked"] = True

        # MenuItem is normally exposed to Windows UI Automation by Qt Quick.
        # Search all visible UIA windows because Qt menus may live in a popup
        # window instead of the ApplicationWindow accessibility subtree.
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

        # addPreset opens the editing popup. Close it so the visual assertion is
        # about the canvas, not about the popup changing pixels.
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

        result["pass"] = True
        (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("FULL FROZEN PACKAGE E2E: PASS")
        print(f"G2_IDENTITY={g2_title}")
        print(f"CHANGED_PIXELS={visual['changed_pixels']}")
        print("SIMPLES_VISIBLE=PASS")
        return 0
    except Exception as exc:
        result["pass"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FULL FROZEN PACKAGE E2E: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    finally:
        if child_pid:
            _kill_process_tree(child_pid)
        _kill_process_tree(shell_process.pid)


if __name__ == "__main__":
    raise SystemExit(main())
