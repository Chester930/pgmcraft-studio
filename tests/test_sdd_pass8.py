"""
Unit tests for Pass 8 Grand Final Optimizations:
Module 1: PGMProjectPackager.get_package_tree_markdown
Module 2: PGMProjectPackager.clean_temp_files
"""

import os
import pytest
from pgm_craft.packager import PGMProjectPackager


def test_package_tree_markdown(tmp_path):
    packager = PGMProjectPackager()
    # Create test package structure
    pkg_dir = os.path.join(tmp_path, "pgm_project_package")
    audio_dir = os.path.join(pkg_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    with open(os.path.join(audio_dir, "test.wav"), "w") as f:
        f.write("dummy audio")

    tree_md = packager.get_package_tree_markdown(pkg_dir)
    assert "pgm_project_package" in tree_md
    assert "audio" in tree_md
    assert "test.wav" in tree_md


def test_clean_temp_files(tmp_path):
    packager = PGMProjectPackager()
    temp_file = os.path.join(tmp_path, "test.tmp")
    with open(temp_file, "w") as f:
        f.write("temp data")

    cleaned = packager.clean_temp_files(str(tmp_path))
    assert cleaned == 1
    assert not os.path.exists(temp_file)
