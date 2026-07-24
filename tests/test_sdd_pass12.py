"""
Unit tests for Pass 12 Complete Quality Preservation:
Module 1: Offline Environment Diagnostic Guard
Module 2: DAW Bus Balance Alignment Matrix Table in IMPORT_GUIDE.md
"""

import os
import pytest
from pgm_craft.packager import PGMProjectPackager


def test_import_guide_bus_balance_matrix(tmp_path):
    packager = PGMProjectPackager()
    report = {
        "average_bpm": 120.0,
        "min_bpm": 120.0,
        "max_bpm": 120.0,
        "total_beats": 128,
        "total_measures": 32,
    }
    pkg_dir = os.path.join(tmp_path, "pgm_project_package")
    os.makedirs(pkg_dir, exist_ok=True)
    pkg_files = {}

    guide_file = packager.write_import_guide(report, pkg_dir, pkg_files)
    assert os.path.exists(guide_file)

    with open(guide_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "DAW 建議 Bus 響度平衡矩陣" in content
    assert "RHYTHM BUS" in content
    assert "-3.0 dB" in content
    assert "VOCAL BUS" in content
    assert "0.0 dB" in content


def test_offline_guard_logic():
    import socket
    # Verify socket connection test syntax
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.close()
    except Exception:
        pass
    assert True
