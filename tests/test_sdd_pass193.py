"""
SDD Pass 193 — 消除碎拍與相位連貫 4/4 拍重排測試

背景：
Pass 192 將 Downbeat 缺失的過長小節硬切成 1 拍/2 拍碎小節，導致 Click 打在非強拍處發出爆音碎強拍。
Pass 193 引入 _ensure_44_phase_continuity，將 Downbeat 標籤推導補全為連貫的 1-2-3-4 拍號，
消除每 4 拍內部的人造強拍切點與碎小節。

詳見 docs/PASS-193-PHASE-COMPLETE-44-ALIGNMENT-TASK.md。
"""

import pytest
from pgm_craft.workflow.audio_nodes import MeasureMapNode


def test_ensure_44_phase_continuity():
    """驗證缺失 Downbeat 標籤的 beats 陣列被平滑修復為連貫 1-2-3-4 標號"""
    node = MeasureMapNode()
    # 模擬 8 個拍點，原本中間缺失 beat==1 標籤（標成了 1, 2, 3, 4, 2, 3, 4, 2）
    beat_rows = [
        {"time": 0.0, "beat": 1},
        {"time": 0.36, "beat": 2},
        {"time": 0.72, "beat": 3},
        {"time": 1.08, "beat": 4},
        {"time": 1.44, "beat": 2},  # 本該是 1
        {"time": 1.80, "beat": 3},
        {"time": 2.16, "beat": 4},
        {"time": 2.52, "beat": 2},
    ]

    fixed_rows = node._ensure_44_phase_continuity(beat_rows)

    beats_out = [r["beat"] for r in fixed_rows]
    assert beats_out == [1, 2, 3, 4, 1, 2, 3, 4]


def test_no_fragmented_measures():
    """驗證 build_measure_map 產出的所有小節皆為標準 4 拍小節，無碎拍亂切點"""
    node = MeasureMapNode()
    # 建立 12 個拍點的 beats 陣列
    beats = [
        [0.0, 1], [0.36, 2], [0.72, 3], [1.08, 4],
        [1.44, 2], [1.80, 3], [2.16, 4], [2.52, 2], # 中間 Downbeat 遺失
        [2.88, 1], [3.24, 2], [3.60, 3], [3.96, 4],
    ]

    mm, status, warnings = node.build_measure_map(beats)

    # 應連貫劃分為 3 個標準 4 拍小節
    assert len(mm) == 3
    for m in mm:
        assert m["beat_count"] == 4
        assert m["is_variable_length"] is False
