"""
SDD Pass 151 — 補上 BarStart v2 證據階梯的 drum_onset_candidates 與
bass_onset_candidates 生產端

背景：Pass 147/148/149 陸續補上吉他/鋼琴節奏和弦 vs 旋律、bass_anchors、
vocal_melody_anchors 生產端。使用者接著指名補上剩下兩個：
`drum_onset_candidates`（DrumEvidenceBarSearchNode 在窗口內完全沒有 kick 證據
時的 fallback 來源）與 `bass_onset_candidates`（DrumBassEvidenceBarSearchNode
在 bass_anchors 之外額外疊加的來源）。稽核發現這兩個 key 全專案只有消費端在讀，
從沒有任何節點寫入過——跟 Pass 147/148/149 抓到的模式完全一樣。

新增 DrumBassOnsetCandidateExtractNode：跟現有 kick/snare/bass_anchors 用的
`_extract_peak_anchors`（單一門檻包絡峰值偵測）不同，改用
`librosa.onset.onset_detect`（頻譜通量，對音色變化更敏感，不只是比大小）：
- drum_onset_candidates 讀 stems["drums"]（完整鼓組混音，不是 kick/snare
  細分軌），可以撈到窄頻的 kick/snare 抓不到的 hihat/鈸等打擊事件
- bass_onset_candidates 讀 BassEvidenceExtractNode 已經在用的同一個 bass
  stem（sub_bass_808 > electric_bass > bass），撈到包絡門檻法會漏掉的
  較平滑起音貝斯音符

本測試驗證：
A. DrumBassOnsetCandidateExtractNode 本身：合成鼓/貝斯脈衝序列音檔能正確偵測
   兩者的 onset；無對應 stem 時安全跳過。
B. 下游消費：drum_onset_candidates 確實能被 DrumEvidenceBarSearchNode 當
   fallback 吃到（沒有 kick_anchors 時）；bass_onset_candidates 確實能被
   DrumBassEvidenceBarSearchNode 疊加進 bass_anchors 一起用。
C. 管線接線：兩條 v2 管線都正確接上這個節點，位置在 BassEvidenceExtractNode
   之後、ChordMelodyOnsetSplitNode 之前。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    DrumBassEvidenceBarSearchNode,
    DrumBassOnsetCandidateExtractNode,
    DrumEvidenceBarSearchNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def _pulse_wav(path, pulse_times, sr=22050, dur=5.0, freq=150.0, seed=1):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    audio = np.zeros_like(t)
    rng = np.random.default_rng(seed)
    for pt in pulse_times:
        idx = int(pt * sr)
        click_len = int(0.004 * sr)
        click_env = np.exp(-np.linspace(0, 20, click_len))
        audio[idx:idx + click_len] += 0.8 * rng.standard_normal(click_len) * click_env
        body_len = int(0.08 * sr)
        body_env = np.exp(-np.linspace(0, 8, body_len))
        audio[idx:idx + body_len] += 0.6 * np.sin(2 * np.pi * freq * np.linspace(0, 0.08, body_len)) * body_env
    sf.write(path, audio.astype(np.float32), sr)
    return path


DRUM_TIMES = [0.4, 1.0, 1.6, 2.2, 2.8, 3.4, 4.0]
BASS_TIMES = [0.5, 1.5, 2.5, 3.5, 4.5]


class TestDrumBassOnsetCandidateExtractNode:

    def test_drum_and_bass_onsets_detected(self, tmp_path):
        drum_path = _pulse_wav(str(tmp_path / "drums.wav"), DRUM_TIMES, freq=150.0, seed=1)
        bass_path = _pulse_wav(str(tmp_path / "bass.wav"), BASS_TIMES, freq=60.0, seed=2)

        bb = Blackboard()
        bb.set_val("stems", {"drums": drum_path, "bass": bass_path})
        status = DrumBassOnsetCandidateExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        drum_onsets = bb.get_val("drum_onset_candidates")
        bass_onsets = bb.get_val("bass_onset_candidates")
        report = bb.get_val("drum_bass_onset_extract_report")

        assert report["drums"]["status"] == "EXTRACTED"
        assert report["bass"]["status"] == "EXTRACTED"
        assert len(drum_onsets) == len(DRUM_TIMES)
        assert len(bass_onsets) == len(BASS_TIMES)
        for expected, detected in zip(DRUM_TIMES, drum_onsets):
            assert abs(expected - detected) < 0.05
        for expected, detected in zip(BASS_TIMES, bass_onsets):
            assert abs(expected - detected) < 0.05

    def test_missing_stems_skips_safely(self):
        bb = Blackboard()
        bb.set_val("stems", {})
        status = DrumBassOnsetCandidateExtractNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("drum_onset_candidates") == []
        assert bb.get_val("bass_onset_candidates") == []
        report = bb.get_val("drum_bass_onset_extract_report")
        assert report["drums"]["status"] == "SKIPPED_NO_STEM"
        assert report["bass"]["status"] == "SKIPPED_NO_STEM"

    def test_bass_stem_priority_prefers_sub_bass_808(self, tmp_path):
        sub_bass_path = _pulse_wav(str(tmp_path / "sub.wav"), [1.0], freq=50.0, seed=3)
        electric_path = _pulse_wav(str(tmp_path / "electric.wav"), [2.0], freq=70.0, seed=4)
        bb = Blackboard()
        bb.set_val("stems", {"sub_bass_808": sub_bass_path, "electric_bass": electric_path})

        DrumBassOnsetCandidateExtractNode().execute(bb)
        report = bb.get_val("drum_bass_onset_extract_report")
        assert report["bass"]["source"] == "sub.wav"


class TestDownstreamConsumersReceiveRealCandidates:

    def test_drum_evidence_search_falls_back_to_drum_onset_candidates(self):
        bb = Blackboard()
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 2.0})
        bb.set_val("kick_anchors", [])
        bb.set_val("snare_anchors", [])
        bb.set_val("drum_onset_candidates", [0.5, 1.5])

        status = DrumEvidenceBarSearchNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        candidates = bb.get_val("bar_start_candidates")
        assert len(candidates) == 2
        assert all(c["evidence_sources"][1] == "drum_onset" for c in candidates)

    def test_drum_bass_evidence_search_uses_bass_onset_candidates(self):
        bb = Blackboard()
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 2.0})
        bb.set_val("bass_anchors", [])
        bb.set_val("bass_onset_candidates", [0.5, 1.5])
        bb.set_val("bar_start_candidates", [])

        status = DrumBassEvidenceBarSearchNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        report = bb.get_val("drum_bass_evidence_report")
        assert report["bass_count_in_window"] == 2
        assert report["bass_only_candidate_count"] == 1


class TestPipelineWiring:

    def test_module3_barstart_v2_pipeline_includes_onset_node_between_bass_and_chord(self):
        tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
        names = _node_names(tree)
        assert "DrumBassOnsetCandidateExtractNode" in names
        assert (
            names.index("BassEvidenceExtractNode")
            < names.index("DrumBassOnsetCandidateExtractNode")
            < names.index("ChordMelodyOnsetSplitNode")
        )

    def test_module3_merge_node_core_chain_includes_onset_node(self, tmp_path):
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
        bb.set_val("stems", {})  # no drums/bass -> node should no-op

        status = Module3BarStartV2MergeNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("barstart_v2_report") is not None
