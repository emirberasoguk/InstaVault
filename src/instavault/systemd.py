from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict, Optional

DEFAULT_USER_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"


def get_default_exec() -> str:
    which_bin = shutil.which("instavault")
    if which_bin:
        return which_bin
    return f"{sys.executable} -m instavault"


def generate_service_content(
    exec_path: Optional[str] = None,
    working_dir: Optional[str | Path] = None,
    scan_input: Optional[str] = None,
) -> str:
    bin_cmd = exec_path or get_default_exec()
    work_dir = str(working_dir or Path.home())
    scan_args = f" --input '{scan_input}'" if scan_input else ""

    return f"""[Unit]
Description=InstaVault Instagram Archive Ingest Service
After=network.target

[Service]
Type=oneshot
ExecStart={bin_cmd} scan{scan_args}
WorkingDirectory={work_dir}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def generate_timer_content(on_calendar: str = "daily") -> str:
    return f"""[Unit]
Description=InstaVault Ingest Daily Timer

[Timer]
OnCalendar={on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""


def install_systemd_units(
    target_dir: Optional[Path] = None,
    exec_path: Optional[str] = None,
    working_dir: Optional[str | Path] = None,
    scan_input: Optional[str] = None,
    on_calendar: str = "daily",
    reload_daemon: bool = True,
) -> Dict[str, Path]:
    dest_dir = Path(target_dir).expanduser().resolve() if target_dir else DEFAULT_USER_SYSTEMD_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    service_file = dest_dir / "instavault.service"
    timer_file = dest_dir / "instavault.timer"

    service_content = generate_service_content(
        exec_path=exec_path,
        working_dir=working_dir,
        scan_input=scan_input,
    )
    timer_content = generate_timer_content(on_calendar=on_calendar)

    service_file.write_text(service_content, encoding="utf-8")
    timer_file.write_text(timer_content, encoding="utf-8")

    if reload_daemon and shutil.which("systemctl"):
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass

    return {
        "service": service_file,
        "timer": timer_file,
    }


def uninstall_systemd_units(
    target_dir: Optional[Path] = None,
    reload_daemon: bool = True,
) -> bool:
    dest_dir = Path(target_dir).expanduser().resolve() if target_dir else DEFAULT_USER_SYSTEMD_DIR
    service_file = dest_dir / "instavault.service"
    timer_file = dest_dir / "instavault.timer"

    removed = False
    for f in (service_file, timer_file):
        if f.exists():
            f.unlink()
            removed = True

    if reload_daemon and shutil.which("systemctl"):
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass

    return removed
