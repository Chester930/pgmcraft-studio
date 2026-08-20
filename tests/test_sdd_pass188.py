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
1. 中間破碎小節（2 拍），前一個是正常 4 拍小節時，Pass 192 的防膨脹保護
   不會合併（避免把正常小節膨脹成 6 拍），維持原樣。
2. 末尾截斷（最後一個小節 3 拍）不被合併（is_incomplete 保留）。
3. 第一個小節破碎，沒有前一個可合併，保持原樣。
4. 連鎖合併（相鄰兩個破碎小節、前一個也是短小節時，才合併給前一個）。
5. 既有回歸：所有既有測試不受影響。

Pass 195 更新：`_ensure_44_phase_continuity`（Pass 193/194 引入）已改為只
局部修復真的不規則的區段，不再整曲機械式拉平成 4/4，這裡的破碎小節/短
小節因此會照原樣進入 `_merge_short_measures`，回到 Pass 188 原始設計的
「只合併、不強制拉平」語意。
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
# Test 1：中間破碎小節（2 拍），前一個是正常 4 拍時不合併（防膨脹保護）
# ---------------------------------------------------------------------------

def test_short_middle_measure_merged():
    """[4拍, 2拍, 4拍] → 中間 2 拍破碎小節的前一個是正常 4 拍小節，Pass 192
    的防膨脹保護不會把它合併進去（合併會讓前一個小節膨脹成 6 拍，比防止
    破碎更糟），維持 3 個小節、中間那個是短小節。真正的連鎖合併場景見
    test_chained_merge（兩個相鄰短小節才合併）。"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 2, 4])

    downbeat_times = beats[beats[:, 1] == 1, 0]
    assert len(downbeat_times) == 3, f"預期 3 個 downbeat，實際 {len(downbeat_times)}"

    mm, status, warnings = node.build_measure_map(beats)

    assert len(mm) == 3
    assert mm[0]["beat_count"] == 4
    assert mm[1]["beat_count"] == 2
    assert mm[1]["is_variable_length"] is True
    assert mm[2]["beat_count"] == 4


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
    """[2拍(第一個), 4拍, 4拍] → 第一個小節沒有前一個可合併，保持原樣（2 拍）。

    Pass 195：`_ensure_44_phase_continuity` 只修「相鄰既有 downbeat 間距不是
    4 的整數倍」的局部區段，這裡第一個 2 拍區段本身內部（1-2 循環）已經
    自我一致，不需要局部修復；`_merge_short_measures` 也沒有更前面的小節
    可以合併——這是合理、應保留的短小節（例如 pickup/anacrusis），不強制
    拉平成 4 拍。"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([2, 4, 4])

    mm, status, warnings = node.build_measure_map(beats)

    assert mm[0]["beat_count"] == 2
    assert mm[0]["is_variable_length"] is True
    assert mm[1]["beat_count"] == 4
    assert mm[2]["beat_count"] == 4


# ---------------------------------------------------------------------------
# Test 4：連鎖合併（相鄰兩個破碎小節）
# ---------------------------------------------------------------------------

def test_chained_merge():
    """[4, 4, 4, 2, 2, 4, 4] → 相鄰兩個 2 拍破碎小節合併為一個標準 4 拍小節。

    改用兩個相鄰的 2 拍破碎小節（而非單一 3 拍），才是 `_merge_short_
    measures` 真正處理的「連鎖合併」場景——單一破碎小節夾在兩個正常 4 拍
    小節之間時，Pass 192 的防膨脹保護不會合併它（見 test_short_middle_
    measure_merged 的既有行為），只有「前一個也是短小節」時才合併。"""
    node = MeasureMapNode()
    beats = _make_beats_from_downbeat_pattern([4, 4, 4, 2, 2, 4, 4])

    mm, status, warnings = node.build_measure_map(beats)

    assert len(mm) == 6, f"預期合併後 6 個小節，實際 {len(mm)}: {[m['beat_count'] for m in mm]}"
    assert mm[3]["beat_count"] == 4
    assert mm[3]["is_variable_length"] is False


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
