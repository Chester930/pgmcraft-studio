"""
SDD Pass 160 — 優化 DownbeatRefineNode 與對齊黑板 Key 讀寫、修正 SyncopationClassificationNode 空轉技術債

背景：
在 Pass 159 解決 Stage 2 分軌樹資料完整性 bug 後，我們進一步針對 Stage 3 節拍精修與切分音識別進行重構盤點：
1. DownbeatRefineNode 執行後同時寫入 beats 與 refined_beats，確保黑板 Key 雙向同步。
2. SyncopationClassificationNode 在原本空轉的 onset_events 無資料情況下，自動整合既有已提取的
   kick_anchors / snare_anchors / guitar_chord_anchors / piano_chord_anchors 作為事件輸入，不用額外增添特徵提取負擔。

本測試驗證：
1. DownbeatRefineNode 執行後 beats 與 refined_beats 是否同步且正確回報狀態。
2. SyncopationClassificationNode 在沒有 onset_events 時，是否能正確讀取 kick_anchors 等既有 anchors 進行切分音分類，不再產生空陣列。
"""

import numpy as np
import pytest

from pgm_craft.workflow.audio_nodes import DownbeatRefineNode
from pgm_craft.workflow.module3_bt import SyncopationClassificationNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass160:

    def test_downbeat_refine_node_syncs_beats_and_refined_beats(self):
        bb = Blackboard()
        # 模擬 8 拍 (2 小節 4/4 拍) 的標準 beat 序列
        test_beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4],
        ])
        bb.set_val("beats", test_beats)

        node = DownbeatRefineNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        assert np.array_equal(bb.get_val("beats"), bb.get_val("refined_beats"))
        assert bb.get_val("downbeat_refine_status") in ("PASS", "WARN")

    def test_syncopation_classification_node_uses_existing_anchors_when_onset_events_empty(self):
        bb = Blackboard()
        # 不設置 onset_events，改設置既有的 kick_anchors 與 snare_anchors
        bb.set_val("kick_anchors", [0.0, 1.0, 2.0])
        bb.set_val("snare_anchors", [0.5, 1.5, 2.5])
        bb.set_val("click_grid", [{"time": 0.0, "label": "1"}, {"time": 0.5, "label": "2"}])
        bb.set_val("subdivision_grid", [{"time": 0.0, "label": "1", "click": True}, {"time": 0.5, "label": "2", "click": True}])

        node = SyncopationClassificationNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        events = bb.get_val("syncopation_events")
        assert len(events) > 0, "應自動整合既有 anchors 進行切分音分類，不再回傳空陣列"
        assert any(e["time"] == 0.0 for e in events)
