"""
SDD Pass 141 — 打通「一鍵生成」與「節奏定位」的 v1/v2 誠實合併邏輯

稽核背景：使用者問「全自動流程」「自動流程測試（Workflow 診斷）」與「節拍處理」
這一塊的 BT 與節點是否可以互通。調查發現：
1. Stage 3 的準備/分析/精修節點確實透過 build_beat_tracking_preparation_nodes()／
   build_beat_tracking_analysis_nodes()／build_beat_refinement_nodes() 被
   module3_bt.py 直接重用（真共用，不是複製貼上）。
2. 但外層管線完全沒有互通：「⚡ 一鍵生成」固定用 target_stage="full"，只走
   Stage 0~6，途中用的是 Stage 3 的原始 v1 拍點網格；「🎯 節奏定位」是完全
   獨立的 target_stage="module3" 按鈕，才會跑 Module3BarStartV2MergeNode 做
   v1/v2 誠實比較。即使 BarStart v2 在節奏定位分頁測出來品質更好、通過了
   promotion gate，「一鍵生成」下載到的素材包也永遠不會用到 v2 的結果。

使用者確認方向：接上主管線，讓一鍵生成也套用 v1/v2 誠實合併邏輯。

實作時發現的關鍵細節：Module3BarStartV2MergeNode 的嚴格 promotion gate
（evaluate_barstart_v2_promotion_gate）要求 reference_acceptance 與
manual_acceptance 兩個欄位都被人工記錄為 "pass"，但整個一鍵生成流程完全沒有
UI 路徑可以設定這兩個欄位——若直接把這個節點原封不動接進主管線，每次一鍵生成
都會多跑一次完整的 v2 引擎（增加處理時間），但 promotable 永遠是 False，v2
的改進永遠不會被真正採用。

使用者確認方向（本 Pass 當時的結論）：主管線改用「自動分數閘門」
（evaluate_barstart_v2_auto_promotion_gate），不需要人工驗收，只要 v2 沒有
unresolved_bar_spans 且品質分數確實高於 v1 就自動採用。節奏定位分頁維持原本
嚴格的人工驗收 gate 不變。

**後續更新（Pass 142）**：使用者實測後確認 v2 品質穩定優於 v1，要求「全部都
改用 v2、不再做 v1/v2 比對」。`evaluate_barstart_v2_auto_promotion_gate()` 與
節奏定位分頁的嚴格 `evaluate_barstart_v2_promotion_gate()` 都已被
`evaluate_barstart_v2_completeness()` 取代（見 tests/test_sdd_pass142.py）——
本檔案裡原本針對自動分數閘門的專屬測試（TestAutoPromotionGate）已隨函式刪除
一併移除；仍然有效的部分（BarStartV2AutoMergeNode 的基本行為、管線組裝正確性）
維持不動，只更新了跟著閘門欄位改名的斷言（`promotable` → `adoptable`）。

本測試驗證：
A. BarStartV2AutoMergeNode：沒有 v1 網格時安全跳過；v2 完整且無 unresolved
   span 時自動採用，不需要任何 reference/manual acceptance 欄位；且不寫出
   legacy/comparison A/B 音檔（那是節奏定位分頁專屬的診斷輸出）；冪等。
B. build_master_pipeline_tree("full") 與 target_stage="stage4"/"stage5"/"stage6"
   的樹裡確實包含 BarStartV2AutoMergeNode；target_stage="stage3" 的樹不包含
   （維持 Stage 3 純粹輸出，方便單獨診斷）；build_full_pipeline_tree() 同步更新。
"""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.builder import build_master_pipeline_tree, build_full_pipeline_tree
from pgm_craft.workflow.module3_bt import BarStartV2AutoMergeNode, Module3BarStartV2MergeNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


# ---------------------------------------------------------------------------
# A. BarStartV2AutoMergeNode
# ---------------------------------------------------------------------------

class TestBarStartV2AutoMergeNode:

    def test_leaves_v1_grid_untouched_when_no_beats_present(self):
        bb = Blackboard()
        assert BarStartV2AutoMergeNode().execute(bb) == NodeStatus.SUCCESS
        report = bb.get_val("barstart_v2_auto_report")
        assert report["status"] == "AUTO_MERGE_SKIPPED"
        assert report["reason"] == "no_v1_beats_to_compare"
        assert report["promoted"] is False

    def test_promotes_without_any_human_acceptance_fields(self, tmp_path):
        """Same fixture shape as
        test_module3_barstart_v2_merge_node_promotes_when_gate_passes_and_v2_scores_higher
        in test_module3_bt.py, but deliberately WITHOUT
        barstart_v2_reference_acceptance/barstart_v2_manual_acceptance --
        the whole point of the auto gate is that it never needs them."""
        audio_path = tmp_path / "source.wav"
        sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

        bb = Blackboard()
        bad_beats = np.array([
            [0.0, 1], [0.05, 2], [3.0, 3], [3.02, 4],
            [3.5, 1], [8.0, 2], [8.01, 3], [8.5, 4],
        ], dtype=float)
        bb.set_val("beats", bad_beats.copy())
        bb.set_val("refined_beats", bad_beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 4.0)
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0, 3.0, 4.0])
        # No barstart_v2_reference_acceptance / barstart_v2_manual_acceptance set.

        assert BarStartV2AutoMergeNode().execute(bb) == NodeStatus.SUCCESS

        report = bb.get_val("barstart_v2_auto_report")
        assert report["status"] == "AUTO_PROMOTED"
        assert report["promoted"] is True
        assert report["auto_promotion_gate"]["adoptable"] is True
        assert report["quality_comparison"]["v2_scores_higher"] is True
        assert report["unresolved_bar_span_count"] == 0

        # v1's own (bad) grid must actually have been replaced.
        assert not np.array_equal(bb.get_val("beats"), bad_beats)
        assert not np.array_equal(bb.get_val("refined_beats"), bad_beats)

    def test_does_not_write_legacy_or_comparison_audio_artifacts(self, tmp_path):
        """Unlike Module3BarStartV2MergeNode, the main-pipeline auto node
        must not produce the diagnostic A/B click/mix wav files -- those are
        a 節奏定位-tab-only concern."""
        audio_path = tmp_path / "source.wav"
        sf.write(audio_path, np.zeros(22050 * 4, dtype=np.float32), 22050)

        bb = Blackboard()
        bad_beats = np.array([
            [0.0, 1], [0.05, 2], [3.0, 3], [3.02, 4],
            [3.5, 1], [8.0, 2], [8.01, 3], [8.5, 4],
        ], dtype=float)
        bb.set_val("beats", bad_beats.copy())
        bb.set_val("refined_beats", bad_beats.copy())
        bb.set_val("audio_path", str(audio_path))
        bb.set_val("project_dir", str(tmp_path))
        bb.set_val("audio_duration_sec", 4.0)
        bb.set_val("manual_bar_starts", [0.0, 1.0, 2.0, 3.0, 4.0])

        assert BarStartV2AutoMergeNode().execute(bb) == NodeStatus.SUCCESS

        for key in (
            "barstart_v2_click_track", "barstart_v2_mix_with_click",
            "module3_legacy_click_track", "module3_legacy_mix_with_click",
            "module3_legacy_beats", "barstart_v2_report",
        ):
            assert bb.get_val(key) is None

    def test_idempotent_when_already_run(self):
        bb = Blackboard()
        bb.set_val("barstart_v2_auto_report", {"status": "AUTO_PROMOTED", "promoted": True})
        bb.set_val("beats", "sentinel")
        assert BarStartV2AutoMergeNode().execute(bb) == NodeStatus.SUCCESS
        assert bb.get_val("beats") == "sentinel"


# ---------------------------------------------------------------------------
# B. Pipeline wiring
# ---------------------------------------------------------------------------

class TestMainPipelineWiring:

    def test_full_pipeline_includes_auto_merge_node_after_stage3(self):
        tree = build_master_pipeline_tree(target_stage="full")
        names = _node_names(tree)
        assert "BarStartV2AutoMergeNode" in names
        assert names.index("BeatTrackingRoot") < names.index("BarStartV2AutoMergeNode")

    def test_stage4_and_later_include_auto_merge_node(self):
        for stage in ("stage4", "stage5", "stage6"):
            tree = build_master_pipeline_tree(target_stage=stage)
            assert "BarStartV2AutoMergeNode" in _node_names(tree), stage

    def test_stage3_truncation_does_not_include_auto_merge_node(self):
        """Stage 3 diagnostic truncation should reflect pure Stage 3 output."""
        tree = build_master_pipeline_tree(target_stage="stage3")
        assert "BarStartV2AutoMergeNode" not in _node_names(tree)

    def test_module3_tree_unaffected_by_new_node(self):
        """The isolated 節奏定位 tab keeps using the strict human-acceptance
        Module3BarStartV2MergeNode -- the new auto node must not appear there."""
        tree = build_master_pipeline_tree(target_stage="module3")
        names = _node_names(tree)
        assert "Module3BarStartV2MergeNode" in names
        assert "BarStartV2AutoMergeNode" not in names

    def test_build_full_pipeline_tree_also_includes_auto_merge_node(self):
        tree = build_full_pipeline_tree()
        names = _node_names(tree)
        assert "BarStartV2AutoMergeNode" in names
        assert names.index("BeatTrackingRoot") < names.index("BarStartV2AutoMergeNode")
