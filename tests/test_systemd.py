from pathlib import Path
from instavault.systemd import (
    generate_service_content,
    generate_timer_content,
    install_systemd_units,
    uninstall_systemd_units,
)


def test_generate_service_content():
    content = generate_service_content(
        exec_path="/usr/local/bin/instavault",
        working_dir="/home/testuser",
        scan_input="/home/testuser/archives",
    )
    assert "ExecStart=/usr/local/bin/instavault scan --input '/home/testuser/archives'" in content
    assert "WorkingDirectory=/home/testuser" in content
    assert "Type=oneshot" in content


def test_generate_timer_content():
    content = generate_timer_content(on_calendar="daily")
    assert "OnCalendar=daily" in content
    assert "Persistent=true" in content


def test_install_and_uninstall_systemd_units(tmp_path):
    dest = tmp_path / "systemd" / "user"
    units = install_systemd_units(target_dir=dest, reload_daemon=False)

    service_file = dest / "instavault.service"
    timer_file = dest / "instavault.timer"

    assert service_file.exists()
    assert timer_file.exists()
    assert units["service"] == service_file
    assert units["timer"] == timer_file

    # Uninstall
    res = uninstall_systemd_units(target_dir=dest, reload_daemon=False)
    assert res is True
    assert not service_file.exists()
    assert not timer_file.exists()
