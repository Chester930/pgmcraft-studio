"""
SDD Pass 153 — 修復 BarStartCandidateCommitNode 卡死不前進的核心 bug

背景：使用者在真實歌曲（【Hatsune_Miku】World is Mine）實測，回報「都不合格」。
用真實 stems 重跑 v2 引擎並逐 tick 追蹤後發現：整首歌只成功委任了 3 個小節就
提前結束（full_song_loop_report: iterations=5, committed_bar_count=3,
stop_reason=stalled_no_recovery）——證據階梯（Pass 147-151 新增的五層）本身運
作正常，問題出在更底層的「委任」邏輯。

根本原因：`RollingProbeWindowNode` 把下一個探測視窗的 start_time 直接設成
剛委任的那個小節時間（而非往後推進），導致剛委任的那個鼓點錨點仍然落在下一輪
搜尋視窗內。`BarStartCandidateCommitNode._best_candidate()` 信心分數同分時用
「時間較早者優先」當 tie-breaker，於是剛委任的那個時間點每次都贏過真正該找
的下一個小節候選（時間較晚但信心分數同樣是滿分）——委任邏輯每次都「重新委任」
同一個已存在的時間點，`_append_unique()` 正確判斷這是重複而不真的新增，但
外層報告仍標示「COMMITTED」，導致 `committed_bar_starts` 長度沒有真正成長，
迴圈在 stall_limit 次無真實進展後判定卡死、提前結束整條探測。

修復：在 `BarStartCandidateCommitNode.execute()` 選出「最佳候選」之前，先
排除掉時間已經在 `committed_bar_starts` 內（在 duplicate_tolerance_sec 容許
範圍內）的候選，強迫選擇邏輯必須挑到真正新的候選。

用真實歌曲重新驗證：修復前 iterations=5、committed_bar_count=3；修復後
iterations=195、committed_bar_count=179（覆蓋 176.6 秒歌曲的絕大部分）。

**額外發現、本 Pass 不處理**：真實歌曲資料顯示，另一個獨立既有機制
`_score_bar_start_list_quality`（相鄰小節長度變異係數評分）在小節歷史還很
短、且前面剛好接著一段長靜音區間（本曲前奏 12.4 秒無鼓點）時特別敏感——
剛脫離長靜音區間的第一個新候選，即使是完全正確的小節，也可能因為讓變異數
「看起來變差」而被判定 quality_regression、暫時擋下（此時 lookahead 機制會
接手跳過去找下一個更遠的錨點，整體上不會像本次修復的 bug 一樣完全卡死，但
仍會讓少數小節被記為 unresolved）。本測試檔案的合成場景刻意採用穩定的小節
長度歷史，避免跟這個獨立機制混在一起，只驗證本 Pass 真正修的「重複候選排除」
邏輯。

本測試驗證：
A. 精確重現卡死場景：committed_bar_starts 已包含某個時間點，候選清單裡「同一
   個已委任時間點」與「真正更晚的新候選」信心分數同分——修復前會錯誤地
   「重新委任」已存在的舊時間點（不推進）；修復後必須正確委任新的候選。
B. 候選清單裡如果全部都是已委任時間點的重複（沒有任何真正新證據），必須誠實
   回報 UNRESOLVED，不能謊報 COMMITTED。
C. 端對端用真實歌曲的 stems 重跑完整 FullSongBarStartLoopNode，確認委任的小節
   數量遠高於修復前的 3 個（此測試標記 slow，需要真實素材檔案存在才會執行）。
"""

import os

import numpy as np
import pytest

from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestBarStartCandidateCommitNodeAdvancesPastAlreadyCommittedBar:
    """Fixtures use a regular bar-duration history (0.8s/bar) so the
    pre-existing, separate quality-regression guard (`_score_bar_start_list_quality`,
    a coefficient-of-variation check) stays neutral and doesn't confound what
    these tests are isolating: whether the *duplicate-exclusion* fix itself
    works. (Real-song data showed that guard is its own, much more sensitive
    behavior when the bar history is still short/irregular right after a long
    silent intro -- worth revisiting separately, but out of scope here.)
    """

    def _seed_regular_history(self, bb, bar_count=10, bar_sec=0.8):
        committed = [round(i * bar_sec, 6) for i in range(bar_count)]
        bb.set_val("committed_bar_starts", committed)
        return committed

    def test_ties_with_already_committed_time_are_excluded_from_selection(self):
        """The exact stall scenario: the just-committed bar's own anchor is
        still inside the next probe window and ties on confidence with the
        genuinely next candidate -- the earlier (already-committed) one must
        not win the tie-break."""
        bb = Blackboard()
        committed = self._seed_regular_history(bb)
        last = committed[-1]
        next_bar = round(last + 0.8, 6)
        bb.set_val("active_bar_probe_window", {"start_time": last, "end_time": last + 3.0})
        bb.set_val("bar_start_candidates", [
            {"time": last, "confidence": 1.0, "source_node": "DrumEvidenceBarSearchNode"},
            {"time": next_bar, "confidence": 1.0, "source_node": "DrumEvidenceBarSearchNode"},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("committed_bar_starts")
        assert len(result) == len(committed) + 1
        assert next_bar in result

        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "COMMITTED"
        assert abs(report["committed_time"] - next_bar) < 1e-6

    def test_repeated_ticks_make_real_progress_instead_of_looping(self):
        """Simulates several ticks the way FullSongBarStartLoopNode would:
        each tick re-anchors the window at committed[-1], and the previously
        committed anchor is still technically inside the new window. Before
        the fix, committed_bar_starts length never grew past the seed+1."""
        bb = Blackboard()
        committed = self._seed_regular_history(bb)
        upcoming = [round(committed[-1] + 0.8 * i, 6) for i in range(1, 5)]  # 4 more real bars ahead

        for _ in range(4):
            last_committed = bb.get_val("committed_bar_starts")[-1]
            bb.set_val("active_bar_probe_window", {"start_time": last_committed, "end_time": last_committed + 3.0})
            bb.set_val("bar_start_candidates", [
                {"time": last_committed, "confidence": 1.0, "source_node": "DrumEvidenceBarSearchNode"},
            ] + [
                {"time": t, "confidence": 1.0, "source_node": "DrumEvidenceBarSearchNode"}
                for t in upcoming if t >= last_committed
            ])
            BarStartCandidateCommitNode().execute(bb)

        result = bb.get_val("committed_bar_starts")
        assert len(result) == len(committed) + len(upcoming)
        for t in upcoming:
            assert any(abs(t - c) < 1e-4 for c in result)

    def test_all_candidates_being_duplicates_reports_unresolved_not_committed(self):
        bb = Blackboard()
        committed = self._seed_regular_history(bb)
        last = committed[-1]
        bb.set_val("active_bar_probe_window", {"start_time": last, "end_time": last + 3.0})
        bb.set_val("bar_start_candidates", [
            {"time": last, "confidence": 1.0, "source_node": "DrumEvidenceBarSearchNode"},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        result = bb.get_val("committed_bar_starts")
        assert result == committed

        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "UNRESOLVED"
        assert report["reason"] == "no_candidates"


REAL_SONG_STEMS_DIR = (
    r"d:\Users\666\Music\1\【Hatsune_Miku】_World_is_Mine_ryo（supercell）"
    r"【初音ミク】\stems"
)


@pytest.mark.skipif(not os.path.isdir(REAL_SONG_STEMS_DIR), reason="real-song fixture not present on this machine")
class TestRealSongEndToEnd:

    def test_full_song_loop_commits_far_more_than_three_bars(self):
        from pgm_craft.workflow.beat_tracking_bt import AnchorTransientSnapNode, KickSnarePulseNode
        from pgm_craft.workflow.module3_barstart_v2_bt import (
            BassEvidenceExtractNode,
            ChordMelodyOnsetSplitNode,
            DrumBassOnsetCandidateExtractNode,
            FullSongBarStartLoopNode,
            ManualCommittedBarStartsSeedNode,
            MeterProfileNode,
            VocalMelodyEvidenceExtractNode,
        )
        from pgm_craft.workflow.nodes import SequenceNode

        project_dir = os.path.dirname(REAL_SONG_STEMS_DIR)
        source_dir = os.path.join(project_dir, "source")
        audio_path = None
        for f in os.listdir(source_dir):
            if "denoised" in f:
                audio_path = os.path.join(source_dir, f)
                break
        assert audio_path is not None

        bb = Blackboard()
        bb.set_val("stems", {})
        bb.set_val("stems_dir", REAL_SONG_STEMS_DIR)
        bb.set_val("audio_path", audio_path)
        bb.set_val("project_dir", project_dir)

        chain = SequenceNode("V2Core", [
            KickSnarePulseNode(),
            AnchorTransientSnapNode(anchor_key="kick_anchors", stem_keys=("kick",), stems_dir_fallbacks=("drums/kick.wav",)),
            AnchorTransientSnapNode(anchor_key="snare_anchors", stem_keys=("snare",), stems_dir_fallbacks=("drums/snare.wav",)),
            MeterProfileNode(),
            ManualCommittedBarStartsSeedNode(),
            BassEvidenceExtractNode(),
            DrumBassOnsetCandidateExtractNode(),
            ChordMelodyOnsetSplitNode(),
            VocalMelodyEvidenceExtractNode(),
            FullSongBarStartLoopNode(),
        ])
        status = chain.run(bb, parent="V2Core")
        assert status == NodeStatus.SUCCESS

        committed = bb.get_val("committed_bar_starts", [])
        loop_report = bb.get_val("full_song_loop_report", {})
        # Before the fix this stalled at exactly 3 committed bars / 5
        # iterations on this song; the fix should get well past that.
        assert len(committed) > 50
        assert loop_report.get("iterations", 0) > 50
