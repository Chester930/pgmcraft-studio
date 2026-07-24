"""
Unit tests for Pass 13 Ultimate Perfection & Seal:
Module 1: README.md Complete Feature Matrix Verification
Module 2: CLI --quiet Flag Guard Verification
"""

import os
import pytest
from pgm_craft.cli import parse_args


def test_readme_feature_matrix_content():
    readme_path = "README.md"
    assert os.path.exists(readme_path)
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "v1.3.0 商業級" in content
    assert "剝洋蔥迭代分軌" in content
    assert "EBU R128" in content


def test_cli_quiet_flag():
    args = parse_args(["--quiet"])
    assert args.quiet is True

    args_normal = parse_args([])
    assert args_normal.quiet is False
