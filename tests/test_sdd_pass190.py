"""
SDD Pass 190 — KickBassDownbeatVerifierNode 180度反相網格連貫性修復

背景：
KickBassDownbeatVerifierNode (Pass 168) 在觸發強拍 180 度反相修復 (ROTATED) 時，
原本會直接將 fixed_beats[:, 1] 清空成 0，只將非保護區段的 beat3_indices 寫回為 1。
這導致非保護區段的 2, 3, 4 拍標籤全部遺失為 0，破壞了 1-2-3-4 拍號網格連貫性，
致使下游 MeasureMapNode 切出 5/6/7 拍之過長破碎小節。

Pass 190 將 180 度旋轉修改為對非保護區段拍號進行 (+2 拍) 平移旋轉：
Beat 3 -> Beat 1, Beat 4 -> Beat 2, Beat 1 -> Beat 3, Beat 2 -> Beat 4，
完整保留拍號網格連貫性，且完全尊重受保護區段 (protected_ranges)。

詳見 docs/PASS-190-KICK-BASS-DOWNBEAT-VERIFIER-GRID-REPRESERVATION-TASK.md。

本測試驗證：
1. 反相旋轉觸發時，非保護區段所有拍號被正確平移 2 拍，無任何 0 遺失。
2. 受保護區段 (protected_ranges) 內的拍號被完整保留。
"""

import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import KickBassDownbeatVerifierNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_kick_bass_verifier_preserves_grid_on_rotation():
    """驗證強拍 180 度旋轉修復時，非保護區段 1-2-3-4 拍號網格被連貫平移，無標號遺失為 0"""
    node = KickBassDownbeatVerifierNode()

    sr = 22050
    duration = 4.0
    n = int(duration * sr)

    # 建立 8 個拍點，週期 0.5s（剛好 2 小節）
    timestamps = np.linspace(0.2, 3.7, 8)
    beats = np.column_stack([timestamps, [1, 2, 3, 4, 1, 2, 3, 4]])

    # 建立低頻音步 (y)，在 idx=2 (Beat 3) 與 idx=6 (Beat 3) 處放強勁 60Hz 低頻脈衝
    y = np.zeros(n)
    t_pulse = np.linspace(0, 0.1, int(0.1 * sr))
    pulse = 1.0 * np.sin(2 * np.pi * 60.0 * t_pulse)

    for idx in [2, 6]:
        sample_idx = int(timestamps[idx] * sr)
        y[sample_idx : sample_idx + len(pulse)] += pulse

    bb = Blackboard()
    bb.set_val("beats", beats)
    bb.set_val("y", y)
    bb.set_val("sr", sr)
    bb.set_val("beat_phase_protected_ranges", [])

    status = node.execute(bb)
    assert status == NodeStatus.SUCCESS

    report = bb.get_val("downbeat_fix_report")
    assert report["status"] == "ROTATED"

    fixed_beats = bb.get_val("beats")
    assert fixed_beats is not None
    assert not np.any(fixed_beats[:, 1] == 0), "標號不應有任何 0 遺失"

    # 原 Beat 3 (idx 2, 6) 應變為 Beat 1
    assert fixed_beats[2, 1] == 1
    assert fixed_beats[6, 1] == 1

    # 原 Beat 4 (idx 3, 7) 應變為 Beat 2
    assert fixed_beats[3, 1] == 2
    assert fixed_beats[7, 1] == 2

    # 原 Beat 1 (idx 0, 4) 應變為 Beat 3
    assert fixed_beats[0, 1] == 3
    assert fixed_beats[4, 1] == 3

    # 原 Beat 2 (idx 1, 5) 應變為 Beat 4
    assert fixed_beats[1, 1] == 4
    assert fixed_beats[5, 1] == 4


def test_kick_bass_verifier_respects_protected_ranges():
    """驗證受保護區段內的拍號在 180 度旋轉時不被動到"""
    node = KickBassDownbeatVerifierNode()

    sr = 22050
    duration = 4.0
    n = int(duration * sr)

    timestamps = np.linspace(0.2, 3.7, 8)
    beats = np.column_stack([timestamps, [1, 2, 3, 4, 1, 2, 3, 4]])

    # 保護第一小節 (0.0s ~ 2.0s，涵蓋 idx 0..3)
    protected_ranges = [(0.0, 2.0)]

    y = np.zeros(n)
    t_pulse = np.linspace(0, 0.1, int(0.1 * sr))
    pulse = 1.0 * np.sin(2 * np.pi * 60.0 * t_pulse)

    # 在非保護區段 idx 6 (Beat 3) 放置低頻重音
    sample_idx = int(timestamps[6] * sr)
    y[sample_idx : sample_idx + len(pulse)] += pulse

    bb = Blackboard()
    bb.set_val("beats", beats)
    bb.set_val("y", y)
    bb.set_val("sr", sr)
    bb.set_val("beat_phase_protected_ranges", protected_ranges)

    status = node.execute(bb)
    assert status == NodeStatus.SUCCESS

    fixed_beats = bb.get_val("beats")

    # 驗證保護區段 idx 0..3 維持 1, 2, 3, 4 (未被旋轉)
    assert list(fixed_beats[0:4, 1]) == [1, 2, 3, 4]

    # 驗證非保護區段 idx 4..7 成功旋轉 (+2 拍)：
    # 原 1, 2, 3, 4 變 3, 4, 1, 2
    assert list(fixed_beats[4:8, 1]) == [3, 4, 1, 2]
