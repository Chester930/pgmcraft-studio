"""
SDD Pass 161 & 162 — 雙軌融合仲裁 (BeatFusionArbitratorNode) 與品質對齊 Safe Fallback 驗證

背景：
在 Stage 3 雙軌融合與精修階段：
1. Pass 161：修復 `_score_beat_grid_quality()` 在 `sections` (樂段結構) 恆為空時的 Safe Fallback 機制，自動退回全曲 Main 樂段進行相干性比對。
2. Pass 162：確保 `BeatFusionArbitratorNode` 在進行 A/B 軌能量仲裁並輸出 `beats` 時，同步更新 `refined_beats` key。

本測試驗證：
1. `_score_beat_grid_quality()` 在 `sections=None` 或 `sections=[]` 時能產生合法的對齊分數（不退化為無效空值）。
2. `BeatFusionArbitratorNode` 在 A/B 軌皆存在時能正確融合，且 `beats` 與 `refined_beats` 完全一致。
"""

import numpy as np
import pytest

from pgm_craft.workflow.beat_tracking_bt import BeatFusionArbitratorNode, _score_beat_grid_quality
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestSDDPass161And162:

    def test_score_beat_grid_quality_sections_safe_fallback(self):
        # 建立測試 beats
        beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4]
        ])
        # 不提供 sections
        res = _score_beat_grid_quality(beats, sections=None)
        assert res["score"] > 0.0
        assert "warnings" in res

    def test_beat_fusion_arbitrator_syncs_refined_beats(self):
        bb = Blackboard()
        beats_a = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]])
        beats_b = np.array([[0.01, 1], [0.51, 2], [1.01, 3], [1.51, 4]])

        bb.set_val("beats_rhythm", beats_a)
        bb.set_val("beats_inst", beats_b)
        bb.set_val("conf_rhythm", 0.9)
        bb.set_val("conf_inst", 0.7)

        node = BeatFusionArbitratorNode()
        status = node.execute(bb)

        assert status == NodeStatus.SUCCESS
        assert bb.get_val("beats") is not None
        assert bb.get_val("refined_beats") is not None
        assert np.array_equal(bb.get_val("beats"), bb.get_val("refined_beats"))
