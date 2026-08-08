"""
SDD Pass 192 — MeasureMapNode 過長小節動態網格拆分與防膨脹合併修復

背景：
過長小節 (5 拍, 6 拍) 在節奏時間上每拍均勻極致平滑 (0.36s)，
主因是由於 Downbeat 標籤缺失導致 MeasureMapNode 將多拍包裹為單個怪異小節。
Pass 192 在 MeasureMapNode 中引入 _split_overlong_measures，將 5/6 拍過長小節拆分為 4 拍標準小節與變拍/短小節，
並升級 _merge_short_measures 具備防膨脹保護（不將原本 4 拍標準小節膨脹至 > 4 拍）。

詳見 docs/PASS-192-LONG-MEASURE-GRID-SPLITTER-TASK.md。

本測試驗證：
1. 6 拍與 5 拍過長小節被精確拆分為標準 4 拍小節與短小節。
2. 防膨脹保護阻止標準 4 拍小節吸收短小節變為 6 拍。
3. 兩個相鄰 2 拍短小節精確合併為一個 4 拍標準小節。
"""

import pytest
from pgm_craft.workflow.audio_nodes import MeasureMapNode


def test_split_overlong_measures():
    """驗證過長小節 (6 拍) 被精確拆分為標準 4 拍小節與殘餘 2 拍小節"""
    node = MeasureMapNode()
    common_length = 4

    beats_6 = [{"time": 0.0 + i * 0.36, "beat": i + 1} for i in range(6)]
    measures = [
        {
            "measure": 1,
            "start_time": 0.0,
            "end_time": 2.16,
            "beat_count": 6,
            "beats": beats_6,
            "is_variable_length": True,
            "is_incomplete": False,
            "source": "downbeat",
        }
    ]

    split_result = node._split_overlong_measures(measures, common_length)

    assert len(split_result) == 2
    # 第一個小節為標準 4 拍小節
    assert split_result[0]["beat_count"] == 4
    assert split_result[0]["is_variable_length"] is False
    assert split_result[0]["start_time"] == 0.0

    # 第二個小節為殘餘 2 拍小節
    assert split_result[1]["beat_count"] == 2
    assert split_result[1]["is_variable_length"] is True


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
