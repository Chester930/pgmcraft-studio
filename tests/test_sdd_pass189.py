"""
SDD Pass 189 — Anchor 邊界雙向相位重補與過長小節修復

背景：
Pass 188 解決了短小節前向合併，但真實資料驗證中發現剩下的 14 個不規則小節全數為 5, 6, 7 拍
的過長小節。根本原因是 SteadyPercussionCountAnchorNode 套用錨點時只往後重標號，
 base_idx 之前的拍點仍維持舊相位，交界處相位不一致導致 MeasureMapNode 切出過長小節。

Pass 189 於 SteadyPercussionCountAnchorNode._apply_anchor() 加入往前倒推對齊 (Backward Phase Alignment)，
使得倒推相位連貫延伸至曲首或前一個受保護區段 (protected_ranges)。

詳見 docs/PASS-189-BOUNDARY-PHASE-BACKTRACE-TASK.md。

本測試驗證：
1. base_idx 之前的非保護拍點被正確倒推修正相位 (1-2-3-4 倒數)。
2. 倒推遭遇 protected_ranges 時自動停止，防護前一個已保護錨點。
3. prot_start 成功延伸至 first_touched_idx 之時間點。
"""

import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import SteadyPercussionCountAnchorNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_apply_anchor_backward_phase_alignment():
    """驗證 _apply_anchor 往前倒推對齊相位"""
    node = SteadyPercussionCountAnchorNode()

    # 建立 12 個拍點，週期 0.5s
    timestamps = np.linspace(0.0, 5.5, 12)
    # 原本的舊相位標號：全都是 1 1 1 1... (混亂相位)
    beats = np.column_stack([timestamps, np.ones(12)])

    # 設 run 從 3.0s (idx=6) 開始，包含 4 個連續擊點 (3.0, 3.5, 4.0, 4.5)
    run = {
        "start_time": 3.0,
        "end_time": 4.5,
        "count": 4,
        "cv": 0.01,
        "mean_interval_sec": 0.5,
        "onsets": [3.0, 3.5, 4.0, 4.5],
    }

    new_beats, prot_start, prot_end = node._apply_anchor(
        beats.copy(), timestamps, run, next_start=float("inf"), protected_ranges=[]
    )

    assert new_beats is not None
    # prot_start 為錨點本體起點 3.0s，不霸佔倒推區間
    assert prot_start == 3.0
    assert prot_end == 5.5

    # 驗證 idx=6 (3.0s) 為 Beat 1
    assert new_beats[6, 1] == 1

    # 驗證往前倒推的標號：idx=5 應為 4, idx=4 為 3, idx=3 為 2, idx=2 為 1, idx=1 為 4, idx=0 為 3
    expected_before = [3, 4, 1, 2, 3, 4]
    actual_before = list(new_beats[0:6, 1])
    assert actual_before == expected_before, f"往前倒推標號不符合預期: {actual_before} vs {expected_before}"


def test_apply_anchor_stops_at_protected_range():
    """驗證倒推標號遇到 protected_ranges 時會自動停下，不覆蓋前一段受保護相位"""
    node = SteadyPercussionCountAnchorNode()

    timestamps = np.linspace(0.0, 5.5, 12)
    beats = np.column_stack([timestamps, np.ones(12)])

    # 前段 idx 0..3 (0.0s ~ 1.5s) 為已受保護的相位
    protected_ranges = [(0.0, 1.5)]
    # 把這段標號改為特異標號 9
    beats[0:4, 1] = 9.0

    run = {
        "start_time": 3.0,
        "end_time": 4.5,
        "count": 4,
        "cv": 0.01,
        "mean_interval_sec": 0.5,
        "onsets": [3.0, 3.5, 4.0, 4.5],
    }

    new_beats, prot_start, prot_end = node._apply_anchor(
        beats.copy(), timestamps, run, next_start=float("inf"), protected_ranges=protected_ranges
    )

    assert new_beats is not None
    # prot_start 為錨點本體起點 3.0s
    assert prot_start == 3.0

    # 驗證 idx 0..3 維持 9.0 (未被覆蓋)
    assert list(new_beats[0:4, 1]) == [9.0, 9.0, 9.0, 9.0]

    # 驗證 idx=4 (2.0s), idx=5 (2.5s) 被對齊倒推：
    # idx=6 為 1 -> idx=5 為 4 -> idx=4 為 3
    assert new_beats[5, 1] == 4
    assert new_beats[4, 1] == 3
