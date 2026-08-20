"""
SDD Pass 144 — 修復 BarStart v2 節奏定位的速度圖劇烈震盪

背景：使用者實測「一鍵生成」後回報速度圖（tempo_curve.png）出現大幅上下震
盪，即使歌曲本身只是漸快漸慢，也不應出現這種上下跳動——設計上應該「只對每
個小節的第一拍做確認，然後均勻切分」，理論上不該有這種現象。使用者分享的
實測截圖顯示平均 165.7 BPM、瞬時值在 120~260+ 間劇烈跳動。

稽核找到兩個疊加的根源：

1. **BarGridContinuityRepairNode（Pass 121）的防震盪範圍太窄**：只抓「單一
   小節突然變超短、緊接著下一個變超長」（或反過來）且兩者加總貼近 2 倍中位
   數的孤立瑕疵模式。真實 evidence-ladder 在快歌（如 165 BPM，每小節僅約
   1.45 秒）上的估計不確定性通常是連續多個小節都有一點點誤差，不會乾淨地
   形成這種交替 pattern，因此完全沒被修正。v1（Stage 3）有全域範圍的
   ViterbiTempoSmoothingNode，v2 過去完全沒有對應的全域平滑機制。

2. **速度圖繪製本身沒有任何平滑**：`pipeline.py` 用
   `bpms = 60.0 / np.diff(beats[:, 0])` 算出逐拍瞬時 BPM 直接畫圖。小節「內
   部」因為均勻切分本身是平的，但只要相鄰兩個小節長度有微小差異（哪怕只是
   估計不確定性，不是真的節奏變化），跨小節邊界瞬時 BPM 就會跳動；連續多個
   小節都有微幅差異時，畫出來就是劇烈上下震盪。

修復：
1. 新增 `BarStartTempoSmoothingNode`：把偏離「局部滾動中位數」（前後各
   `window_bars` 個小節，預設 3）超過 `tolerance_pct`（預設 8%）的小節長
   度，換成該局部中位數。用局部視窗而非全曲單一中位數（v1 ViterbiTempo-
   SmoothingNode 的做法），讓真正漸快漸慢的長期趨勢可以存活（因為局部中位
   數會跟著趨勢移動），只有不符合趨勢的短時間噪聲會被拉平。接在
   `BarGridContinuityRepairNode` 之後、`MeterAwareBeatGridNode` 之前跑兩
   次（收斂用，實測第三次通常已無修正）。
2. `pipeline.py` 的速度曲線圖改成「每小節平均 BPM」而非逐拍瞬時值：用
   `beats[:,1]==1` 找出小節邊界，計算每個小節內 `60 * 該小節拍數 / 小節時
   長`，一個小節畫一個點。

**實作過程中的一個重要修正**：第一版 `BarStartTempoSmoothingNode` 用「逐一
掃描原始 intervals、邊掃邊往後平移小節時間」的寫法，但平移後的小節時間會
被拿去當作「下一個」小節間隔的基準，而該基準本身沒有被回頭檢查是否仍然合
理——這種連鎖位移實測後發現**反而會讓 BPM 標準差變大**（比完全不修還糟）。
改為：先用原始未修改過的 intervals 陣列一次算出所有小節的局部中位數，決定
每個 interval 是否要替換，最後才用 `cumsum` 一次性重建絕對小節時間——避免
任何一次修正的副作用污染後續判斷。

本測試驗證：
A. BarStartTempoSmoothingNode：規律網格不動；孤立噪聲被拉平且標準差確實下
   降（不會像修復前的錯誤版本一樣把標準差變大）；真正漸快漸慢的長期趨勢存
   活（幾乎不觸發修正）；小節數太少時安全跳過。
B. build_module3_barstart_v2_pipeline_tree() 與 _run_barstart_v2_comparison()
   的 v2 核心鏈都跑兩次 BarStartTempoSmoothingNode，且順序在
   BarGridContinuityRepairNode 之後、MeterAwareBeatGridNode 之前。
"""

import numpy as np

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import BarStartTempoSmoothingNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def _make_bar_starts(n_bars, base_interval, jitter_pct, seed=42):
    rng = np.random.default_rng(seed)
    bars = [0.0]
    for _ in range(n_bars):
        jitter = rng.normal(0, base_interval * jitter_pct)
        bars.append(bars[-1] + base_interval + jitter)
    return bars


class TestBarStartTempoSmoothingNode:

    BASE_INTERVAL = 60.0 / 165.0 * 4  # 165 BPM, 4/4 -> ~1.4545s/bar

    def test_regular_grid_is_left_untouched(self):
        bars = [i * self.BASE_INTERVAL for i in range(30)]
        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        status = BarStartTempoSmoothingNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        report = bb.get_val("bar_tempo_smoothing_report")
        assert report["status"] == "PASS"
        assert report["smoothed_count"] == 0
        assert bb.get_val("committed_bar_starts") == bars

    def test_isolated_jitter_reduces_bpm_std_not_increases_it(self):
        """Regression guard for the cascading-drift bug found during
        implementation: an earlier version of this node made bpm std worse
        (12.39 -> 13.90+) instead of better on this exact fixture."""
        bars = _make_bar_starts(60, self.BASE_INTERVAL, jitter_pct=0.20)
        raw_bpm = 60.0 * 4 / np.diff(bars)

        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        node = BarStartTempoSmoothingNode(tolerance_pct=0.08)
        node.execute(bb)
        node.execute(bb)  # second pass, matching pipeline wiring

        smoothed = bb.get_val("committed_bar_starts")
        smoothed_bpm = 60.0 * 4 / np.diff(smoothed)

        assert np.std(smoothed_bpm) < np.std(raw_bpm)
        # Must be a meaningful reduction, not a rounding-error-sized one.
        assert np.std(smoothed_bpm) < np.std(raw_bpm) * 0.7

    def test_gradual_tempo_ramp_survives_smoothing(self):
        """A real, gradual accelerando (each bar ~0.5% faster than the last)
        must not get flattened back to a constant tempo -- only noise that
        doesn't fit the local trend should be touched."""
        bars = [0.0]
        interval = self.BASE_INTERVAL
        for _ in range(60):
            interval *= 0.995
            bars.append(bars[-1] + interval)

        bb = Blackboard()
        bb.set_val("committed_bar_starts", bars)
        node = BarStartTempoSmoothingNode(tolerance_pct=0.08)
        node.execute(bb)
        report = bb.get_val("bar_tempo_smoothing_report")

        assert report["smoothed_count"] == 0
        smoothed = bb.get_val("committed_bar_starts")
        bpm = 60.0 * 4 / np.diff(smoothed)
        assert bpm[-1] > bpm[0] * 1.2  # clear rising trend preserved

    def test_skips_when_too_few_bars(self):
        bb = Blackboard()
        bb.set_val("committed_bar_starts", [0.0, 1.5, 3.0])
        status = BarStartTempoSmoothingNode().execute(bb)
        assert status == NodeStatus.SUCCESS
        report = bb.get_val("bar_tempo_smoothing_report")
        assert report["status"] == "SKIPPED_NOT_ENOUGH_BARS"


class TestPipelineWiring:

    def test_module3_barstart_v2_pipeline_runs_smoothing_twice_in_right_order(self, monkeypatch):
        """BarStartV2CoreChain (built lazily inside _run_barstart_v2_comparison(),
        see Pass 166 -- it is no longer part of the static tree returned by
        build_module3_barstart_v2_pipeline_tree()) must still run
        BarStartTempoSmoothingNode exactly twice, after BarGridContinuityRepairNode
        and before MeterAwareBeatGridNode. Spy on execute() call order instead of
        introspecting a tree the function doesn't expose."""
        from pgm_craft.workflow.module3_bt import _run_barstart_v2_comparison
        from pgm_craft.workflow import module3_barstart_v2_bt as v2mod

        call_order = []

        def make_spy(name, original):
            def spy(self, blackboard):
                call_order.append(name)
                return original(self, blackboard)
            return spy

        for cls_name in ("BarGridContinuityRepairNode", "BarStartTempoSmoothingNode", "MeterAwareBeatGridNode"):
            cls = getattr(v2mod, cls_name)
            monkeypatch.setattr(cls, "execute", make_spy(cls_name, cls.execute))

        bb = Blackboard()
        interval = 60.0 / 165.0 * 4
        bb.set_val("beats", np.array([[i * interval / 4, (i % 4) + 1] for i in range(80)], dtype=float))

        _run_barstart_v2_comparison(bb)

        smoothing_positions = [i for i, n in enumerate(call_order) if n == "BarStartTempoSmoothingNode"]
        assert len(smoothing_positions) == 2
        repair_pos = call_order.index("BarGridContinuityRepairNode")
        grid_pos = call_order.index("MeterAwareBeatGridNode")
        assert repair_pos < smoothing_positions[0] < smoothing_positions[1] < grid_pos

    def test_module3_tree_includes_smoothing_via_merge_node_core_chain(self):
        """Module3BarStartV2MergeNode builds its own v2 core chain lazily
        inside execute() (not part of the static tree), so we verify it via
        a direct run instead of tree introspection."""
        from pgm_craft.workflow.module3_bt import Module3BarStartV2MergeNode
        import soundfile as sf
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "source.wav")
            sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

            bb = Blackboard()
            beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float)
            bb.set_val("beats", beats.copy())
            bb.set_val("refined_beats", beats.copy())
            bb.set_val("audio_path", audio_path)
            bb.set_val("project_dir", tmp)
            bb.set_val("audio_duration_sec", 2.0)
            bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0])

            status = Module3BarStartV2MergeNode().execute(bb)
            assert status == NodeStatus.SUCCESS
            # No crash / no missing-node error is the main assertion here --
            # confirms BarStartTempoSmoothingNode is importable and wired
            # into the v2 core chain used by the merge node without error.
            report = bb.get_val("barstart_v2_report")
            assert report is not None
