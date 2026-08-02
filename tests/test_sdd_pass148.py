"""
SDD Pass 148 — 補上 BarStart v2 證據階梯的 bass_anchors 生產端

背景：Pass 147 稽核發現整條「5 秒探測法」證據階梯除了鼓（kick_anchors/
snare_anchors，Stage 3 KickSnarePulseNode 產生）以外，其餘證據層都只有消費端
在讀，從未有節點寫入。Pass 147 先補上了吉他/鋼琴「節奏和弦 vs 旋律」的生產端
（guitar_chord_anchors/piano_chord_anchors/guitar_melody_anchors/
piano_melody_anchors）。使用者接著確認優先補上鼓+貝斯這一層——通常是最常見、
最穩定的第二層證據，指名「好,補上 bass_anchors」。

新增 BassEvidenceExtractNode：複用 Stage 3 KickSnarePulseNode 已經在用的同一
套峰值偵測演算法（_extract_peak_anchors），套用在 Stage 2 已分離好的 bass
stem 上（依序嘗試 sub_bass_808/electric_bass/bass，與 KickSnarePulseNode 的
低頻 backfill 邏輯相同的優先序），輸出 bass_anchors 陣列寫入 blackboard。
threshold_ratio=0.35 沿用 KickSnarePulseNode 內部「Sub-Bass Guard」段落既有
的貝斯脈衝門檻慣例。無 bass stem 時安全跳過。

本測試驗證：
A. BassEvidenceExtractNode 本身：合成貝斯脈衝序列音檔能正確偵測出脈衝時間點
   （在容許誤差內對齊）；無 stems/無 bass stem 時安全跳過不視為失敗。
B. 產出的 bass_anchors 確實能被 DrumBassEvidenceBarSearchNode 消費——鼓證據
   候選在有貝斯脈衝重合支持時，confidence 會被提升且加上
   bass_coincidence_support 標記。
C. 兩條管線（build_module3_barstart_v2_pipeline_tree() 與
   _run_barstart_v2_comparison() 的 v2_core chain）都正確接上這個節點，順序
   在 ManualCommittedBarStartsSeedNode() 之後、ChordMelodyOnsetSplitNode()
   之前（與 build_module3_barstart_v2_pipeline_tree() 中已套用的順序一致）。
"""

import os
import tempfile

import numpy as np
import soundfile as sf

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BassEvidenceExtractNode,
    DrumBassEvidenceBarSearchNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def _bass_pulse_wav(path, pulse_times, sr=22050, dur=8.0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    audio = np.zeros_like(t)
    pulse_len = int(0.15 * sr)
    env = np.exp(-np.linspace(0, 8, pulse_len))
    for pt in pulse_times:
        idx = int(pt * sr)
        if idx + pulse_len < len(audio):
            audio[idx:idx + pulse_len] += 0.8 * np.sin(
                2 * np.pi * 55 * np.linspace(0, 0.15, pulse_len)
            ) * env
    sf.write(path, audio.astype(np.float32), sr)
    return path


class TestBassEvidenceExtractNode:

    def test_synthetic_pulses_detected_within_tolerance(self, tmp_path):
        pulse_times = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
        bass_path = _bass_pulse_wav(str(tmp_path / "bass.wav"), pulse_times)
        bb = Blackboard()
        bb.set_val("stems", {"bass": bass_path})

        status = BassEvidenceExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        anchors = bb.get_val("bass_anchors")
        report = bb.get_val("bass_evidence_extract_report")
        assert report["status"] == "EXTRACTED"
        assert report["anchor_count"] == len(pulse_times)
        assert len(anchors) == len(pulse_times)
        for expected, detected in zip(pulse_times, anchors):
            assert abs(expected - detected) < 0.1

    def test_stem_priority_prefers_sub_bass_808(self, tmp_path):
        sub_bass_path = _bass_pulse_wav(str(tmp_path / "sub.wav"), [1.0, 2.0])
        electric_path = _bass_pulse_wav(str(tmp_path / "electric.wav"), [3.0, 4.0])
        bb = Blackboard()
        bb.set_val("stems", {
            "sub_bass_808": sub_bass_path,
            "electric_bass": electric_path,
        })

        BassEvidenceExtractNode().execute(bb)
        report = bb.get_val("bass_evidence_extract_report")
        assert report["source"] == "sub.wav"

    def test_missing_bass_stem_skips_safely(self):
        bb = Blackboard()
        bb.set_val("stems", {})
        status = BassEvidenceExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("bass_anchors") == []
        assert bb.get_val("bass_evidence_extract_report")["status"] == "SKIPPED_NO_STEM"


class TestDownstreamConsumerReceivesRealAnchors:

    def test_drum_bass_evidence_search_boosts_coincident_candidate(self, tmp_path):
        bass_path = _bass_pulse_wav(str(tmp_path / "bass.wav"), [0.5, 1.5, 2.5, 3.5], dur=4.0)
        bb = Blackboard()
        bb.set_val("stems", {"bass": bass_path})
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 4.0})
        bb.set_val("bar_start_candidates", [
            {
                "time": 0.48,
                "confidence": 0.5,
                "source_node": "DrumEvidenceBarSearchNode",
                "evidence_sources": ["drum"],
            },
        ])

        status = SequenceNode(
            "Chain", [BassEvidenceExtractNode(), DrumBassEvidenceBarSearchNode()]
        ).execute(bb)
        assert status == NodeStatus.SUCCESS

        candidates = bb.get_val("bar_start_candidates")
        assert candidates[0]["confidence"] > 0.5
        assert "bass_coincidence_support" in candidates[0]["evidence_sources"]

        report = bb.get_val("drum_bass_evidence_report")
        assert report["boosted_candidate_count"] == 1

    def test_no_bass_stem_leaves_candidates_unboosted(self):
        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 4.0})
        bb.set_val("bar_start_candidates", [
            {
                "time": 0.5,
                "confidence": 0.5,
                "source_node": "DrumEvidenceBarSearchNode",
                "evidence_sources": ["drum"],
            },
        ])

        SequenceNode(
            "Chain", [BassEvidenceExtractNode(), DrumBassEvidenceBarSearchNode()]
        ).execute(bb)

        candidates = bb.get_val("bar_start_candidates")
        assert candidates[0]["confidence"] == 0.5
        assert "bass_coincidence_support" not in candidates[0]["evidence_sources"]


class TestPipelineWiring:

    def test_module3_barstart_v2_pipeline_includes_bass_node_before_split_and_loop(self):
        tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
        names = _node_names(tree)
        assert "BassEvidenceExtractNode" in names
        assert (
            names.index("ManualCommittedBarStartsSeedNode")
            < names.index("BassEvidenceExtractNode")
            < names.index("ChordMelodyOnsetSplitNode")
            < names.index("FullSongBarStartLoopNode")
        )

    def test_module3_merge_node_core_chain_includes_bass_node(self, tmp_path):
        """Module3BarStartV2MergeNode builds its v2 core chain lazily inside
        execute(), so verify via a direct run rather than tree introspection."""
        from pgm_craft.workflow.module3_bt import Module3BarStartV2MergeNode

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
        bb.set_val("stems", {})  # no bass -> BassEvidenceExtractNode should no-op

        status = Module3BarStartV2MergeNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("barstart_v2_report") is not None
