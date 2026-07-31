"""
Frontend four-block narrative (user-directed restructure):
音色分軌 (existing) -> 🎯 節奏定位 (renamed from 自動節拍器, Block 1: bars +
beats + click) -> 🎵 和弦簡譜 (Block 2: chord lead sheet, placeholder) ->
📦 DAW 素材包 (Block 3: full DAW-importable package integrating Block 1 + 2 +
per-track MIDI transcription, placeholder).

Block 2/3 have no backend wired yet -- this only locks in the tab skeleton
and ordering per the user's explicit "先建立劃定區塊，內容區是空的沒關係"
instruction.
"""

from pathlib import Path

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_block1_renamed_from_自動節拍器():
    assert 'with gr.TabItem("🎯 節奏定位")' in APP_SOURCE
    assert "自動節拍器" not in APP_SOURCE


def test_block2_and_block3_placeholder_tabs_exist():
    assert 'with gr.TabItem("🎵 和弦簡譜")' in APP_SOURCE
    assert 'with gr.TabItem("📦 DAW 素材包")' in APP_SOURCE
    assert "開發中，尚未接上後端" in APP_SOURCE


def test_four_block_narrative_order():
    stem_idx = APP_SOURCE.index('with gr.TabItem("🎛️ 音色分軌")')
    block1_idx = APP_SOURCE.index('with gr.TabItem("🎯 節奏定位")')
    block2_idx = APP_SOURCE.index('with gr.TabItem("🎵 和弦簡譜")')
    block3_idx = APP_SOURCE.index('with gr.TabItem("📦 DAW 素材包")')
    assert stem_idx < block1_idx < block2_idx < block3_idx
