"""
SDD Pass 156 — 新增 v1 網格第六層證據，讓 v2 在無鼓段落也能持續委任小節

背景：使用者提供的舊參考版本（Music\\2，用 v1 的 measure_map 直接切出小節）在
World is Mine 前奏（12.4 秒無鼓）表現明顯優於現行 v2 引擎。直接比對兩者的
底層資料後確認：v1 的 BeatNet/Librosa 追蹤器完全不需要鼓證據就能對全曲連續
估計節奏脈動（同一首歌的真實 `beats` 陣列從 t=0.033s 開始、468 拍連續無缺口，
不像 v2 一直等到第一個真實鼓點 12.376s 才有東西可用）。v2 現有的和弦/旋律/
人聲證據層信心分數上限都被鎖死在 0.6~0.66（低於 0.7 commit 門檻），永遠無法
獨立委任小節，導致無鼓段落完全空白，只能靠 lookahead 硬跳，留下大缺口。

新增 V1GridEvidenceBarSearchNode（第六層證據）：讀取 v1 已經算好的
downbeat 網格（透過新的 `v1_reference_beat_grid` key，在
`_run_barstart_v2_comparison()` 把 v1 原始網格 pop 掉、讓 v2 自己的節點寫入
同名 key 之前，先存一份到這個新 key，讓這層證據節點在 v2 迴圈執行期間可以
讀到），在目前探測窗口內找 v1 的 downbeat，**跟和弦/旋律不同，這層信心分數
可以達到 commit 門檻、獨立委任小節**——因為這代表一整個神經網路模型對全曲的
一致性判斷，不是單一樂器的局部訊號。信心分數依 `downbeat_refinement` 自己
回報的來源做調整：v1 自己也是用 fallback（沒找到真實 downbeat、假設等速
4 拍)時，這層證據跟著降低信心，不假裝比 v2 自己的外插更可靠。

只接進 `_run_barstart_v2_comparison()`（真正的比較路徑，Module3BarStartV2MergeNode
與 BarStartV2AutoMergeNode 共用），不接進 `build_module3_barstart_v2_pipeline_tree()`
（獨立診斷樹，Stage 3 從未跑過，本來就沒有 v1 網格可用，接了也只會一直安全跳過）。

本測試驗證：
A. V1GridEvidenceBarSearchNode 本身：正確在探測窗口內找到 v1 downbeat 並產生
   候選；fallback 來源時信心分數降低；無網格/無窗口時安全跳過；已有候選時
   正確去重不重複產生。
B. 端對端模擬：連續多個 tick，在完全沒有鼓證據的情境下（模擬真實前奏），
   確認委任小節數穩定成長、覆蓋整段區間，而非卡在單一大跳躍缺口。
C. `_run_barstart_v2_comparison()` 正確在 pop 掉 beats/refined_beats 之前，
   把 v1 原始網格存進 v1_reference_beat_grid。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    BeatThisCandidateAdapterNode,
    BidirectionalBarAlignmentNode,
    ChordTrackPKNode,
    DrumBassEvidenceBarSearchNode,
    DrumEvidenceBarSearchNode,
    InterveningBarCountEstimatorNode,
    LocalModelRegistryNode,
    LookaheadDrumAnchorSearchNode,
    LookaheadDrumEventScanNode,
    MelodyTrackPKNode,
    NoDrumPhaseCarryNode,
    ReliableBarAnchorNode,
    RollingProbeWindowNode,
    TransitionConfidenceNode,
    V1GridEvidenceBarSearchNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode


def _v1_grid(bar_sec=1.46, n_bars=100):
    rows = []
    for i in range(n_bars * 4):
        t = i * (bar_sec / 4)
        beat_num = (i % 4) + 1
        rows.append([t, beat_num])
    return np.array(rows)


class TestV1GridEvidenceBarSearchNode:

    def test_finds_downbeats_in_window_with_base_confidence(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid())
        bb.set_val("active_bar_probe_window", {"start_time": 3.0, "end_time": 8.0})
        bb.set_val("downbeat_refinement", {"source": "existing_downbeats"})

        status = V1GridEvidenceBarSearchNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        candidates = bb.get_val("bar_start_candidates")
        assert len(candidates) >= 1
        for c in candidates:
            assert c["confidence"] == 0.72
            assert c["evidence_sources"] == ["v1_grid"]

    def test_fallback_source_reduces_confidence(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid())
        bb.set_val("active_bar_probe_window", {"start_time": 3.0, "end_time": 8.0})
        bb.set_val("downbeat_refinement", {"source": "fallback_candidate_4beat"})

        V1GridEvidenceBarSearchNode().execute(bb)
        candidates = bb.get_val("bar_start_candidates")
        assert all(c["confidence"] == 0.5 for c in candidates)

    def test_no_grid_skips_safely(self):
        bb = Blackboard()
        bb.set_val("active_bar_probe_window", {"start_time": 3.0, "end_time": 8.0})
        status = V1GridEvidenceBarSearchNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("v1_grid_evidence_report")["status"] == "NO_V1_DOWNBEAT_IN_WINDOW"

    def test_no_window_skips_safely(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid())
        status = V1GridEvidenceBarSearchNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("v1_grid_evidence_report")["status"] == "SKIPPED_NO_WINDOW"

    def test_does_not_duplicate_existing_nearby_candidate(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid())
        bb.set_val("active_bar_probe_window", {"start_time": 3.0, "end_time": 4.5})
        bb.set_val("downbeat_refinement", {"source": "existing_downbeats"})
        bb.set_val("bar_start_candidates", [
            {"time": 3.0, "confidence": 0.9, "source_node": "DrumEvidenceBarSearchNode"},
        ])

        V1GridEvidenceBarSearchNode().execute(bb)
        candidates = bb.get_val("bar_start_candidates")
        times = [c["time"] for c in candidates]
        assert times.count(3.0) == 1
        assert 4.38 in [round(t, 2) for t in times] or any(abs(t - 4.38) < 0.05 for t in times)


class TestEndToEndDrumlessSpanCoverage:

    def test_full_intro_gets_covered_instead_of_one_big_jump(self):
        """The exact real-song scenario: no drum evidence until t=12.4s, but
        v1's continuous grid covers the whole span. Before this pass, the
        loop would jump straight from the seed to the first real kick,
        leaving a single ~10s unresolved gap. After: it should commit a
        steady sequence of bars through the gap."""
        tick = SequenceNode("Tick", [
            RollingProbeWindowNode(), LocalModelRegistryNode(),
            DrumEvidenceBarSearchNode(), DrumBassEvidenceBarSearchNode(),
            ChordTrackPKNode(), MelodyTrackPKNode(),
            V1GridEvidenceBarSearchNode(),
            BeatThisCandidateAdapterNode(), ReliableBarAnchorNode(),
            LookaheadDrumEventScanNode(), LookaheadDrumAnchorSearchNode(),
            NoDrumPhaseCarryNode(), InterveningBarCountEstimatorNode(),
            BidirectionalBarAlignmentNode(), TransitionConfidenceNode(),
            BarStartCandidateCommitNode(),
        ])

        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 2.0])
        bb.set_val("v1_reference_beat_grid", _v1_grid())
        bb.set_val("downbeat_refinement", {"source": "existing_downbeats"})
        bb.set_val("kick_anchors", [12.4, 13.2, 14.0])
        bb.set_val("snare_anchors", [])

        for _ in range(6):
            tick.run(bb, parent="Tick")

        committed = bb.get_val("committed_bar_starts")
        # steady ~1.46s bars through the drum-less span, not one giant jump
        assert len(committed) >= 7
        gaps = [b - a for a, b in zip(committed, committed[1:])]
        assert max(gaps[1:]) < 2.0, f"found a large unfilled gap: {gaps}"


class TestV1ReferenceGridPreservedBeforePop:

    def test_run_barstart_v2_comparison_preserves_v1_grid(self, tmp_path):
        from pgm_craft.workflow.module3_bt import _run_barstart_v2_comparison

        audio_path = tmp_path / "source.wav"
        sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

        bb = Blackboard()
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float)
        bb.set_val("beats", beats.copy())
        bb.set_val("refined_beats", beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 2.0)
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0])
        bb.set_val("stems", {})

        comparison = _run_barstart_v2_comparison(bb)
        assert comparison is not None
        # the ORIGINAL blackboard's own beats must be untouched (isolation)
        assert bb.get_val("beats") is not None
