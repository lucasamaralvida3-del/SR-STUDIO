"""The frozen-host gate must survive Qt events during a slow editor startup."""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")


def test_smoke_closes_even_if_startup_processes_the_first_quit_timer(tmp_path):
    script = textwrap.dedent('''
        import sys
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtTest import QTest
        from srstudio.graphics2 import release_smoke as smoke
        launch = smoke.launch_qt_quick_editor
        watchdogs = []
        def slow_launch(*args, **kwargs):
            # Font registration/preview generation can process events before
            # launch_qt_quick_editor reaches app.exec().
            QTest.qWait(1200)
            watchdog = QTimer()
            watchdog.setSingleShot(True)
            watchdog.timeout.connect(lambda: QGuiApplication.instance().exit(9))
            # Hosted Windows runners may spend several seconds compiling QML.
            # This watchdog detects a hung event loop, not a startup budget.
            watchdog.start(15000)
            watchdogs.append(watchdog)
            return launch(*args, **kwargs)
        smoke.launch_qt_quick_editor = slow_launch
        result = smoke.run_release_smoke(sys.argv[1])
        assert result['ok'] and result['editor_exit_code'] == 0
    ''')
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
    completed = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                               env=env, text=True, capture_output=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr
