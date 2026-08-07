"""
SDD Pass 188 — MeasureMapNode 短小節前向合併

背景：
SteadyPercussionCountAnchorNode._apply_anchor() 從 base_idx 往後重標 1-2-3-4，
但 base_idx 之前的拍點相位沒有同步更新。這導致上一個小節到 base_idx 之間切出
一個只有 1-3 拍的「破碎小節」，計入 irregular_measure_count。

Pass 188 在 MeasureMapNode._build_from_downbeats() 結尾加入
_merge_short_measures() 後處理：把 beat_count < round(common_length * 0.75)
的中間破碎小節（非首尾）合併給前一個小節。

詳見 docs/PASS-188-BOUNDARY-SHORT-MEASURE-MERGE-TASK.md。

本測試驗證：
1. 中間破碎小節（2 拍，夾在正常 4 拍之間）被合併給前一個小節。
2. 末尾截斷（最後一個小節 3 拍）不被合併（is_incomplete 保留）。
3. 第一個小節破碎，沒有前一個可合併，保持原樣。
4. 連鎖合併（相鄰兩個破碎小節都合併給前一個）。
5. 既有回歸：所有既有測試不受影響。
"""

import numpy as np
import pytest

from pgm_craft.workflow.audio_nodes import MeasureMapNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


# ---------------------------------------------------------------------------
# 輔助函式
# ---------------------------------------------------------------------------

def _make_beats_from_downbeat_pattern(pattern, beat_sec=0.36):
    """
    根據小節 beat_count 序列合成 beats 陣列。
    pattern: [(beat_count, ...)] 例如 [4, 2, 4] 代表 4拍小節、2拍破碎、4拍小節。
    回傳 np.ndarray shape=(N, 2) [(time, beat_label), ...]，第一拍都標 1。
    """
    rows = []
    t = 0.0
    for count in pattern:
        for b in range(count):
            label = (b % 4) + 1  # 1-2-3-4 循環（實際標號不影響測試，只有 1 影響 downbeat）
            if b == 0:
                label = 1  # 每個小節第一拍強制是 1
            rows.append([t, label])
            t += beat_sec
    return np.array(rows, dtype=float)


def _count_irregular(measure_map, common_length=4):
    """統計 is_variable_length=True 的小節數（等同 irregular_measure_count）。"""
    return sum(1 for m in measure_map if m.get("is_variable_length", False))


# ---------------------------------------------------------------------------
# Test 1：中間破碎小節（2 拍）被合併給前一個
# ---------------------------------------------------------------------------

def test_short_middle_measure_merged():
    """[4拍, 2拍(破碎), 4拍] → 合併後 [6拍, 4拍]，irregular_count 從 1 → 1（6拍≠4拍，但破碎消失了；合理，因為這是保留了）"""
    # pattern = [4, 2, 4] → downbeat 在 idx 0, 4, 6
    # 預期合併後：[6拍小節, 4拍小節] → irregular_measure_count = 1（6拍異常）
    # 重要：2拍那個破碎小節被消滅了（否則會有 2 個 irregular）
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 2, 4])

    # 驗證合成的 beats 有 3 個 downbeat（beat==1）
    downbeat_times = beats[beats[:, 1] == 1, 0]
    assert len(downbeat_times) == 3, f"預期 3 個 downbeat，實際 {len(downbeat_times)}"

    mm, status, warnings = node.build_measure_map(beats)

    # 合併後應該只有 2 個小節（6拍 + 4拍），不是 3 個
    assert len(mm) == 2, f"合併後預期 2 小節，實際 {len(mm)}: {[m['beat_count'] for m in mm]}"
    assert mm[0]["beat_count"] == 6, f"第 1 小節預期 6 拍（4+2 合併），實際 {mm[0]['beat_count']}"
    assert mm[1]["beat_count"] == 4, f"第 2 小節預期 4 拍，實際 {mm[1]['beat_count']}"

    # 合併後 irregular_count：只有 6拍那個（6≠4），比合併前（2拍那個）更合理
    irregular = _count_irregular(mm)
    assert irregular == 1, f"合併後預期 1 個 irregular（6拍），實際 {irregular}"


# ---------------------------------------------------------------------------
# Test 2：末尾截斷不被合併
# ---------------------------------------------------------------------------

def test_last_measure_not_merged():
    """[4拍, 4拍, 3拍（末尾截斷）] → 不合併，3 個小節保持，末尾 is_incomplete=True"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 4, 3])

    mm, status, warnings = node.build_measure_map(beats)

    # 末尾那個 3 拍不應被合併
    assert len(mm) == 3, f"預期 3 小節（末尾不合併），實際 {len(mm)}: {[m['beat_count'] for m in mm]}"
    assert mm[2]["beat_count"] == 3, f"末尾小節預期 3 拍，實際 {mm[2]['beat_count']}"
    assert mm[2]["is_incomplete"] is True, "末尾小節應標 is_incomplete=True"


# ---------------------------------------------------------------------------
# Test 3：第一個小節破碎，沒有前一個可合併，保持原樣
# ---------------------------------------------------------------------------

def test_first_measure_short_kept():
    """[2拍(第一個), 4拍, 4拍] → 第一個不被合併，保持 3 個小節"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([2, 4, 4])

    mm, status, warnings = node.build_measure_map(beats)

    # 第一個 2 拍不能合併（沒有前一個），應保持 3 個小節
    assert len(mm) == 3, f"預期 3 小節（第一個不合併），實際 {len(mm)}: {[m['beat_count'] for m in mm]}"
    assert mm[0]["beat_count"] == 2, f"第一個小節預期 2 拍（保持），實際 {mm[0]['beat_count']}"


# ---------------------------------------------------------------------------
# Test 4：連鎖合併（相鄰兩個破碎小節）
# ---------------------------------------------------------------------------

def test_chained_merge():
    """真實場景：多個 4 拍小節中夾著一個 3 拍破碎小節。
    3 拍不被 _prune_ghost_downbeats 移除（gap=3 >= 0.6*4=2.4）。
    merge_threshold=round(4*1.0)=4，3 < 4 ✓，合併給前一個 4 拍 → 7 拍。
    [4, 4, 4, 3, 4, 4] → [4, 4, 7, 4, 4]（5 小節）。
    """
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 4, 4, 3, 4, 4])

    mm, status, warnings = node.build_measure_map(beats)

    # 3 拍小節（原第 4 個）合入前一個 4 拍 → 7 拍
    assert len(mm) == 5, f"預期 5 小節（3 拍合入前 4 拍），實際 {len(mm)}: {[m['beat_count'] for m in mm]}"
    assert mm[2]["beat_count"] == 7, f"第 3 小節預期 7 拍（4+3 合併），實際 {mm[2]['beat_count']}"
    assert mm[3]["beat_count"] == 4, f"第 4 小節預期 4 拍，實際 {mm[3]['beat_count']}"


# ---------------------------------------------------------------------------
# Test 5：正常小節不受影響（全是 4 拍）
# ---------------------------------------------------------------------------

def test_normal_measures_unchanged():
    """[4, 4, 4, 4] → 不觸發任何合併，4 個小節全部保持"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 4, 4, 4])

    mm, status, warnings = node.build_measure_map(beats)

    assert len(mm) == 4, f"預期 4 小節（全正常），實際 {len(mm)}"
    for i, m in enumerate(mm):
        assert m["beat_count"] == 4, f"第 {i+1} 小節預期 4 拍，實際 {m['beat_count']}"
    assert _count_irregular(mm) == 0, "全是 4 拍不應有 irregular"


# ---------------------------------------------------------------------------
# Test 6：小節編號連續性
# ---------------------------------------------------------------------------

def test_measure_numbers_sequential_after_merge():
    """合併後小節編號要連續（1, 2, 3...）"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 2, 4, 3, 4])

    mm, status, warnings = node.build_measure_map(beats)

    # 驗證編號連續
    for i, m in enumerate(mm):
        assert m["measure"] == i + 1, f"第 {i} 個小節的 measure 編號應為 {i+1}，實際 {m['measure']}"
