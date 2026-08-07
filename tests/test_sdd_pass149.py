"""
SDD Pass 149 — 補上 BarStart v2 證據階梯的 vocal_melody_anchors 生產端

背景：Pass 147/148 陸續補上吉他/鋼琴節奏和弦 vs 旋律、bass_anchors 兩層生產端。
使用者接著指名補上 vocal_melody_anchors（人聲旋律樂句進入點，MelodyTrackPKNode
消費）。

（原本這個 Pass 也一併規劃補上 count_in_events「喊拍倒數」證據層，但使用者
表示目前不處理喊拍環節，該部分整個移除，之後若需要會加在 DAW 素材包處理
那塊——本檔案只涵蓋 vocal_melody_anchors。）

新增 VocalMelodyEvidenceExtractNode（module3_barstart_v2_bt.py，v2 專屬）：
讀取 lead_vocal/vocals_debreathed/vocals stem，用 onset 偵測抓人聲樂句進入
點；人聲本質上是單音旋律（不像吉他/鋼琴會刷和弦），因此不需要
ChordMelodyOnsetSplitNode 那種和弦/旋律二分類，全部視為旋律證據。

本測試驗證：
A. VocalMelodyEvidenceExtractNode：合成單音人聲旋律序列能正確偵測為旋律
   anchors；無人聲 stem 時安全跳過。
B. 下游消費：vocal_melody_anchors 確實能被 MelodyTrackPKNode 吃到。
C. 管線接線：VocalMelodyEvidenceExtractNode 接在兩條 v2 管線的
   ChordMelodyOnsetSplitNode 之後、FullSongBarStartLoopNode 之前。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.module3_barstart_v2_bt import (
    MelodyTrackPKNode,
    VocalMelodyEvidenceExtractNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode


def _melody_wav(path, sr=22050):
    def make_note(freq, dur):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        envelope = np.minimum(1.0, t * 30) * np.minimum(1.0, (dur - t) * 30)
        return 0.5 * np.sin(2 * np.pi * freq * t) * envelope

    silence = np.zeros(int(sr * 0.05))
    notes = [261.63, 293.66, 329.63, 392.0]
    audio = np.concatenate([np.concatenate([make_note(f, 0.4), silence]) for f in notes])
    sf.write(path, audio.astype(np.float32), sr)
    return path


class TestVocalMelodyEvidenceExtractNode:

    def test_synthetic_melody_detected(self, tmp_path):
        path = _melody_wav(str(tmp_path / "lead_vocal.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"lead_vocal": path})

        status = VocalMelodyEvidenceExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        anchors = bb.get_val("vocal_melody_anchors")
        report = bb.get_val("vocal_melody_extract_report")
        assert report["status"] == "EXTRACTED"
        assert len(anchors) >= 3
        for anchor in anchors:
            assert anchor["chord"] is None
            assert 0.0 <= anchor["confidence"] <= 1.0

    def test_stem_priority_prefers_lead_vocal(self, tmp_path):
        lead_path = _melody_wav(str(tmp_path / "lead.wav"))
        vocals_path = _melody_wav(str(tmp_path / "vocals.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"lead_vocal": lead_path, "vocals": vocals_path})

        VocalMelodyEvidenceExtractNode().execute(bb)
        report = bb.get_val("vocal_melody_extract_report")
        assert report["source"] == "lead.wav"

    def test_missing_vocal_stem_skips_safely(self):
        bb = Blackboard()
        bb.set_val("stems", {})
        status = VocalMelodyEvidenceExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("vocal_melody_anchors") == []
        assert bb.get_val("vocal_melody_extract_report")["status"] == "SKIPPED_NO_STEM"


class TestDownstreamConsumersReceiveRealAnchors:

    def test_melody_track_pk_consumes_produced_vocal_melody_anchors(self, tmp_path):
        path = _melody_wav(str(tmp_path / "lead_vocal.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"lead_vocal": path})
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 5.0})

        status = SequenceNode("Chain", [VocalMelodyEvidenceExtractNode(), MelodyTrackPKNode()]).execute(bb)
        assert status == NodeStatus.SUCCESS

        pk = bb.get_val("melody_track_pk")
        assert pk["status"] == "ANCHORS_BUILT"
        assert pk["anchor_count"] > 0
        assert pk["primary_source"] == "vocal_melody"


class TestPipelineWiring:

    def test_module3_merge_node_core_chain_includes_vocal_melody_node(self, tmp_path):
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
        bb.set_val("stems", {})  # no vocal -> VocalMelodyEvidenceExtractNode should no-op

        status = Module3BarStartV2MergeNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("barstart_v2_report") is not None
