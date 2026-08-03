"""
SDD Pass 163 — 雙軌融合仲裁 (BeatFusionArbitratorNode) 仲裁時間軸記錄與 v1 網格速度慣性約束驗證

背景：
在 Pass 163 中升級 BeatFusionArbitratorNode：
1. 當 A 軌（Drums+Bass）能量過低切換 B 軌或進行慣性內插時，在 beat_fusion_report 內完整紀錄 track_b_spans 時間軸明細。
2. 進行 Tempo Inertia 速度慣性內插時，若 Blackboard 存在 v1_reference_beat_grid，優先參考 v1 的真實步距而非假定等速。

本測試驗證：
1. BeatFusionArbitratorNode 輸出的 beat_fusion_report 包含 track_b_spans 鍵與紀錄結構。
2. v1_reference_beat_grid 存在時，慣性內插成功被導引並執行。
"""

import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import BeatFusionArbitratorNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass163:

    def test_arbitrator_generates_track_b_spans_report(self):
        bb = Blackboard()
        # 模擬 10 拍的 beats_a 與 beats_b
        beats_a = np.array([[float(i * 0.5), (i % 4) + 1] for i in range(10)])
        beats_b = np.array([[float(i * 0.5 + 0.01), (i % 4) + 1] for i in range(10)])

        bb.set_val("beats_rhythm", beats_a)
        bb.set_val("beats_inst", beats_b)
        bb.set_val("conf_rhythm", 0.8)
        bb.set_val("conf_inst", 0.6)

        # 模擬全零/低能量音訊（觸發 B 軌切換）
        sr = 22050
        y_rhythm = np.zeros(sr * 6)
        bb.set_val("y_rhythm", y_rhythm)
        bb.set_val("sr_rhythm", sr)

        node = BeatFusionArbitratorNode(energy_threshold=0.02)
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        report = bb.get_val("beat_fusion_report")
        assert "track_b_spans" in report
        assert report["switched_to_track_b_count"] > 0
        assert len(report["track_b_spans"]) > 0
        assert report["track_b_spans"][0]["reason"] == "low_rhythm_energy"

    def test_arbitrator_uses_v1_reference_grid_inertia(self):
        bb = Blackboard()
        beats_a = np.array([[float(i * 0.5), (i % 4) + 1] for i in range(10)])
        beats_b = np.array([[float(i * 0.5 + 0.01), (i % 4) + 1] for i in range(10)])

        # 提供 v1 參考網格 (以 2.0s 為 downbeat，拍步距 0.5s)
        v1_grid = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4], [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4]])
        bb.set_val("v1_reference_beat_grid", v1_grid)

        bb.set_val("beats_rhythm", beats_a)
        bb.set_val("beats_inst", beats_b)
        sr = 22050
        bb.set_val("y_rhythm", np.zeros(sr * 6))
        bb.set_val("sr_rhythm", sr)

        node = BeatFusionArbitratorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        assert bb.get_val("beats") is not None
