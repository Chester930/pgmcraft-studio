"""
Unit tests for Package Zip builder and Tab 6 export renderer.
"""

import os
import zipfile
import tempfile
import pytest
from pgm_craft.packager import PGMProjectPackager


def test_build_zip_archive():
    packager = PGMProjectPackager()
    with tempfile.TemporaryDirectory() as temp_dir:
        pkg_dir = os.path.join(temp_dir, "pgm_project_package")
        os.makedirs(os.path.join(pkg_dir, "audio"), exist_ok=True)
        os.makedirs(os.path.join(pkg_dir, "midi"), exist_ok=True)

        with open(os.path.join(pkg_dir, "IMPORT_GUIDE.md"), "w", encoding="utf-8") as f:
            f.write("# Import Guide")

        with open(os.path.join(pkg_dir, "pgm_session.rpp"), "w", encoding="utf-8") as f:
            f.write("<REAPER_PROJECT>")

        zip_path = packager.build_zip_archive(pkg_dir)

        assert os.path.exists(zip_path)
        assert zip_path.endswith(".zip")

        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            assert any("IMPORT_GUIDE.md" in n for n in names)
            assert any("pgm_session.rpp" in n for n in names)
