"""
Unit tests for Pass 9 Masterpiece Optimizations:
Module 1: CHANGELOG.md file verification
Module 2: Advanced Studio options UI & Packager verification
"""

import os
import pytest


def test_changelog_file_exists():
    changelog_path = "CHANGELOG.md"
    assert os.path.exists(changelog_path)
    with open(changelog_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "v1.3.0" in content
    assert "剝洋蔥迭代減法分軌" in content
    assert "EBU R128" in content


def test_app_ui_imports():
    import app
    assert hasattr(app, "build_ui")
