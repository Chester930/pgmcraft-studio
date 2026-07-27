import unittest
import os
import shutil
import tempfile
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, SequenceNode, FallbackNode, Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import (
    VideoURLDownloadNode,
    AudioLoadNode,
    BeatNetNode,
    LibrosaBeatNode,
    BeatValidationNode,
    DownbeatRefineNode,
    MeasureMapNode,
)
from pgm_craft.workflow.builder import BTWorkflowEngine, build_pgm_workflow_tree


class StaticStatusNode(BaseNode):
    def __init__(self, name, status):
        super().__init__(name)
        self.status = status

    def execute(self, blackboard):
        return self.status


class RequiredInputNode(StaticStatusNode):
    required_keys = ["required_input"]
    output_keys = ["static_status"]


class TestBTWorkflowEngine(unittest.TestCase):
    def setUp(self):
        self.test_audio = "sample_test.wav"
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_video_url_download_node_local_skip(self):
        """測試 VideoURLDownloadNode：輸入為本地檔案時自動 PASS 並跳過下載」"""
        node = VideoURLDownloadNode()
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_audio)
        status = node.execute(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("audio_path"), self.test_audio)

    def test_main_workflow_nodes_expose_blackboard_contract_metadata(self):
        """測試主要 BT 節點都有 blackboard 契約 metadata"""
        tree = build_pgm_workflow_tree()
        nodes = self._flatten_tree(tree)
        concrete_nodes = [
            node for node in nodes
            if node.__class__.__name__ not in {"SequenceNode", "FallbackNode", "ParallelNode"}
        ]

        for node in concrete_nodes:
            self.assertIsInstance(node.required_keys, list, node.name)
            self.assertIsInstance(node.optional_keys, list, node.name)
            self.assertIsInstance(node.output_keys, list, node.name)
            self.assertGreater(len(node.output_keys), 0, node.name)

        contract_by_name = {node.name: node for node in nodes}
        self.assertEqual(contract_by_name["AudioLoadNode"].required_keys, ["audio_path"])
        self.assertIn("target_analysis_path", contract_by_name["AudioLoadNode"].output_keys)
        beatnet_node = contract_by_name.get("BeatNetNode_TrackA") or contract_by_name.get("BeatNetNode")
        self.assertIsNotNone(beatnet_node)
        self.assertTrue("beats" in beatnet_node.output_keys or "beats_rhythm" in beatnet_node.output_keys)
        self.assertIn("workflow_trace", tree.output_keys)

    def test_blackboard_contract_document_lists_core_keys(self):
        """測試 blackboard contract 文件保留核心 key"""
        contract_path = os.path.join("docs", "BLACKBOARD-CONTRACT.md")
        with open(contract_path, "r", encoding="utf-8") as f:
            contract = f.read()

        for key in (
            "audio_path",
            "target_analysis_path",
            "beats",
            "beat_validation",
            "measure_map",
            "workflow_status",
            "workflow_trace",
            "validate_contracts",
            "contract_validation",
            "tempo_map_midi",
            "click_guide_midi",
            "sections_json",
            "measure_map_json",
            "ai_model_status",
        ):
            self.assertIn(f"`{key}`", contract)

    def test_contract_validation_records_missing_keys_without_blocking(self):
        """測試 contract validation：缺 key 時只記錄，不主動中斷節點執行"""
        node = RequiredInputNode("NeedsInput", NodeStatus.SUCCESS)
        blackboard = Blackboard()
        blackboard.set_val("validate_contracts", True)

        status = node.run(blackboard)
        validations = blackboard.get_val("contract_validation")

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(validations[0]["node"], "NeedsInput")
        self.assertEqual(validations[0]["status"], "WARN")
        self.assertEqual(validations[0]["missing_required_keys"], ["required_input"])
        self.assertEqual(blackboard.get_val("workflow_trace")[-1]["status"], "SUCCESS")

    def test_bt_engine_contract_validation_passes_on_full_run(self):
        """測試完整 BT run 啟用 contract validation 時會記錄每個節點契約狀態"""
        bt_engine = BTWorkflowEngine()
        blackboard = bt_engine.run(
            self.test_audio,
            output_dir=self.temp_dir,
            enable_stem=True,
            target_stage="stage5",
            validate_contracts=True,
        )
        validations = blackboard.get_val("contract_validation")

        self.assertEqual(blackboard.get_val("workflow_status"), "SUCCESS")
        self.assertIsInstance(validations, list)
        self.assertGreater(len(validations), 0)
        self.assertEqual(validations[0]["node"], "PGMCraftWorkflowRoot")
        self.assertEqual(
            [entry for entry in validations if entry["missing_required_keys"]],
            [],
        )

    def _flatten_tree(self, node):
        nodes = [node]
        for child in getattr(node, "children", []):
            nodes.extend(self._flatten_tree(child))
        return nodes

    def test_bt_fallback_selector(self):
        """測試 BT Selector/Fallback 控制節點：當第一個失敗時自動降級跑第二個"""
        fallback_node = FallbackNode("BeatTrackingSelector", [
            BeatNetNode(),
            LibrosaBeatNode()
        ])
        
        blackboard = Blackboard()
        blackboard.set_val("audio_path", self.test_audio)
        blackboard.set_val("target_analysis_path", self.test_audio)

        status = fallback_node.execute(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertIsNotNone(blackboard.get_val("beats"))

    def test_sequence_records_workflow_trace_and_stops_on_failure(self):
        """測試 SequenceNode：run 時記錄 trace，且子節點失敗後停止"""
        sequence = SequenceNode("Root", [
            StaticStatusNode("First", NodeStatus.SUCCESS),
            StaticStatusNode("Second", NodeStatus.FAILURE),
            StaticStatusNode("Third", NodeStatus.SUCCESS),
        ])
        blackboard = Blackboard()

        status = sequence.run(blackboard)
        trace = blackboard.get_val("workflow_trace")

        self.assertEqual(status, NodeStatus.FAILURE)
        self.assertEqual([entry["node"] for entry in trace], ["First", "Second", "Root"])
        self.assertEqual([entry["status"] for entry in trace], ["SUCCESS", "FAILURE", "FAILURE"])
        self.assertEqual(trace[0]["parent"], "Root")
        self.assertEqual(trace[-1]["parent"], None)
        self.assertEqual([entry["index"] for entry in trace], [0, 1, 2])

    def test_fallback_records_failed_and_successful_candidates(self):
        """測試 FallbackNode：run 時保留失敗候選與成功候選的 trace"""
        fallback = FallbackNode("Selector", [
            StaticStatusNode("Primary", NodeStatus.FAILURE),
            StaticStatusNode("Fallback", NodeStatus.SUCCESS),
        ])
        blackboard = Blackboard()

        status = fallback.run(blackboard)
        trace = blackboard.get_val("workflow_trace")

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual([entry["node"] for entry in trace], ["Primary", "Fallback", "Selector"])
        self.assertEqual([entry["status"] for entry in trace], ["FAILURE", "SUCCESS", "SUCCESS"])
        self.assertEqual(trace[0]["parent"], "Selector")

    def test_beat_validation_pass(self):
        """測試 BeatValidationNode：穩定 120 BPM 與 downbeat 標籤應通過"""
        node = BeatValidationNode()
        blackboard = Blackboard()
        blackboard.set_val("beats", np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 4],
            [2.0, 1],
        ]))

        status = node.execute(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("beat_confidence_level"), "PASS")
        self.assertEqual(blackboard.get_val("beat_warnings"), [])

    def test_beat_validation_warns_on_bpm_jump(self):
        """測試 BeatValidationNode：BPM 跳動過大時警告但不中斷流程"""
        node = BeatValidationNode()
        blackboard = Blackboard()
        blackboard.set_val("beats", np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.08, 4],
            [1.58, 1],
        ]))

        status = node.execute(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("beat_confidence_level"), "WARN")
        self.assertGreater(len(blackboard.get_val("beat_warnings")), 0)

    def test_beat_validation_allows_variable_measure_lengths(self):
        """測試 BeatValidationNode：同一首內不同小節長度應保留資訊，不視為錯誤"""
        node = BeatValidationNode()
        blackboard = Blackboard()
        blackboard.set_val("beats", np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 1],
            [2.0, 2],
            [2.5, 3],
            [3.0, 4],
            [3.5, 1],
        ]))

        status = node.execute(blackboard)
        stats = blackboard.get_val("beat_validation")["stats"]

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("beat_confidence_level"), "PASS")
        self.assertEqual(stats["measure_lengths"], [3, 4])
        self.assertTrue(stats["has_variable_measure_lengths"])
        self.assertEqual(stats["meter_status"], "detected_variable")

    def test_beat_validation_fails_on_invalid_timestamps(self):
        """測試 BeatValidationNode：timestamp 錯序時停止流程"""
        node = BeatValidationNode()
        blackboard = Blackboard()
        blackboard.set_val("beats", np.array([
            [0.0, 1],
            [0.5, 2],
            [0.4, 3],
            [1.0, 4],
        ]))

        status = node.execute(blackboard)

        self.assertEqual(status, NodeStatus.FAILURE)
        self.assertEqual(blackboard.get_val("beat_confidence_level"), "FAIL")
        self.assertGreater(len(blackboard.get_val("beat_errors")), 0)

    def test_downbeat_refine_preserves_existing_downbeats(self):
        """測試 DownbeatRefineNode：已有 downbeat 時保留原標籤"""
        node = DownbeatRefineNode()
        blackboard = Blackboard()
        beats = np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 4],
            [2.0, 1],
        ])
        blackboard.set_val("beat_validation", {"status": "PASS", "warnings": []})
        blackboard.set_val("beats", beats)

        status = node.execute(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("downbeat_refine_status"), "PASS")
        self.assertEqual(blackboard.get_val("downbeat_refinement")["source"], "existing_downbeats")
        np.testing.assert_array_equal(blackboard.get_val("refined_beats"), beats)

    def test_downbeat_refine_creates_fallback_candidates_without_downbeats(self):
        """測試 DownbeatRefineNode：沒有 downbeat 時建立 4 拍候選並標記 WARN"""
        node = DownbeatRefineNode()
        blackboard = Blackboard()
        blackboard.set_val("beat_validation", {"status": "WARN", "warnings": []})
        blackboard.set_val("beats", np.array([
            [0.0, 2],
            [0.5, 3],
            [1.0, 4],
            [1.5, 2],
            [2.0, 3],
        ]))

        status = node.execute(blackboard)
        refined = blackboard.get_val("refined_beats")

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("downbeat_refine_status"), "WARN")
        self.assertEqual(blackboard.get_val("downbeat_refinement")["source"], "fallback_candidate_4beat")
        self.assertEqual(refined[:, 1].astype(int).tolist(), [1, 2, 3, 4, 1])
        self.assertGreater(len(blackboard.get_val("downbeat_candidates")), 0)

    def test_downbeat_refine_warns_on_abnormal_measure_length(self):
        """測試 DownbeatRefineNode：明顯異常小節長度只警告，不自動修正"""
        node = DownbeatRefineNode()
        blackboard = Blackboard()
        beats = np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 4],
            [2.0, 2],
            [2.5, 3],
            [3.0, 4],
            [3.5, 2],
            [4.0, 3],
            [4.5, 1],
        ])
        blackboard.set_val("beat_validation", {"status": "PASS", "warnings": []})
        blackboard.set_val("beats", beats)

        status = node.execute(blackboard)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("downbeat_refine_status"), "WARN")
        np.testing.assert_array_equal(blackboard.get_val("refined_beats"), beats)
        self.assertGreater(len(blackboard.get_val("downbeat_refine_warnings")), 0)

    def test_measure_map_uses_downbeats_and_variable_lengths(self):
        """測試 MeasureMapNode：有 downbeat 時依 downbeat 切小節並保留變動拍數"""
        node = MeasureMapNode()
        blackboard = Blackboard()
        blackboard.set_val("beat_validation", {"status": "PASS", "warnings": []})
        blackboard.set_val("beats", np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 1],
            [2.0, 2],
            [2.5, 3],
            [3.0, 4],
            [3.5, 1],
        ]))

        status = node.execute(blackboard)
        measure_map = blackboard.get_val("measure_map")

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("measure_map_status"), "PASS")
        self.assertEqual([measure["beat_count"] for measure in measure_map], [3, 4, 1])
        self.assertTrue(measure_map[0]["is_variable_length"])
        self.assertFalse(measure_map[1]["is_variable_length"])
        self.assertTrue(measure_map[2]["is_incomplete"])
        self.assertEqual(measure_map[0]["source"], "downbeat")

    def test_measure_map_falls_back_without_downbeats(self):
        """測試 MeasureMapNode：缺少 downbeat 時以 4 拍 fallback 並標記警告"""
        node = MeasureMapNode()
        blackboard = Blackboard()
        blackboard.set_val("beat_validation", {"status": "WARN", "warnings": ["沒有偵測到 downbeat 標籤。"]})
        blackboard.set_val("beats", np.array([
            [0.0, 2],
            [0.5, 3],
            [1.0, 4],
            [1.5, 2],
            [2.0, 3],
        ]))

        status = node.execute(blackboard)
        measure_map = blackboard.get_val("measure_map")

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("measure_map_status"), "WARN")
        self.assertEqual([measure["beat_count"] for measure in measure_map], [4, 1])
        self.assertEqual(measure_map[0]["source"], "fallback_4beat")
        self.assertTrue(measure_map[1]["is_incomplete"])
        self.assertGreater(len(blackboard.get_val("measure_map_warnings")), 0)

    def test_measure_map_uses_refined_fallback_beats(self):
        """測試 MeasureMapNode：使用 refined fallback beats 時保留 fallback 來源"""
        refine_node = DownbeatRefineNode()
        map_node = MeasureMapNode()
        blackboard = Blackboard()
        blackboard.set_val("beat_validation", {"status": "WARN", "warnings": []})
        blackboard.set_val("beats", np.array([
            [0.0, 2],
            [0.5, 3],
            [1.0, 4],
            [1.5, 2],
            [2.0, 3],
        ]))

        refine_status = refine_node.execute(blackboard)
        map_status = map_node.execute(blackboard)
        measure_map = blackboard.get_val("measure_map")

        self.assertEqual(refine_status, NodeStatus.SUCCESS)
        self.assertEqual(map_status, NodeStatus.SUCCESS)
        self.assertEqual(blackboard.get_val("measure_map_status"), "WARN")
        self.assertEqual([measure["beat_count"] for measure in measure_map], [4, 1])
        self.assertEqual(measure_map[0]["source"], "fallback_4beat")

    def test_bt_engine_full_run(self):
        """測試 BT 引擎完整行為樹節點執行流水線 (包含 VideoURLDownloadNode 進入點)"""
        bt_engine = BTWorkflowEngine()
        blackboard = bt_engine.run(self.test_audio, output_dir=self.temp_dir, enable_stem=True, target_stage="stage5")

        self.assertIsNotNone(blackboard.get_val("beats"))
        self.assertIsNotNone(blackboard.get_val("beat_validation"))
        self.assertIsNotNone(blackboard.get_val("downbeat_refinement"))
        self.assertIsNotNone(blackboard.get_val("measure_map"))
        self.assertIsNotNone(blackboard.get_val("estimated_key"))
        self.assertTrue(os.path.exists(blackboard.get_val("click_track")))
        self.assertTrue(os.path.exists(blackboard.get_val("tempo_map_midi")))
        self.assertTrue(os.path.exists(blackboard.get_val("click_guide_midi")))
        self.assertEqual(blackboard.get_val("workflow_status"), "SUCCESS")
        trace = blackboard.get_val("workflow_trace")
        self.assertIsInstance(trace, list)
        self.assertGreater(len(trace), 0)
        self.assertEqual(trace[-1]["node"], "PGMCraftWorkflowRoot")
        self.assertEqual(trace[-1]["status"], "SUCCESS")
        self.assertIn("AudioLoadNode", [entry["node"] for entry in trace])

if __name__ == '__main__':
    unittest.main()
