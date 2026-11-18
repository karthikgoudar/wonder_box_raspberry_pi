"""run_wonderbox.sh: restart after a crash, stay closed after ESC (exit 0)."""

import os
import shutil
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(shutil.which("flock") is None, reason="needs flock (Linux)")


def _setup(tmp_path, exit_codes):
    """Copy the script next to a fake app that exits with the given codes in turn."""
    shutil.copy(os.path.join(ROOT, "run_wonderbox.sh"), tmp_path / "run_wonderbox.sh")
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    fake = tmp_path / "venv" / "bin" / "python"
    codes = " ".join(str(c) for c in exit_codes)
    fake.write_text(
        "#!/bin/bash\n"
        f"codes=({codes})\n"
        "n=$(cat runs 2>/dev/null || echo 0)\n"
        "echo $((n+1)) > runs\n"
        "exit ${codes[$n]}\n"
    )
    fake.chmod(0o755)
    return tmp_path


def _run(d, timeout=20):
    env = dict(os.environ, WONDERBOX_RESTART_PAUSE="0", WONDERBOX_LOCK=str(d / "lock"))
    return subprocess.run(["bash", str(d / "run_wonderbox.sh")], cwd=d, env=env, timeout=timeout)


def test_esc_close_is_not_restarted(tmp_path):
    d = _setup(tmp_path, [0])
    assert _run(d).returncode == 0
    assert (d / "runs").read_text().strip() == "1"
    assert "closed on purpose" in (d / "logs" / "app.log").read_text()


def test_crash_is_restarted_until_clean_exit(tmp_path):
    d = _setup(tmp_path, [1, 1, 0])
    assert _run(d).returncode == 0
    assert (d / "runs").read_text().strip() == "3"
    assert (d / "logs" / "app.log").read_text().count("crashed (exit code 1)") == 2


def test_second_copy_does_not_start(tmp_path):
    d = _setup(tmp_path, [0])
    holder = subprocess.Popen(["flock", str(d / "lock"), "sleep", "5"])
    try:
        time.sleep(0.3)
        assert _run(d).returncode == 0
        assert not (d / "runs").exists()  # the app was never started
        assert "already running" in (d / "logs" / "app.log").read_text()
    finally:
        holder.kill()
