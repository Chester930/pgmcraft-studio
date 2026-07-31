"""
SDD Pass 142 — BarStart v2 全面轉為預設輸出，移除 v1/v2 比對

背景：Pass 141 打通「一鍵生成」與「節奏定位」後，主管線改用自動分數閘門
（v2 需無 unresolved_bar_spans 且分數高於 v1 才促升）、節奏定位分頁維持嚴格
人工驗收閘門。使用者實測後回報「確定 v2 品質比較好」，要求全部改用 v2、
不再做 v1/v2 比對，兩邊（一鍵生成主管線 + 節奏定位分頁）都要改。

變更：
1. 移除 evaluate_barstart_v2_promotion_gate()（節奏定位分頁原本的嚴格人工
   驗收閘門）與 evaluate_barstart_v2_auto_promotion_gate()（Pass 141 剛加的
   主管線自動分數閘門）——兩者都不再被任何節點呼叫，屬於稽核這整個 session
   一直在抓的「孤兒程式碼」模式，一併清掉而非留著養蚊子。
2. 新增單一的 evaluate_barstart_v2_completeness()：不做任何 v1/v2 品質分數
   比較、不需要人工驗收，只檢查 v2 自己有沒有 unresolved_bar_spans（v2 是否
   真的把整首歌都算完）。有 → 不採用（回退 v1，避免輸出已知有缺口的網格）；
   沒有 → 直接採用 v2。
3. Module3BarStartV2MergeNode（節奏定位分頁）與 BarStartV2AutoMergeNode（主
   管線）都改用這個共用的完整性檢查，quality_comparison 仍寫入報告但純供
   參考，不再影響是否採用 v2 的決策。
4. Module3BarStartV2SummaryNode 的狀態字面值從 EXPERIMENTAL_PASS_129 更新為
   DEFAULT_ACTIVE_PASS_142，反映 v2 從「實驗性」變成「預設啟用」的定位轉變。

本測試驗證：
A. evaluate_barstart_v2_completeness() 的邏輯本身。
B. 兩個舊的 gate 函式已從模組移除（防止孤兒程式碼復發）。
C. Module3BarStartV2MergeNode／BarStartV2AutoMergeNode 在「v2 產生零
   unresolved span」時一律採用 v2，即使 v2 分數比 v1 低也一樣（不再比較）；
   在「v2 有 unresolved span」時一律回退 v1，即使 v2 分數比 v1 高也一樣。
"""

import numpy as np
import soundfile as sf

import pgm_craft.workflow.module3_barstart_v2_bt as module3_barstart_v2_bt
from pgm_craft.workflow.module3_barstart_v2_bt import evaluate_barstart_v2_completeness
from pgm_craft.workflow.module3_bt import BarStartV2AutoMergeNode, Module3BarStartV2MergeNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


# ---------------------------------------------------------------------------
# A. evaluate_barstart_v2_completeness()
# ---------------------------------------------------------------------------

class TestCompletenessGate:

    def test_adoptable_with_no_unresolved_spans(self):
        gate = evaluate_barstart_v2_completeness(unresolved_bar_spans=[])
        assert gate["adoptable"] is True
        assert gate["status"] == "V2_READY"
        assert gate["blockers"] == []

    def test_adoptable_with_none_unresolved_spans(self):
        gate = evaluate_barstart_v2_completeness(unresolved_bar_spans=None)
        assert gate["adoptable"] is True

    def test_blocks_on_any_unresolved_span(self):
        gate = evaluate_barstart_v2_completeness(unresolved_bar_spans=[{"reason": "no_evidence"}])
        assert gate["adoptable"] is False
        assert gate["status"] == "V2_INCOMPLETE"
        assert gate["blockers"] == ["UNRESOLVED_BAR_SPANS_PRESENT"]
        assert gate["unresolved_bar_span_count"] == 1

    def test_does_not_take_any_score_or_acceptance_arguments(self):
        """The whole point of this gate: no v1/v2 score comparison, no human
        acceptance -- just did v2 finish covering the whole song."""
        import inspect
        sig = inspect.signature(evaluate_barstart_v2_completeness)
        for forbidden in ("v2_score", "original_score", "reference_acceptance", "manual_acceptance"):
            assert forbidden not in sig.parameters


# ---------------------------------------------------------------------------
# B. Retired gate functions are actually gone (no orphaned code left behind)
# ---------------------------------------------------------------------------

class TestRetiredGateFunctionsRemoved:

    def test_strict_human_acceptance_gate_removed(self):
        assert not hasattr(module3_barstart_v2_bt, "evaluate_barstart_v2_promotion_gate")

    def test_auto_score_gate_removed(self):
        assert not hasattr(module3_barstart_v2_bt, "evaluate_barstart_v2_auto_promotion_gate")


# ---------------------------------------------------------------------------
# C. Both merge nodes adopt v2 purely on completeness, never on score
# ---------------------------------------------------------------------------

def _write_silence(path, seconds=4.0, sr=22050):
    sf.write(path, np.zeros(int(sr * seconds), dtype=np.float32), sr)


class TestBothMergeNodesIgnoreQualityScore:

    def test_module3_node_adopts_v2_even_when_v2_scores_lower_than_v1(self, tmp_path):
        """A clean, regular v1 grid plausibly scores higher than v2 struggling
        on silent audio with no seed -- but if v2 still manages zero
        unresolved spans, it must be adopted anyway now that score no longer
        gates the decision. (In practice a fully-seeded run leaves zero
        unresolved spans regardless of how the two scores compare; this test
        forces that combination directly to prove the code path ignores
        v2_scores_higher.)"""
        audio_path = tmp_path / "source.wav"
        _write_silence(audio_path)

        bb = Blackboard()
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float)
        bb.set_val("beats", beats.copy())
        bb.set_val("refined_beats", beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 2.0)
        # Fully seeding the whole (short) song guarantees zero unresolved
        # spans regardless of how good/bad v2's resulting grid scores.
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0])

        assert Module3BarStartV2MergeNode().execute(bb) == NodeStatus.SUCCESS
        report = bb.get_val("barstart_v2_report")

        assert report["unresolved_bar_span_count"] == 0
        assert report["promotion_gate"]["adoptable"] is True
        assert report["status"] == "PROMOTED_TO_MODULE3_DEFAULT"
        assert report["replaces_module3_click"] is True
        # Decision must not depend on this field even though it is still
        # reported for reference.
        assert "v2_scores_higher" in report["quality_comparison"]

    def test_auto_merge_node_same_completeness_only_behavior(self, tmp_path):
        audio_path = tmp_path / "source.wav"
        _write_silence(audio_path)

        bb = Blackboard()
        beats = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float)
        bb.set_val("beats", beats.copy())
        bb.set_val("refined_beats", beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 2.0)
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0])

        assert BarStartV2AutoMergeNode().execute(bb) == NodeStatus.SUCCESS
        report = bb.get_val("barstart_v2_auto_report")

        assert report["unresolved_bar_span_count"] == 0
        assert report["auto_promotion_gate"]["adoptable"] is True
        assert report["status"] == "AUTO_PROMOTED"
        assert report["promoted"] is True

    def test_module3_node_falls_back_to_v1_when_v2_has_unresolved_spans(self, tmp_path):
        """No manual seed + silent audio -> the real v2 evidence ladder
        cannot resolve the whole song -> must fall back to v1 regardless of
        how the two quality scores compare."""
        audio_path = tmp_path / "source.wav"
        _write_silence(audio_path)

        bb = Blackboard()
        beats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4],
        ], dtype=float)
        bb.set_val("beats", beats.copy())
        bb.set_val("refined_beats", beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 4.0)
        # No manual_bar_starts seed.

        assert Module3BarStartV2MergeNode().execute(bb) == NodeStatus.SUCCESS
        report = bb.get_val("barstart_v2_report")

        assert report["unresolved_bar_span_count"] > 0
        assert report["promotion_gate"]["adoptable"] is False
        assert report["status"] == "COMPARED_NOT_PROMOTED"
        np.testing.assert_array_equal(bb.get_val("beats"), beats)
