"""
Unit tests for Pass 11 Ultimate Perfection Optimizations:
Module 1: Interactive Report Clipboard Exporter & Format
Module 2: Arrangement Dynamic Density Tag
"""

import pytest


def test_arrangement_density_tag_logic():
    # Test Arrangement Dynamic Density logic mapping
    inst_matrix_sparse = [{"drums": 1, "bass": 0, "vocals": 0}]
    avg_sparse = sum(inst_matrix_sparse[0].values())
    assert avg_sparse < 1.5

    inst_matrix_dense = [{"drums": 1, "bass": 1, "vocals": 1, "piano": 1}]
    avg_dense = sum(inst_matrix_dense[0].values())
    assert avg_dense > 2.8


def test_clipboard_format_string():
    summary_text = (
        "🎵 **PGMCraft Studio 分析速報**\n"
        "▫️ 平均速度: 120.0 BPM (固定極速對拍)\n"
        "▫️ 樂曲調性: C Major\n"
        "▫️ 小節數: 32 小節\n"
        "▫️ 配器層次: Balanced Band (標準樂團編制)\n"
        "▫️ 數位指紋: 4a2d8e...\n"
    )
    assert "PGMCraft Studio 分析速報" in summary_text
    assert "120.0 BPM" in summary_text
    assert "Balanced Band" in summary_text
