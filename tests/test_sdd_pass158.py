"""
SDD Pass 158 — BarStartCandidateCommitNode 選候選時加入「小節長度合理性」檢查，
不再把每一拍都誤判成一個新小節

背景：使用者直接聽 v2 輸出的節拍器，回報「一團亂、一大堆點、根本聽不出來」。
用真實歌曲（World is Mine）資料分析後確認：v2 這次委任的 409 個「小節」，全曲
中位數間距只有 0.399 秒；而 v1 自己算出來的真實 downbeat（小節起點）間距中位
數是 1.453 秒——相差近 3.6 倍。0.399 秒正好接近這首歌的「拍」長度（≈150 BPM），
不是「小節」長度。也就是說 v2 把幾乎每一拍都誤判成一個新小節。

根本原因：`DrumEvidenceBarSearchNode` 等證據節點，只要在探測窗口內偵測到一個
kick/onset，就直接把它當成小節起點候選丟進候選池——沒有任何機制判斷「這個
kick 是小節的第一拍，還是小節中間普通的一拍」。最終的委任閘門
`BarStartCandidateCommitNode._best_candidate()` 只看信心分數高低
（`max(candidates, key=lambda item: (item["confidence"], -item["time"]))`），
完全不檢查「這個候選跟上一個已委任小節之間的間隔，是不是真的接近一個小節的
長度」。在鼓點打滿每一拍的段落（例如副歌、四大拍），每一拍的 kick 都會贏過
真正的下一個小節候選（時間更晚但信心分數未必更高），導致 v2 幾乎每拍都委任
一次，全曲密度暴增到接近拍子而非小節。

修復：在 `BarStartCandidateCommitNode.execute()` 選出「最佳候選」之前，新增
`_prefer_bar_length_plausible()`——用 Pass 156/157 已經建立的
`v1_reference_beat_grid`（v1 自己算出的真實 downbeat 網格，全曲穩定、不會被
v2 自己的委任歷史污染）算出全曲小節長度中位數，過濾掉「跟上一個已委任小節
的間隔小於中位數 60%」的候選——這些幾乎必然是同一小節內的普通拍子，不是
真正的下一個小節。如果過濾後候選清單變空（例如合法的短小節/過門樂句、或
根本沒有 v1 網格可用），則安全退回未過濾的清單，不引入 Pass 153 教訓過的
「無候選導致卡死」風險。

**為什麼不用 `committed[-1] - committed[-2]`（既有 `DrumEvidenceBarSearchNode.
_expected_interval` 的作法）當基準**：那個值只看「最近一次委任的間隔」，如果
早期不小心委任錯一個拍子級間隔，後續會自我強化鎖死在錯誤的密度上，永遠回不
去（親身驗證：這正是真實歌曲資料裡發生的事）。v1 的 downbeat 網格是獨立於
v2 自己委任歷史之外、一次算好的穩定基準，不會有這個自我污染問題。

真實歌曲端對端驗證（`_run_barstart_v2_comparison`，用真實 stems + 真實
`audio_duration_sec`）：
- 修復前：409 個「小節」，全曲中位數間距 0.399 秒
- 修復後：144 個小節，全曲中位數間距 1.207 秒（v1 真實 downbeat 中位數是
  1.453 秒——同一數量級，不再是拍子級密度），`full_song_loop_report.status
  == "COMPLETED"`，`unresolved_span_count = 11`（略高於修復前的 6，是預期
  中的合理代價：更嚴格的間隔檢查會讓少數邊緣候選被過濾掉、誠實回報
  unresolved，而不是用一個其實是拍子而非小節的候選蒙混過關）

本測試驗證：
A. 有 v1 網格、且候選池同時有「拍子級太近」與「小節級合理」兩種候選時，優先
   選小節級合理的那個，即使拍子級候選信心分數更高。
B. 沒有 v1 網格時完全不過濾，行為與 Pass 117/153 既有邏輯一致（向後相容）。
C. 過濾後候選池變空時（全部候選都太近）安全退回未過濾清單，不誤報無候選。
D. 尚未委任任何小節時（committed 為空）不套用過濾，即第一個小節不受影響。
E. 端對端：真實歌曲 stems，驗證全曲委任小節數與中位數間距落在合理範圍
   （此測試標記需要真實素材檔案存在才會執行）。
"""

import os

import numpy as np
import pytest

from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _v1_grid(bar_sec=1.46, n_bars=20, start=0.0):
    rows = []
    t = start
    for _ in range(n_bars):
        for beat in range(4):
            rows.append([t, beat + 1])
            t += bar_sec / 4
    return np.array(rows)


class TestPrefersBarLengthPlausibleCandidate:

    def test_rejects_beat_level_candidate_in_favor_of_bar_spaced_one(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46))
        bb.set_val("committed_bar_starts", [10.0])
        bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 20.0})
        bb.set_val("bar_start_candidates", [
            # a beat-level onset right after the previous bar -- high
            # confidence but implausibly close (~0.37s, a quarter of 1.46s)
            {"time": 10.365, "confidence": 0.95, "source_node": "DrumEvidenceBarSearchNode"},
            # the real next bar, one full bar-length ahead
            {"time": 11.46, "confidence": 0.72, "source_node": "V1GridEvidenceBarSearchNode"},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        assert status == NodeStatus.SUCCESS

        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "COMMITTED"
        assert abs(report["committed_time"] - 11.46) < 0.01

    def test_without_v1_grid_falls_back_to_pure_confidence(self):
        """Regression safety: Pass 117/153's existing behaviour (pure
        highest-confidence-wins) must be unchanged when there is no v1 grid
        to derive a bar-length expectation from."""
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [10.0])
        bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 20.0})
        bb.set_val("bar_start_candidates", [
            {"time": 10.365, "confidence": 0.95, "source_node": "DrumEvidenceBarSearchNode"},
            {"time": 11.46, "confidence": 0.72, "source_node": "V1GridEvidenceBarSearchNode"},
        ])

        BarStartCandidateCommitNode().execute(bb)
        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "COMMITTED"
        assert abs(report["committed_time"] - 10.365) < 0.01

    def test_falls_back_to_unfiltered_when_every_candidate_is_too_close(self):
        """If every available candidate is implausibly close to the previous
        bar (e.g. a legitimate short/pickup bar, or the real next bar simply
        wasn't detected this tick), do not report no-candidate -- fall back
        to the unfiltered list rather than risk a Pass-153-style stall."""
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46))
        bb.set_val("committed_bar_starts", [10.0])
        bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 12.0})
        bb.set_val("bar_start_candidates", [
            {"time": 10.365, "confidence": 0.95, "source_node": "DrumEvidenceBarSearchNode"},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "COMMITTED"
        assert abs(report["committed_time"] - 10.365) < 0.01

    def test_no_filter_applied_before_first_bar_is_committed(self):
        bb = Blackboard()
        bb.set_val("v1_reference_beat_grid", _v1_grid(bar_sec=1.46))
        bb.set_val("committed_bar_starts", [])
        bb.set_val("active_bar_probe_window", {"start_time": 0.0, "end_time": 2.0})
        bb.set_val("bar_start_candidates", [
            {"time": 0.1, "confidence": 0.95, "source_node": "DrumEvidenceBarSearchNode"},
        ])

        status = BarStartCandidateCommitNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        report = bb.get_val("bar_start_decision_report")
        assert report["status"] == "COMMITTED"
        assert abs(report["committed_time"] - 0.1) < 0.01


REAL_SONG_STEMS_DIR = (
    r"d:\Users\666\Music\1\【Hatsune_Miku】_World_is_Mine_ryo（supercell）"
    r"【初音ミク】\stems"
)
REAL_SONG_REPORT_PATH = (
    r"d:\Users\666\Music\1\【Hatsune_Miku】_World_is_Mine_ryo（supercell）"
    r"【初音ミク】\reports\module3_pipeline_report.json"
)


@pytest.mark.skipif(
    not (os.path.isdir(REAL_SONG_STEMS_DIR) and os.path.isfile(REAL_SONG_REPORT_PATH)),
    reason="real-song fixture not present on this machine",
)
class TestRealSongEndToEnd:

    def test_committed_bars_track_v1_real_bar_length_not_beat_length(self):
        import json

        from pgm_craft.workflow.module3_bt import _run_barstart_v2_comparison

        with open(REAL_SONG_REPORT_PATH, encoding="utf-8") as f:
            data = json.load(f)

        beats = data.get("refined_beats") or data.get("beats")
        stems = data.get("stems", {})
        project_dir = data.get("project_dir")
        audio_path = next(iter(stems.values()), None)

        v1_beats_arr = np.asarray(beats, dtype=float)
        v1_downbeats = sorted(v1_beats_arr[v1_beats_arr[:, 1] == 1, 0])
        v1_median_bar_sec = float(np.median(np.diff(v1_downbeats)))

        bb = Blackboard()
        bb.set_val("beats", beats)
        bb.set_val("refined_beats", beats)
        bb.set_val("stems", stems)
        bb.set_val("project_dir", project_dir)
        bb.set_val("audio_path", audio_path)
        # Must be set for NoDrumPhaseCarryNode's fallback branch to know
        # when to stop -- without it the fallback would run past the real
        # song end using the default 120bpm/4-beat=2.0s extrapolation.
        bb.set_val("audio_duration_sec", max(t for t, _ in beats) + 4.0)

        result = _run_barstart_v2_comparison(bb)
        assert result is not None and result["success"]

        committed = result["committed_bar_starts"]
        intervals = np.diff(committed)
        median_committed_interval = float(np.median(intervals))

        # Before this fix the median was ~0.399s (beat-level, ~3.6x too
        # dense). After the fix it should be the same order of magnitude as
        # v1's own real bar length, not a small fraction of it.
        assert median_committed_interval > v1_median_bar_sec * 0.5
        assert median_committed_interval < v1_median_bar_sec * 1.5

        loop_report = result["full_song_loop_report"]
        assert loop_report["status"] == "COMPLETED"
        # A musically sensible bar count for this ~176s song at ~1.2-1.5s/bar
        # (previously 409 "bars" at beat-level density).
        assert 80 < len(committed) < 250
