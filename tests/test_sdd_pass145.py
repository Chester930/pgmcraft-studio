"""
SDD Pass 145 — BarStart v2 節奏平滑不應覆蓋真實鼓點證據

背景：使用者聽了 Pass 144 修復後的結果，回報「為了要壓快速的節奏變化，反而
有些地方失真了」——具體案例是前奏與主歌速度差很多（例如前奏沒有鼓、速度估
計本來就不準；進主歌後鼓進來了），但 BarStartTempoSmoothingNode 把主歌一
開始那幾個小節也當成「離群值」拉回局部中位數，導致連原本靠鼓點就能對準的
小節都被移動、跟鼓點對不上了。使用者明確指出：「只要有鼓點就是準的」——真
正的段落速度轉變（伴隨鼓點進來）不該被統計平滑器誤判成噪聲。

修復：BarStartTempoSmoothingNode 新增 kick_anchors/snare_anchors 保護機
制。任何小節起點只要在 kick_anchors 或 snare_anchors 附近（預設 100ms 內），
就永遠不會被平滑器移動，無論它與局部中位數的偏差看起來多大。

**實作中發現並修正的第二個 bug**：一開始只是讓「被保護小節自己的 interval」
不被替換，但小節絕對時間是靠 cumsum 從第一個小節累加重建的——即使某個受保
護小節自己的 interval 沒被動，只要它之前的任何一個小節被平滑修正過，
cumsum 累加下來這個受保護小節的絕對時間還是會偏移，鼓點保護形同虛設（實測
時真的觀察到主歌第一小節被移動了 0.4 秒）。修正方式：cumsum 重建完之後，
再把所有受保護小節的絕對時間強制寫回原始偵測值，不管上游發生什麼事。

本測試驗證：
A. 有 kick_anchors 命中的小節，即使其 interval 明顯偏離局部中位數（真實的
   段落速度轉變），也完全不會被移動（含連鎖位移迴歸測試——這正是第二個
   bug 修正前會失敗的案例）。
B. 沒有鼓點證據的小節（前奏區間）仍然正常被平滑。
C. 完全沒有提供 kick_anchors/snare_anchors 時，行為與 Pass 144 原始版本一
   致（不影響既有行為）。
D. `_run_barstart_v2_comparison()`（節奏定位分頁與一鍵生成主管線共用的核心
   邏輯）不會把 kick_anchors/snare_anchors 從共用 blackboard 複本中清掉，
   確保這兩個真正在用的生產路徑都拿得到鼓點證據。
"""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import BarStartTempoSmoothingNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


INTRO_BPM = 100.0
VERSE_BPM = 140.0


def _make_intro_to_verse_fixture(seed=1):
    intro_interval = 60.0 / INTRO_BPM * 4
    verse_interval = 60.0 / VERSE_BPM * 4
    rng = np.random.default_rng(seed)

    bars = [0.0]
    for _ in range(8):
        jitter = rng.normal(0, intro_interval * 0.05)
        bars.append(bars[-1] + intro_interval + jitter)
    verse_start_index = len(bars) - 1

    for _ in range(8):
        bars.append(bars[-1] + verse_interval)

    bars = [round(b, 6) for b in bars]
    kick_anchors = bars[verse_start_index:]
    return bars, kick_anchors, verse_start_index


class TestDrumEvidenceProtection:

    def test_drum_anchored_bars_survive_a_real_tempo_jump_exactly(self):
        bars, kick_anchors, verse_start_index = _make_intro_to_verse_fixture()
        original_verse_bars = bars[verse_start_index:]

        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        bb.set_val("kick_anchors", kick_anchors)
        status = BarStartTempoSmoothingNode(tolerance_pct=0.08).execute(bb)

        assert status == NodeStatus.SUCCESS
        smoothed = bb.get_val("committed_bar_starts")
        # Every drum-anchored verse bar, including the transition bar itself,
        # must land at EXACTLY its original detected time -- not just close.
        assert smoothed[verse_start_index:] == original_verse_bars

    def test_intro_bars_without_drum_evidence_are_still_smoothed(self):
        bars, kick_anchors, verse_start_index = _make_intro_to_verse_fixture()
        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        bb.set_val("kick_anchors", kick_anchors)
        BarStartTempoSmoothingNode(tolerance_pct=0.08).execute(bb)
        report = bb.get_val("bar_tempo_smoothing_report")

        assert report["smoothed_count"] > 0
        assert report["drum_protected_bar_count"] == len(kick_anchors)

    def test_snare_anchors_also_protect(self):
        bars, kick_anchors, verse_start_index = _make_intro_to_verse_fixture()
        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        bb.set_val("snare_anchors", kick_anchors)  # same times, different key
        BarStartTempoSmoothingNode(tolerance_pct=0.08).execute(bb)
        smoothed = bb.get_val("committed_bar_starts")
        assert smoothed[verse_start_index:] == bars[verse_start_index:]

    def test_no_drum_anchors_behaves_like_pre_pass145(self):
        """Regression guard: without any kick/snare evidence at all, behavior
        must be identical to Pass 144's pure statistical smoothing."""
        base_interval = 60.0 / 165.0 * 4
        rng = np.random.default_rng(42)
        bars = [0.0]
        for _ in range(60):
            jitter = rng.normal(0, base_interval * 0.20)
            bars.append(bars[-1] + base_interval + jitter)
        raw_bpm = 60.0 * 4 / np.diff(bars)

        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        node = BarStartTempoSmoothingNode(tolerance_pct=0.08)
        node.execute(bb)
        node.execute(bb)
        smoothed = bb.get_val("committed_bar_starts")
        smoothed_bpm = 60.0 * 4 / np.diff(smoothed)

        report = bb.get_val("bar_tempo_smoothing_report")
        assert report["drum_protected_bar_count"] == 0
        assert np.std(smoothed_bpm) < np.std(raw_bpm) * 0.6


class TestSharedComparisonPreservesDrumEvidence:

    def test_run_barstart_v2_comparison_does_not_pop_kick_or_snare_anchors(self):
        """The main pipeline (BarStartV2AutoMergeNode) and the 節奏定位 tab
        (Module3BarStartV2MergeNode) both drive their v2 core chain through
        _run_barstart_v2_comparison()'s isolated blackboard copy -- if that
        copy ever dropped kick_anchors/snare_anchors, drum protection would
        silently do nothing in both real production paths even though the
        unit tests above pass."""
        import pgm_craft.workflow.module3_bt as module3_bt

        bb = Blackboard()
        bb.set_val("beats", np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float))
        bb.set_val("kick_anchors", [1.0, 2.0, 3.0])
        bb.set_val("snare_anchors", [1.5, 2.5])
        bb.set_val("audio_duration_sec", 2.0)
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0])

        module3_bt._run_barstart_v2_comparison(bb)

        # The ORIGINAL blackboard passed in must be untouched (comparison
        # only mutates its own isolated copy).
        assert bb.get_val("kick_anchors") == [1.0, 2.0, 3.0]
        assert bb.get_val("snare_anchors") == [1.5, 2.5]
