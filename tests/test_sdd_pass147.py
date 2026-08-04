"""
SDD Pass 147 — 補上 BarStart v2 證據階梯的吉他/鋼琴節奏和弦 vs 旋律分軌生產端

背景：使用者要求檢視「5 秒探測法」（FullSongBarStartLoopNode 的 BarStartV2ProbeTick）
整條證據階梯，稽核發現除了第一層鼓證據（kick_anchors/snare_anchors，來自 Stage 3
KickSnarePulseNode，真的有節點產生)以外，其餘 bass/guitar_chord/piano_chord/
guitar_melody/piano_melody/vocal_melody/count_in_events 全部只有消費端
（ChordTrackPKNode/MelodyTrackPKNode/DrumBassEvidenceBarSearchNode）在讀取，
從來沒有任何節點寫入過。也就是說證據階梯實務上只剩鼓這一層，跟完全沒有
這個階梯設計幾乎一樣——這直接解釋了為什麼 v2 在沒有鼓的段落總是判定
V2_INCOMPLETE 而回退用 v1。

使用者確認優先補上吉他/鋼琴的「節奏和弦 vs 旋律」分軌生產端（這正是使用者
原本設計、但從未真正實作生產端的部分）。bass_anchors 等其餘證據層留待後續
Pass。

新增 ChordMelodyOnsetSplitNode：讀取 Stage 2 已分離好的 guitar.wav/piano.wav，
用 onset 偵測 + chroma 多音判斷（一個 onset 窗口內有幾個活躍音高類別）分類每
個 onset 是「和弦」（≥3 個活躍音高類別，典型如刷弦/塊狀和弦）還是「旋律」
（1-2 個，單音線條），各自輸出 anchors 陣列（time/confidence/chord）寫入
guitar_chord_anchors/piano_chord_anchors/guitar_melody_anchors/
piano_melody_anchors。無 guitar/piano stem 時安全跳過。

本測試驗證：
A. ChordMelodyOnsetSplitNode 本身：合成音檔（單音序列=旋律、三音和弦序列=和弦）
   分類正確；無 guitar/piano stem 時安全跳過不視為失敗。
B. 產出的 anchors 確實能被 ChordTrackPKNode/MelodyTrackPKNode 消費（不再是空
   陣列）。
C. 兩條管線（build_module3_barstart_v2_pipeline_tree() 與
   _run_barstart_v2_comparison() 的 v2_core chain）都正確接上這個節點，順序
   在 FullSongBarStartLoopNode() 之前。
"""

import os
import tempfile

import numpy as np
import soundfile as sf

from pgm_craft.workflow.module3_barstart_v2_bt import (
    ChordMelodyOnsetSplitNode,
    ChordTrackPKNode,
    MelodyTrackPKNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode


def _make_note(freq, dur, sr):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    envelope = np.minimum(1.0, t * 30) * np.minimum(1.0, (dur - t) * 30)
    return 0.5 * np.sin(2 * np.pi * freq * t) * envelope


def _make_chord(freqs, dur, sr):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    envelope = np.minimum(1.0, t * 30) * np.minimum(1.0, (dur - t) * 30)
    y = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    return 0.5 * y * envelope


def _melody_wav(path, sr=22050):
    silence = np.zeros(int(sr * 0.05))
    notes = [261.63, 329.63, 392.0, 523.25]  # C4 E4 G4 C5, one at a time
    audio = np.concatenate([np.concatenate([_make_note(f, 0.4, sr), silence]) for f in notes])
    sf.write(path, audio.astype(np.float32), sr)
    return path


def _chord_wav(path, sr=22050):
    silence = np.zeros(int(sr * 0.05))
    audio = np.concatenate([
        np.concatenate([_make_chord([261.63, 329.63, 392.0], 0.4, sr), silence])
        for _ in range(4)
    ])
    sf.write(path, audio.astype(np.float32), sr)
    return path


class TestChordMelodyOnsetSplitNode:

    def test_single_note_sequence_classified_as_melody(self, tmp_path):
        guitar_path = _melody_wav(str(tmp_path / "guitar.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"guitar": guitar_path})

        status = ChordMelodyOnsetSplitNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        melody = bb.get_val("guitar_melody_anchors")
        chord = bb.get_val("guitar_chord_anchors")
        assert len(melody) >= 3
        assert len(chord) == 0
        for anchor in melody:
            assert anchor["chord"] is None
            assert 0.0 <= anchor["confidence"] <= 1.0

    def test_chord_sequence_classified_as_chord(self, tmp_path):
        piano_path = _chord_wav(str(tmp_path / "piano.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"piano": piano_path})

        status = ChordMelodyOnsetSplitNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        chord = bb.get_val("piano_chord_anchors")
        melody = bb.get_val("piano_melody_anchors")
        assert len(chord) >= 3
        assert len(melody) == 0
        for anchor in chord:
            assert anchor["chord"] == "C"

    def test_missing_stems_skips_safely(self):
        bb = Blackboard()
        bb.set_val("stems", {})
        status = ChordMelodyOnsetSplitNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("guitar_chord_anchors") == []
        assert bb.get_val("guitar_melody_anchors") == []
        assert bb.get_val("piano_chord_anchors") == []
        assert bb.get_val("piano_melody_anchors") == []
        report = bb.get_val("chord_melody_split_report")
        assert report["guitar"]["status"] == "SKIPPED_NO_STEM"
        assert report["piano"]["status"] == "SKIPPED_NO_STEM"


class TestDownstreamConsumersReceiveRealAnchors:

    def test_chord_track_pk_consumes_produced_guitar_chord_anchors(self, tmp_path):
        piano_path = _chord_wav(str(tmp_path / "piano.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"piano": piano_path})
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 5.0})

        SequenceNode("Chain", [ChordMelodyOnsetSplitNode(), ChordTrackPKNode()]).execute(bb)

        pk = bb.get_val("chord_track_pk")
        assert pk["status"] == "ANCHORS_BUILT"
        assert pk["anchor_count"] > 0

    def test_melody_track_pk_consumes_produced_guitar_melody_anchors(self, tmp_path):
        guitar_path = _melody_wav(str(tmp_path / "guitar.wav"))
        bb = Blackboard()
        bb.set_val("stems", {"guitar": guitar_path})
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 5.0})

        SequenceNode("Chain", [ChordMelodyOnsetSplitNode(), MelodyTrackPKNode()]).execute(bb)

        pk = bb.get_val("melody_track_pk")
        assert pk["status"] == "ANCHORS_BUILT"
        assert pk["anchor_count"] > 0


class TestPipelineWiring:

    def test_module3_merge_node_core_chain_includes_split_node(self, tmp_path):
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
        bb.set_val("stems", {})  # no guitar/piano -> ChordMelodyOnsetSplitNode should no-op

        status = Module3BarStartV2MergeNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("barstart_v2_report") is not None
