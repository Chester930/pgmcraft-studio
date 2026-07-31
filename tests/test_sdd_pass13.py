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

    assert "v2.0.0" in content or "v1.3.0" in content
    assert "PGMCraft Studio" in content
    assert "Behavior Tree" in content


def test_cli_quiet_flag():
    args = parse_args(["--quiet"])
    assert args.quiet is True

    args_normal = parse_args([])
    assert args_normal.quiet is False


def test_cli_max_workers_flag():
    args = parse_args(["--batch-dir", "music_files", "--max-workers", "2"])
    assert args.max_workers == 2

    args_default = parse_args([])
    assert args_default.max_workers == 4


def test_cli_target_stage_module3_flag():
    args = parse_args(["--audio", "sample_test.wav", "--target-stage", "module3"])
    assert args.target_stage == "module3"


def test_app_exposes_module3_stage_choice():
    with open("app.py", "r", encoding="utf-8") as f:
        source = f.read()

    assert 'with gr.TabItem("🎯 節奏定位")' in source
    assert "def process_module3_click_test" in source
    assert "module3_start_btn.click" in source
    assert "module3_candidate_sources_chk" in source
    assert "module3_candidate_sources" in source
    assert '("Module 3: 節拍候選可信度合成 + Click 手動測試", "module3")' in source
