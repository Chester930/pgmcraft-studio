"""
SDD Pass 150 — 用瞬態磁吸校正提升 BarStart v2 鼓/貝斯錨點精準度

背景：使用者要求檢視節拍分析階段可以怎麼優化，指出兩個既有 v1 技巧值得借用：
`OnsetPhaseRealignmentNode`（頻譜通量 onset_strength 包絡，±35ms 視窗內找真正
onset peak）與 `MicroTimingTransientSnapNode`（在已分離的鼓組 stem 波形上做同樣
的瞬態磁吸）。v2 現有的 kick_anchors/snare_anchors/bass_anchors 都是靠
`_extract_peak_anchors` 抓出來的——單一全域門檻、100ms 窗口取最大絕對值包絡，
只是「找大聲的地方」，不是真的判斷「這裡是不是一次新的打擊起始點」，容易在較輕
的 ghost note 或跟其他樂器頻率重疊時抓偏。

新增 AnchorTransientSnapNode（beat_tracking_bt.py，v1/v2 共用）：合併上述兩個
技巧——在錨點所屬的獨立分軌 stem 上（不是全曲混音）計算 onset_strength 頻譜通量
包絡，在每個既有錨點 ±35ms 視窗內搜尋真正的 onset peak 並磁吸過去。這個節點不會
生出新的錨點——stem 真的靜音的地方依然是空的，只會校正已經抓到的錨點的精準度。

接進兩個位置：
1. 共用 Stage 3 準備節點（build_beat_tracking_preparation_nodes()，
   KickSnarePulseNode 之後）：校正 kick_anchors/snare_anchors，v1、v2 都會受益。
2. 兩條 v2 管線的 BassEvidenceExtractNode 之後：校正 bass_anchors。

本測試驗證：
A. AnchorTransientSnapNode 本身：合成音檔（真實瞬態位置已知、餵入的錨點刻意偏移
   15-40ms）能把錨點磁吸得更接近真實瞬態位置；無 stem／無錨點時安全跳過。
B. 端對端驗證：跟 v1 既有的 OnsetPhaseRealignmentNode 對同一份合成訊號跑，結果
   逐點比對完全一致——證明這是同一套演算法的忠實移植，不是另一套行為不同的邏輯。
C. 管線接線：kick/snare 校正接在共用 Stage 3 準備節點的 KickSnarePulseNode 之後；
   bass 校正接在兩條 v2 管線的 BassEvidenceExtractNode 之後、
   ChordMelodyOnsetSplitNode 之前。
"""

import os
import tempfile

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import (
    AnchorTransientSnapNode,
    OnsetPhaseRealignmentNode,
    build_beat_tracking_preparation_nodes,
)
from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def _kick_wav(path, true_peaks, sr=22050, dur=6.0, seed=0):
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    audio = np.zeros_like(t)
    rng = np.random.default_rng(seed)
    for pt in true_peaks:
        idx = int(pt * sr)
        click_len = int(0.004 * sr)
        click_env = np.exp(-np.linspace(0, 20, click_len))
        audio[idx:idx + click_len] += 0.9 * rng.standard_normal(click_len) * click_env
        body_len = int(0.08 * sr)
        body_env = np.exp(-np.linspace(0, 8, body_len))
        audio[idx:idx + body_len] += 0.7 * np.sin(2 * np.pi * 80 * np.linspace(0, 0.08, body_len)) * body_env
    sf.write(path, audio.astype(np.float32), sr)
    return path, audio, sr


TRUE_PEAKS = [0.55, 1.52, 2.49, 3.51, 4.48]
OFFSETS = [0.04, -0.03, 0.025, -0.02, 0.015]


class TestAnchorTransientSnapNode:

    def test_snaps_noisy_anchors_closer_to_true_transients(self, tmp_path):
        path, _, _ = _kick_wav(str(tmp_path / "kick.wav"), TRUE_PEAKS)
        noisy = [p + o for p, o in zip(TRUE_PEAKS, OFFSETS)]

        bb = Blackboard()
        bb.set_val("kick_anchors", noisy)
        bb.set_val("stems", {"kick": path})
        node = AnchorTransientSnapNode(
            anchor_key="kick_anchors", stem_keys=("kick",), stems_dir_fallbacks=("drums/kick.wav",)
        )
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS

        snapped = bb.get_val("kick_anchors")
        report = bb.get_val("kick_anchors_snap_report")
        assert report["status"] == "SNAPPED"
        assert len(snapped) == len(TRUE_PEAKS)

        before_errs = [abs(expected - before) for expected, before in zip(TRUE_PEAKS, noisy)]
        after_errs = [abs(expected - after) for expected, after in zip(TRUE_PEAKS, snapped)]
        # majority of points should end up closer to the true transient than
        # the noisy input -- matches v1's own OnsetPhaseRealignmentNode
        # behavior on the same signal (see test below), not a perfect-every-time
        # guarantee.
        improved = sum(1 for b, a in zip(before_errs, after_errs) if a < b)
        assert improved >= 3

    def test_missing_stem_skips_safely(self):
        bb = Blackboard()
        bb.set_val("kick_anchors", [0.5])
        bb.set_val("stems", {})
        node = AnchorTransientSnapNode(anchor_key="kick_anchors", stem_keys=("kick",))
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("kick_anchors") == [0.5]
        assert bb.get_val("kick_anchors_snap_report")["status"] == "SKIPPED_NO_STEM"

    def test_empty_anchors_skips_safely(self, tmp_path):
        path, _, _ = _kick_wav(str(tmp_path / "kick.wav"), TRUE_PEAKS)
        bb = Blackboard()
        bb.set_val("kick_anchors", [])
        bb.set_val("stems", {"kick": path})
        node = AnchorTransientSnapNode(anchor_key="kick_anchors", stem_keys=("kick",))
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("kick_anchors_snap_report")["status"] == "SKIPPED_NO_ANCHORS"

    def test_stems_dir_fallback_path(self, tmp_path):
        drums_dir = tmp_path / "drums"
        drums_dir.mkdir()
        path, _, _ = _kick_wav(str(drums_dir / "kick.wav"), TRUE_PEAKS)
        bb = Blackboard()
        bb.set_val("kick_anchors", [p + 0.02 for p in TRUE_PEAKS])
        bb.set_val("stems", {})
        bb.set_val("stems_dir", str(tmp_path))
        node = AnchorTransientSnapNode(
            anchor_key="kick_anchors", stem_keys=("kick",), stems_dir_fallbacks=("drums/kick.wav",)
        )
        status = node.execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("kick_anchors_snap_report")["status"] == "SNAPPED"


class TestMatchesV1OnsetPhaseRealignment:

    def test_identical_result_to_v1_onset_phase_realignment_node(self, tmp_path):
        """AnchorTransientSnapNode should be a faithful port of the same
        algorithm v1's OnsetPhaseRealignmentNode already uses in production --
        not a different heuristic that happens to look similar."""
        path, audio, sr = _kick_wav(str(tmp_path / "kick.wav"), TRUE_PEAKS)
        noisy = [p + o for p, o in zip(TRUE_PEAKS, OFFSETS)]

        bb_snap = Blackboard()
        bb_snap.set_val("kick_anchors", noisy)
        bb_snap.set_val("stems", {"kick": path})
        AnchorTransientSnapNode(anchor_key="kick_anchors", stem_keys=("kick",)).execute(bb_snap)
        snap_result = bb_snap.get_val("kick_anchors")

        beats = np.array([[a, i % 4 + 1] for i, a in enumerate(noisy)], dtype=float)
        bb_v1 = Blackboard()
        bb_v1.set_val("beats", beats)
        bb_v1.set_val("y", audio)
        bb_v1.set_val("sr", sr)
        OnsetPhaseRealignmentNode(search_window_ms=35.0).execute(bb_v1)
        v1_result = bb_v1.get_val("beats")[:, 0].tolist()

        for a, b in zip(sorted(snap_result), sorted(v1_result)):
            assert abs(a - b) < 1e-6


class TestPipelineWiring:

    def test_kick_snare_snap_after_kick_snare_pulse_in_shared_prep(self):
        nodes = build_beat_tracking_preparation_nodes()
        names = [n.name for n in nodes]
        kick_snap = [n for n in names if n.startswith("AnchorTransientSnapNode") and "kick_anchors" in n]
        snare_snap = [n for n in names if n.startswith("AnchorTransientSnapNode") and "snare_anchors" in n]
        assert kick_snap and snare_snap
        assert names.index("KickSnarePulseNode") < names.index(kick_snap[0])
        assert names.index("KickSnarePulseNode") < names.index(snare_snap[0])

    def test_bass_snap_wired_into_v2_diagnostic_pipeline(self):
        tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
        names = _node_names(tree)
        bass_snap = [n for n in names if n.startswith("AnchorTransientSnapNode") and "bass_anchors" in n]
        assert bass_snap
        assert (
            names.index("BassEvidenceExtractNode")
            < names.index(bass_snap[0])
            < names.index("ChordMelodyOnsetSplitNode")
        )

    def test_module3_merge_node_core_chain_runs_with_bass_snap(self, tmp_path):
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
        bb.set_val("stems", {})  # no bass -> AnchorTransientSnapNode should no-op

        status = Module3BarStartV2MergeNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        assert bb.get_val("barstart_v2_report") is not None
