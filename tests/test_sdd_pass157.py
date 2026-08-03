"""
SDD Pass 157 — 讓 lookahead/carry-forward 缺口填補改用 v1 網格的真實節奏，
不再假設整段缺口是等速

背景：Pass 156 新增 V1GridEvidenceBarSearchNode，讓 v2 在無鼓段落也能用 v1
自己的連續 downbeat 網格獨立委任小節。但當這層證據也沒能單獨命中（例如信心
分數被 fallback 拉低到門檻以下，或探測窗口剛好落在兩個 tick 之間），流程會
掉到 InterveningBarCountEstimatorNode 和 NoDrumPhaseCarryNode 這兩個「缺口
填補」節點。這兩者長期以來都是用單一固定的 `bar_duration_sec / tempo_bpm`
去除、去外插整段缺口的秒數，隱含「這段缺口是等速的」假設——這正是使用者
反覆回報「前奏對不上」的同一種根因（v2 沒有跨越無鼓段落的真實節奏依據，
只能用等速估計硬猜）。

Pass 156 已經把 v1 的原始 downbeat 網格保存進 `v1_reference_beat_grid`，本
pass 直接重用它：

1. InterveningBarCountEstimatorNode：算兩個錨點之間的小節數時，優先直接數
   v1 網格裡落在這段時間內的真實 downbeat 數量，取代 `delta / duration`
   的算術估計。只有在 v1 網格沒有資料時才退回原本的算術估計（向後相容）。
2. NoDrumPhaseCarryNode：無論是「已知未來錨點」的 CARRIED 分支，還是「找不
   到任何未來錨點」的 CARRIED_FALLBACK 分支，都先檢查 v1 網格在該段區間內
   有沒有真實 downbeat；有的話直接採用那些真實時間點，而非用固定
   bar_duration 等距外插。v1 網格沒有資料時，兩個分支都完整保留 Pass 125
   建立的原始等速外插行為（含 tolerance/max_fallback_bars/duration_cap 邏輯
   不變）。

三個節點共用同一個新的模組層級 helper `_v1_reference_downbeats()`（從 Pass
156 的 `V1GridEvidenceBarSearchNode._v1_downbeat_times` 抽出，該方法現在改
為委派呼叫這個共用函式），避免三處重複同一段陣列篩選邏輯。

本測試驗證：
A. InterveningBarCountEstimatorNode：有 v1 網格時優先採用真實計數
   （estimate_source == "v1_grid_count"）；沒有 v1 網格時維持原本算術估計
   （estimate_source == "arithmetic_estimate"），行為與 Pass 117 完全一致。
B. NoDrumPhaseCarryNode：CARRIED 與 CARRIED_FALLBACK 兩個分支，有 v1 網格
   時都改用真實 downbeat 時間點（並標記 CARRIED_V1_GRID /
   CARRIED_FALLBACK_V1_GRID）；沒有 v1 網格時完全比照 Pass 125 的既有行為
   （含 max_fallback_bars 上限與 duration_cap）。
C. 端對端：模擬一段「前段變速、後段變速」的非等速 v1 網格缺口（刻意讓
   bar_duration 在缺口中途改變），確認整條 pipeline 產生的小節時間點跟隨
   v1 的真實變速節奏,而非被鎖死成單一固定間距。
"""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    BidirectionalBarAlignmentNode,
    InterveningBarCountEstimatorNode,
    LookaheadDrumAnchorSearchNode,
    LookaheadDrumEventScanNode,
    NoDrumPhaseCarryNode,
    ReliableBarAnchorNode,
    TransitionConfidenceNode,
    _v1_reference_downbeats,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode


def _v1_grid(bar_sec=1.46, n_bars=100, start=0.0):
    rows = []
    t = start
    for i in range(n_bars):
        for beat in range(4):
            rows.append([t, beat + 1])
            t += bar_sec / 4
    return np.array(rows)


def _variable_tempo_v1_grid():
    """First half at 1.0s/bar, second half at 1.5s/bar -- a genuinely
    non-constant-tempo grid, so a fix that just averages/locks onto a single
    bar_duration would still misplace bars in one half."""
    rows = []
    t = 0.0
    for _ in range(20):
        for beat in range(4):
            rows.append([t, beat + 1])
            t += 1.0 / 4
    for _ in range(20):
        for beat in range(4):
            rows.append([t, beat + 1])
            t += 1.5 / 4
    return np.array(rows)


class TestInterveningBarCountEstimatorPrefersV1Grid:

    def _base_blackboard(self):
        bb = Blackboard()
        bb.set_val("reliable_bar_anchors", [{"time": 2.0}])
        bb.set_val("lookahead_bar_candidates", [
            {"time": 12.376236, "confidence": 0.7, "offset_sec": 0.0},
        ])
        bb.set_val("bar_duration_sec", 1.46)
        return bb

    def test_uses_real_v1_downbeat_count_when_grid_available(self):
        bb = self._base_blackboard()
        # real downbeats strictly between 2.0 and 12.376236 at 1.46s spacing
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46, n_bars=20, start=2.0))

        status = InterveningBarCountEstimatorNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        selected = bb.get_val("selected_intervening_bar_count")
        assert selected is not None
        assert selected["estimate_source"] == "v1_grid_count"
        # ~7 bars of real v1.46s spacing fit in the ~10.38s gap
        assert 6 <= selected["bar_count"] <= 8

    def test_falls_back_to_arithmetic_when_no_v1_grid(self):
        bb = self._base_blackboard()
        status = InterveningBarCountEstimatorNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        selected = bb.get_val("selected_intervening_bar_count")
        assert selected is not None
        assert selected["estimate_source"] == "arithmetic_estimate"
        rows = bb.get_val("intervening_bar_count_candidates")
        assert all("bar_count" in row for row in rows)

    def test_falls_back_to_arithmetic_when_v1_grid_empty_in_span(self):
        bb = self._base_blackboard()
        # grid exists but has no downbeats in the (2.0, 12.376236) span
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46, n_bars=1, start=50.0))

        InterveningBarCountEstimatorNode().execute(bb)
        selected = bb.get_val("selected_intervening_bar_count")
        assert selected["estimate_source"] == "arithmetic_estimate"


class TestNoDrumPhaseCarryPrefersV1Grid:

    def test_carried_branch_uses_v1_grid_times_when_available(self):
        bb = Blackboard()
        bb.set_val("reliable_bar_anchors", [{"time": 2.0}])
        bb.set_val("lookahead_bar_candidates", [{"time": 12.4, "confidence": 0.8}])
        bb.set_val("bar_duration_sec", 1.46)
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46, n_bars=20, start=2.0))

        status = NoDrumPhaseCarryNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        report = bb.get_val("no_drum_phase_report")
        assert report["status"] == "CARRIED_V1_GRID"
        assert report["used_v1_grid"] is True
        provisional = bb.get_val("provisional_bar_starts")
        assert len(provisional) >= 5
        # every provisional time should coincide with a real v1 downbeat
        v1_times = _v1_reference_downbeats(bb)
        for t in provisional:
            assert any(abs(t - v1t) < 0.01 for v1t in v1_times)

    def test_carried_branch_falls_back_to_linear_without_v1_grid(self):
        bb = Blackboard()
        bb.set_val("reliable_bar_anchors", [{"time": 2.0}])
        bb.set_val("lookahead_bar_candidates", [{"time": 12.4, "confidence": 0.8}])
        bb.set_val("bar_duration_sec", 1.46)

        NoDrumPhaseCarryNode().execute(bb)
        report = bb.get_val("no_drum_phase_report")
        assert report["status"] == "CARRIED"
        assert report["used_v1_grid"] is False

    def test_fallback_branch_uses_v1_grid_times_when_available(self):
        bb = Blackboard()
        bb.set_val("reliable_bar_anchors", [{"time": 2.0}])
        bb.set_val("audio_duration_sec", 20.0)
        bb.set_val("bar_duration_sec", 1.46)
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46, n_bars=20, start=2.0))

        node = NoDrumPhaseCarryNode(max_fallback_bars=4)
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        report = bb.get_val("no_drum_phase_report")
        assert report["status"] == "CARRIED_FALLBACK_V1_GRID"
        provisional = bb.get_val("provisional_bar_starts")
        assert len(provisional) == 4  # still bounded by max_fallback_bars

    def test_fallback_branch_preserves_pass125_linear_behavior_without_v1_grid(self):
        bb = Blackboard()
        bb.set_val("reliable_bar_anchors", [{"time": 2.0}])
        bb.set_val("audio_duration_sec", 20.0)
        bb.set_val("bar_duration_sec", 1.46)

        node = NoDrumPhaseCarryNode(max_fallback_bars=4)
        node.execute(bb)
        report = bb.get_val("no_drum_phase_report")
        assert report["status"] == "CARRIED_FALLBACK_NO_LOOKAHEAD"
        assert report["used_v1_grid"] is False
        provisional = bb.get_val("provisional_bar_starts")
        assert len(provisional) == 4


class TestEndToEndVariableTempoGapFollowsRealGrid:

    def test_gap_bars_track_real_tempo_change_not_a_single_fixed_duration(self):
        """The v1 grid speeds up mid-gap (1.0s/bar -> 1.5s/bar). A fix that
        just picks one fixed bar_duration for the whole gap would misplace
        bars in at least one half; using the real v1 times should not."""
        tick = SequenceNode("Tick", [
            ReliableBarAnchorNode(),
            LookaheadDrumEventScanNode(),
            LookaheadDrumAnchorSearchNode(),
            NoDrumPhaseCarryNode(max_fallback_bars=50),
            InterveningBarCountEstimatorNode(),
            BidirectionalBarAlignmentNode(),
            TransitionConfidenceNode(),
            BarStartCandidateCommitNode(),
        ])

        grid = _variable_tempo_v1_grid()
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0])
        bb.set_val("v1_reference_beat_grid", grid)
        bb.set_val("bar_duration_sec", 1.0)  # a stale/global fallback estimate
        bb.set_val("kick_anchors", [])
        bb.set_val("snare_anchors", [])

        tick.run(bb, parent="Tick")

        report = bb.get_val("no_drum_phase_report")
        assert report["used_v1_grid"] is True
        provisional = bb.get_val("provisional_bar_starts")
        assert len(provisional) > 0

        real_downbeats = set(round(t, 4) for t in _v1_reference_downbeats(bb))
        # every provisional bar should land on (or extremely near) a real v1
        # downbeat -- not on a naive fixed-1.0s-spacing guess
        for t in provisional:
            assert any(abs(t - rt) < 0.01 for rt in real_downbeats), (
                f"{t} does not coincide with a real v1 downbeat -- "
                "looks like equal-tempo extrapolation instead"
            )
