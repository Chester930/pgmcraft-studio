"""
SDD Pass 191 — _relabel_beat_numbers 保護區段相位連貫性修復

背景：
_relabel_beat_numbers 原本天真地使用 np.arange(len) 從全曲 index 0 硬套 1-2-3-4 標號，
事後才蓋回受保護區段 (protected_ranges) 的原始標號。
當硬套網格與保護區段錨點網格相位不一致時，交界處拍號斷層導致下游 MeasureMapNode 切出 5/6/7 拍過長小節。

Pass 191 重構 _relabel_beat_numbers，採順向時間軸單次掃描維護 last_label，
使非保護區段連貫順應前後保護區段之相位，實現全區交界處 0 相位跳躍銜接。

詳見 docs/PASS-191-RELABEL-BEAT-NUMBERS-PHASE-CONTINUITY-TASK.md。

本測試驗證：
1. 非保護區段順應前一個拍點標號連貫延伸 (1-2-3-4)。
2. 保護區段標號精確保留，離開保護區段時非保護拍點順暢接續 (例如 Beat 4 接 Beat 1)。
3. 保護區段前方的非保護拍點與保護區段起點 (Beat 1) 完美無縫銜接。
"""

import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import _relabel_beat_numbers


def test_relabel_beat_numbers_phase_continuity():
    """驗證非保護區段連貫順應保護區段之相位延伸"""
    # 建立 10 個拍點，時間 0.0 ~ 4.5s (週期 0.5s)
    timestamps = np.linspace(0.0, 4.5, 10)

    # 假設 Protected Range 為 1.5s ~ 3.0s (包含 idx 3, 4, 5, 6)，錨點標號為 [1, 2, 3, 4]
    protected_ranges = [(1.5, 3.0)]

    beats = np.zeros((10, 2))
    beats[:, 0] = timestamps
    beats[3:7, 1] = [1, 2, 3, 4]

    relabeled = _relabel_beat_numbers(beats, first_label=1, beats_per_bar=4, protected_ranges=protected_ranges)

    # 驗證全曲 10 個拍點被連貫標號為 [1, 2, 3, 1, 2, 3, 4, 1, 2, 3]
    # idx 0..2 (非保護): 1, 2, 3
    # idx 3..6 (保護區): 1, 2, 3, 4
    # idx 7..9 (非保護): 1, 2, 3
    expected_labels = [1, 2, 3, 1, 2, 3, 4, 1, 2, 3]
    actual_labels = list(relabeled[:, 1].astype(int))

    assert actual_labels == expected_labels, f"連貫標號不符預期: {actual_labels} vs {expected_labels}"


def test_relabel_beat_numbers_seamless_junction():
    """驗證保護區段起點為 Beat 1 時，保護區段前方的非保護拍號自動順應為 2, 3, 4... 無斷層"""
    timestamps = np.linspace(0.0, 4.0, 9)

    # Protected Range 為 2.0s ~ 3.5s (idx 4, 5, 6, 7)，標號為 1, 2, 3, 4
    protected_ranges = [(2.0, 3.5)]

    beats = np.zeros((9, 2))
    beats[:, 0] = timestamps
    beats[4:8, 1] = [1, 2, 3, 4]

    relabeled = _relabel_beat_numbers(beats, first_label=1, beats_per_bar=4, protected_ranges=protected_ranges)

    # idx 0..3 非保護區段應順序標號，到 idx 4 (1) 之前剛好為 4！
    # idx 0..3: 1, 2, 3, 4 -> idx 4..7 (保護區): 1, 2, 3, 4 -> idx 8 (非保護): 1
    expected_labels = [1, 2, 3, 4, 1, 2, 3, 4, 1]
    actual_labels = list(relabeled[:, 1].astype(int))

    assert actual_labels == expected_labels, f"銜接處標號不符預期: {actual_labels} vs {expected_labels}"
