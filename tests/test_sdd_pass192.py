"""
SDD Pass 192 — MeasureMapNode 過長小節防膨脹合併修復

背景：
過長小節 (5 拍, 6 拍) 在節奏時間上每拍均勻極致平滑 (0.36s)，
主因是由於 Downbeat 標籤缺失導致 MeasureMapNode 將多拍包裹為單個怪異小節。
Pass 192 當時在 MeasureMapNode 中引入 `_split_overlong_measures`，將
5/6 拍過長小節拆分為 4 拍標準小節與變拍/短小節；但實際跑真實音訊後，
使用者回報這個硬切邏輯製造大量 1 拍/2 拍碎小節、嚴重破壞聽感連貫性，
Pass 193 已將 `_split_overlong_measures` 整個移除（改用全曲相位連貫
補全取代），原本測試這個方法的 `test_split_overlong_measures` 因此
一併移除。`_merge_short_measures` 的防膨脹保護（不將原本 4 拍標準小節
膨脹至 > 4 拍）維持不變，繼續由下方測試驗證。

詳見 docs/PASS-192-LONG-MEASURE-GRID-SPLITTER-TASK.md、
docs/PASS-193-PHASE-COMPLETE-44-ALIGNMENT-TASK.md。

本測試驗證：
1. 防膨脹保護阻止標準 4 拍小節吸收短小節變為 6 拍。
2. 兩個相鄰 2 拍短小節精確合併為一個 4 拍標準小節。
"""

import pytest
from pgm_craft.workflow.audio_nodes import MeasureMapNode


def test_merge_short_measures_anti_bloat():
    """驗證防膨脹保護：標準 4 拍小節不吞噬短小節變為 6 拍；而兩個 2 拍短小節則合併為 4 拍"""
    node = MeasureMapNode()
    common_length = 4

    measures = [
        # 標準 4 拍小節
        {
            "measure": 1,
            "start_time": 0.0,
            "end_time": 1.44,
            "beat_count": 4,
            "beats": [{"time": i * 0.36, "beat": i + 1} for i in range(4)],
            "is_variable_length": False,
            "is_incomplete": False,
            "source": "downbeat",
        },
        # 2 拍短小節 A
        {
            "measure": 2,
            "start_time": 1.44,
            "end_time": 2.16,
            "beat_count": 2,
            "beats": [{"time": 1.44 + i * 0.36, "beat": i + 1} for i in range(2)],
            "is_variable_length": True,
            "is_incomplete": False,
            "source": "downbeat",
        },
        # 2 拍短小節 B
        {
            "measure": 3,
            "start_time": 2.16,
            "end_time": 2.88,
            "beat_count": 2,
            "beats": [{"time": 2.16 + i * 0.36, "beat": i + 1} for i in range(2)],
            "is_variable_length": True,
            "is_incomplete": False,
            "source": "downbeat",
        },
    ]

    merged_result = node._merge_short_measures(measures, common_length)
    print("merged_result len:", len(merged_result))
    for m in merged_result:
        print("  m:", m["measure"], "beat_count:", m["beat_count"])

    # 第一個 4 拍標準小節保持原樣（不被吞噬膨脹成 6 拍）
    assert merged_result[0]["beat_count"] == 4
    assert merged_result[0]["is_variable_length"] is False

    # 兩個 2 拍短小節合體為一個 4 拍標準小節！
    assert len(merged_result) == 2
    assert merged_result[1]["beat_count"] == 4
    assert merged_result[1]["is_variable_length"] is False
