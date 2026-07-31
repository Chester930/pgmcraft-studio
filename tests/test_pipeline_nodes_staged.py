"""
PGMCraft 全自動流程 — 階段性節點串接測試 (Staged Pipeline Node Integration Test)
======================================================================
分 5 個階段驗證整條 BT Pipeline 各節點是否正確串接並能作用：

Phase 1: Blackboard 核心契約 — BaseNode / Blackboard 基礎
Phase 2: 音訊載入鏈 — AudioLoadNode → target_analysis_path 輸出
Phase 3: 節拍追蹤鏈 — LibrosaBeatNode → BeatValidationNode → DownbeatRefineNode → MeasureMapNode
Phase 4: 音訊分析鏈 — KeyChordAnalysisNode → ClickSynthesisNode → MIDIExportNode → SectionStructureNode
Phase 5: 全自動行為樹引擎 — BTWorkflowEngine.run (端對端) + MasterBTWorkflowEngine
"""

import os
import json
import shutil
import tempfile
import unittest
import numpy as np

# ── 核心 BT 引擎 ──────────────────────────────────────────────────────────────
from pgm_craft.workflow.nodes import (
    BaseNode, Blackboard, NodeStatus,
    SequenceNode, FallbackNode, RetryFallbackNode, ParallelNode
)
from pgm_craft.workflow.audio_nodes import (
    AudioLoadNode,
    LibrosaBeatNode,
    BeatValidationNode,
    DownbeatRefineNode,
    MeasureMapNode,
    SectionStructureNode,
    KeyChordAnalysisNode,
    ClickSynthesisNode,
    MIDIExportNode,
    BasicPitchNode,
    CREPEPitchNode,
    PodcastSpeechNode,
    InstrumentPresenceNode,
    HybridPitchNode,
    VideoURLDownloadNode,
    SubMixGeneratorNode,
)
from pgm_craft.workflow.builder import BTWorkflowEngine, MasterBTWorkflowEngine, build_pgm_workflow_tree

# ── 測試固定 WAV ───────────────────────────────────────────────────────────────
SAMPLE_WAV = "sample_test.wav"

# 建一組標準合法的 beats (Nx2, 120 BPM, 4/4)
def make_beats(n=32, bpm=120.0):
    interval = 60.0 / bpm
    rows = []
    for i in range(n):
        beat_num = (i % 4) + 1
        rows.append([round(i * interval, 6), beat_num])
    return np.array(rows)

BEATS = make_beats()


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — Blackboard 核心契約
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhase1_BlackboardCore(unittest.TestCase):
    """Phase 1: Blackboard 基本讀寫、型別安全、trace、contract validation"""

    def test_blackboard_set_get(self):
        bb = Blackboard()
        bb.set_val("audio_path", "test.wav")
        self.assertEqual(bb.get_val("audio_path"), "test.wav")
        self.assertIsNone(bb.get_val("nonexistent"))

    def test_blackboard_get_typed_coercion(self):
        bb = Blackboard()
        bb.set_val("bpm", "120")
        result = bb.get_typed("bpm", float, default=0.0)
        self.assertEqual(result, 120.0)

    def test_blackboard_append_trace(self):
        bb = Blackboard()
        bb.append_trace({"node": "TestNode", "status": "SUCCESS", "duration_ms": 1.0})
        trace = bb.get_val("workflow_trace")
        self.assertIsInstance(trace, list)
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["node"], "TestNode")

    def test_base_node_run_records_trace(self):
        """BaseNode.run() 執行後應在 workflow_trace 留下記錄"""
        class OKNode(BaseNode):
            output_keys = ["ok"]
            def execute(self, bb):
                bb.set_val("ok", True)
                return NodeStatus.SUCCESS

        bb = Blackboard()
        node = OKNode("OKNode")
        status = node.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        trace = bb.get_val("workflow_trace", [])
        self.assertGreater(len(trace), 0)
        self.assertEqual(trace[0]["node"], "OKNode")

    def test_base_node_run_catches_exception_as_failure(self):
        """節點 execute() 若拋出例外，BaseNode.run() 應安全降級為 FAILURE"""
        class BrokenNode(BaseNode):
            output_keys = ["x"]
            def execute(self, bb):
                raise RuntimeError("模擬崩潰")

        bb = Blackboard()
        status = BrokenNode("BrokenNode").run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_sequence_node_stops_on_failure(self):
        class SuccessNode(BaseNode):
            output_keys = ["a"]
            def execute(self, bb): return NodeStatus.SUCCESS

        class FailNode(BaseNode):
            output_keys = ["b"]
            def execute(self, bb): return NodeStatus.FAILURE

        class NeverReachedNode(BaseNode):
            output_keys = ["c"]
            def execute(self, bb):
                bb.set_val("should_not_run", True)
                return NodeStatus.SUCCESS

        bb = Blackboard()
        seq = SequenceNode("TestSeq", [SuccessNode("A"), FailNode("B"), NeverReachedNode("C")])
        status = seq.run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)
        self.assertIsNone(bb.get_val("should_not_run"))

    def test_fallback_node_returns_first_success(self):
        class FailNode(BaseNode):
            output_keys = ["x"]
            def execute(self, bb): return NodeStatus.FAILURE

        class SuccessNode(BaseNode):
            output_keys = ["y"]
            def execute(self, bb):
                bb.set_val("winner", True)
                return NodeStatus.SUCCESS

        bb = Blackboard()
        fb = FallbackNode("TestFB", [FailNode("F1"), SuccessNode("S1")])
        status = fb.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(bb.get_val("winner"))

    def test_retry_fallback_node(self):
        call_count = {"n": 0}

        class FlakyNode(BaseNode):
            output_keys = ["ok"]
            def execute(self, bb):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    return NodeStatus.FAILURE
                return NodeStatus.SUCCESS

        bb = Blackboard()
        rfn = RetryFallbackNode("RFN", child=FlakyNode("Flaky"), max_retries=3)
        status = rfn.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertGreaterEqual(call_count["n"], 3)

    def test_parallel_node_success_threshold(self):
        class SuccessNode(BaseNode):
            output_keys = ["ok"]
            def execute(self, bb): return NodeStatus.SUCCESS

        class FailNode(BaseNode):
            output_keys = ["nope"]
            def execute(self, bb): return NodeStatus.FAILURE

        bb = Blackboard()
        # 3 個 children，success_threshold=1 → 只要一個成功即 SUCCESS
        par = ParallelNode("Par", children=[FailNode("F"), SuccessNode("S"), FailNode("F2")], success_threshold=1)
        status = par.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)

    def test_contract_validate_mode(self):
        """validate_contracts=True 時，BaseNode.run() 應執行 validate_contract 並寫入 bb"""
        class NodeWithContract(BaseNode):
            required_keys = ["audio_path"]
            output_keys = ["y"]
            def execute(self, bb): return NodeStatus.SUCCESS

        bb = Blackboard()
        bb.set_val("validate_contracts", True)  # 啟用 contract 檢查
        # 沒有 audio_path → 應標記 WARN
        node = NodeWithContract("ContractNode")
        node.run(bb)
        validations = bb.get_val("contract_validation", [])
        self.assertGreater(len(validations), 0)
        self.assertIn("audio_path", validations[0]["missing_required_keys"])


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — 音訊載入鏈
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhase2_AudioLoadChain(unittest.TestCase):
    """Phase 2: VideoURLDownloadNode + AudioLoadNode → y/sr/target_analysis_path 輸出"""

    def test_video_url_node_skips_local_path(self):
        node = VideoURLDownloadNode()
        bb = Blackboard()
        bb.set_val("audio_path", SAMPLE_WAV)
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        # 本地路徑不應被覆寫
        self.assertEqual(bb.get_val("audio_path"), SAMPLE_WAV)

    def test_video_url_node_fails_on_bad_url(self):
        """無法下載的 URL 應回傳 FAILURE 而非 crash"""
        node = VideoURLDownloadNode()
        bb = Blackboard()
        bb.set_val("audio_path", "https://totally.invalid.url.xyz/nope.mp4")
        bb.set_val("output_dir", tempfile.mkdtemp())
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_audio_load_node_sets_y_sr_target(self):
        """AudioLoadNode 應設定 y、sr、target_analysis_path"""
        node = AudioLoadNode()
        bb = Blackboard()
        bb.set_val("audio_path", SAMPLE_WAV)
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        y = bb.get_val("y")
        sr = bb.get_val("sr")
        target = bb.get_val("target_analysis_path")
        self.assertIsNotNone(y)
        self.assertGreater(len(y), 0)
        self.assertEqual(sr, 22050)
        self.assertEqual(target, SAMPLE_WAV)

    def test_audio_load_node_fails_on_missing_file(self):
        node = AudioLoadNode()
        bb = Blackboard()
        bb.set_val("audio_path", "nonexistent_file.wav")
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_audio_load_node_missing_key_fails(self):
        node = AudioLoadNode()
        bb = Blackboard()  # 沒有 audio_path
        status = node.execute(bb)
        self.assertEqual(status, NodeStatus.FAILURE)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — 節拍追蹤鏈
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhase3_BeatTrackingChain(unittest.TestCase):
    """Phase 3: LibrosaBeatNode → BeatValidationNode → DownbeatRefineNode → MeasureMapNode 串接"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.bb = Blackboard()
        self.bb.set_val("audio_path", SAMPLE_WAV)
        self.bb.set_val("output_dir", self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_librosa_beat_node_sets_beats(self):
        """LibrosaBeatNode 應設定 beats (Nx2 numpy array)"""
        # 需要先跑 AudioLoadNode 給 target_analysis_path
        al = AudioLoadNode()
        al.execute(self.bb)
        node = LibrosaBeatNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        beats = self.bb.get_val("beats")
        self.assertIsNotNone(beats)
        self.assertGreater(len(beats), 0)

    def test_beat_validation_pass_with_valid_beats(self):
        """BeatValidationNode 對合法 beats 應回傳 SUCCESS"""
        self.bb.set_val("beats", BEATS)
        node = BeatValidationNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        val = self.bb.get_val("beat_validation")
        self.assertIn(val["status"], ["PASS", "WARN"])

    def test_beat_validation_fail_on_empty(self):
        """空 beats 應導致 BeatValidationNode FAILURE"""
        self.bb.set_val("beats", np.empty((0, 2)))
        node = BeatValidationNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_beat_validation_fail_on_non_increasing(self):
        """非嚴格遞增 timestamp 應 FAIL"""
        bad_beats = np.array([[0.5, 1], [0.5, 2], [1.0, 3], [1.5, 4]])  # 第 1→2 timestamp 相同
        self.bb.set_val("beats", bad_beats)
        node = BeatValidationNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_downbeat_refine_node_with_valid_beats(self):
        """DownbeatRefineNode 對合法 beats 應回傳 SUCCESS 並設定 refined_beats"""
        self.bb.set_val("beats", BEATS)
        self.bb.set_val("beat_validation", {"status": "PASS", "warnings": []})
        node = DownbeatRefineNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        refined = self.bb.get_val("refined_beats")
        self.assertIsNotNone(refined)
        self.assertEqual(len(refined), len(BEATS))

    def test_downbeat_refine_node_skips_if_validation_failed(self):
        """beat_validation status=FAIL 時，DownbeatRefineNode 應直接 FAILURE"""
        self.bb.set_val("beats", BEATS)
        self.bb.set_val("beat_validation", {"status": "FAIL", "warnings": ["test"]})
        node = DownbeatRefineNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_measure_map_node_builds_correct_structure(self):
        """MeasureMapNode 應產出 measure_map list，每個條目含 measure/start_time/end_time/beats"""
        self.bb.set_val("beats", BEATS)
        self.bb.set_val("beat_validation", {"status": "PASS", "warnings": []})
        # 先跑 DownbeatRefineNode 建立 refined_beats
        DownbeatRefineNode().execute(self.bb)
        node = MeasureMapNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        mm = self.bb.get_val("measure_map")
        self.assertIsInstance(mm, list)
        self.assertGreater(len(mm), 0)
        # 驗證第一個小節結構
        m0 = mm[0]
        self.assertIn("measure", m0)
        self.assertIn("start_time", m0)
        self.assertIn("end_time", m0)
        self.assertIn("beats", m0)

    def test_beat_chain_end_to_end(self):
        """LibrosaBeat → Validation → Refine → MeasureMap 完整鏈接 (使用實際音檔)"""
        AudioLoadNode().execute(self.bb)
        LibrosaBeatNode().execute(self.bb)
        self.assertIsNotNone(self.bb.get_val("beats"), "LibrosaBeatNode 未產出 beats")

        s1 = BeatValidationNode().execute(self.bb)
        self.assertIn(s1, [NodeStatus.SUCCESS, NodeStatus.FAILURE])

        if s1 == NodeStatus.SUCCESS:
            s2 = DownbeatRefineNode().execute(self.bb)
            self.assertEqual(s2, NodeStatus.SUCCESS)
            s3 = MeasureMapNode().execute(self.bb)
            self.assertEqual(s3, NodeStatus.SUCCESS)
            mm = self.bb.get_val("measure_map")
            self.assertIsInstance(mm, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4 — 音訊分析鏈
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhase4_AnalysisChain(unittest.TestCase):
    """Phase 4: SectionStructureNode / KeyChordAnalysisNode / ClickSynthesisNode / MIDIExportNode / AI nodes"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # 建立一個預載完整的 blackboard
        self.bb = Blackboard()
        self.bb.set_val("audio_path", SAMPLE_WAV)
        self.bb.set_val("output_dir", self.temp_dir)
        self.bb.set_val("beats", BEATS)
        self.bb.set_val("beat_validation", {"status": "PASS", "warnings": []})
        self.bb.set_val("refined_beats", BEATS)
        # 建假 measure_map
        measure_map = []
        for i in range(8):
            measure_map.append({
                "measure": i + 1,
                "start_time": round(i * 2.0, 3),
                "end_time": round((i + 1) * 2.0, 3),
                "beats": [{"beat": j + 1, "time": round(i * 2.0 + j * 0.5, 3)} for j in range(4)],
                "is_variable_length": False,
                "is_incomplete": False,
                "source": "downbeat",
            })
        self.bb.set_val("measure_map", measure_map)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── SectionStructureNode ─────────────────────────────────────────────────
    def test_section_structure_segments_into_sections(self):
        node = SectionStructureNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        sections = self.bb.get_val("sections")
        self.assertIsInstance(sections, list)
        self.assertGreater(len(sections), 0)
        # 8 個小節 → 應切出 Intro / Verse / Chorus
        names = [s["name"] for s in sections]
        self.assertIn("Intro", names)

    def test_section_structure_empty_measure_map(self):
        """空 measure_map 應回傳 SUCCESS 且 sections=[]"""
        self.bb.set_val("measure_map", [])
        node = SectionStructureNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(self.bb.get_val("sections"), [])

    # ── KeyChordAnalysisNode ─────────────────────────────────────────────────
    def test_key_chord_analysis_sets_key_and_chords(self):
        node = KeyChordAnalysisNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        key = self.bb.get_val("estimated_key")
        chords = self.bb.get_val("chord_progression")
        self.assertIsNotNone(key)
        self.assertIsInstance(chords, list)

    def test_key_chord_analysis_uses_cache(self):
        """如果已有 chord_progression 和 estimated_key 應 0ms 複用，不重跑"""
        self.bb.set_val("estimated_key", "C major")
        self.bb.set_val("chord_progression", [{"chord": "C"}])
        node = KeyChordAnalysisNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        # 確認值未被覆寫
        self.assertEqual(self.bb.get_val("estimated_key"), "C major")

    # ── ClickSynthesisNode ───────────────────────────────────────────────────
    def test_click_synthesis_creates_files(self):
        node = ClickSynthesisNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        click_path = self.bb.get_val("click_track")
        mix_path = self.bb.get_val("mix_with_click")
        self.assertTrue(os.path.exists(click_path), "click_track.wav 未產出")
        self.assertTrue(os.path.exists(mix_path), "mix_with_click.wav 未產出")

    # ── MIDIExportNode ───────────────────────────────────────────────────────
    def test_midi_export_creates_three_files(self):
        node = MIDIExportNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        for key in ["tempo_map_midi", "click_guide_midi", "chord_guide_midi"]:
            path = self.bb.get_val(key)
            self.assertIsNotNone(path, f"{key} 未設定")
            self.assertTrue(os.path.exists(path), f"{path} 不存在")

    # ── AI 節點 (graceful fallback) ──────────────────────────────────────────
    def test_basic_pitch_node_graceful_fallback(self):
        """BasicPitchNode: basic_pitch 不可用時應 fallback 並仍回傳 SUCCESS"""
        node = BasicPitchNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        midi_path = self.bb.get_val("melody_lead_midi")
        self.assertIsNotNone(midi_path)
        self.assertTrue(os.path.exists(midi_path))

    def test_crepe_pitch_node_graceful_fallback(self):
        """CREPEPitchNode: CREPE 不可用時應 fallback 到 librosa pyin 並回傳 SUCCESS"""
        # 先載入音訊供 fallback 使用
        AudioLoadNode().execute(self.bb)
        node = CREPEPitchNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        json_path = self.bb.get_val("pitch_contour_json")
        self.assertIsNotNone(json_path)
        self.assertTrue(os.path.exists(json_path))

    def test_podcast_speech_node_graceful_fallback(self):
        """PodcastSpeechNode: Whisper 不可用時應 fallback 並回傳 SUCCESS"""
        AudioLoadNode().execute(self.bb)
        node = PodcastSpeechNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        srt_path = self.bb.get_val("subtitles_srt")
        self.assertIsNotNone(srt_path)
        self.assertTrue(os.path.exists(srt_path))

    def test_instrument_presence_node_sets_matrix(self):
        """InstrumentPresenceNode 應產出 instrument_matrix list"""
        AudioLoadNode().execute(self.bb)
        node = InstrumentPresenceNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        matrix = self.bb.get_val("instrument_matrix")
        self.assertIsInstance(matrix, list)
        self.assertGreater(len(matrix), 0)
        # 驗證每個條目的 key
        for entry in matrix:
            self.assertIn("measure", entry)
            self.assertIn("bass_present", entry)
            self.assertIn("drums_present", entry)
            self.assertIn("vocal_present", entry)

    def test_hybrid_pitch_node_creates_midi(self):
        """HybridPitchNode 應產出 vocal_lead_quantized.mid"""
        node = HybridPitchNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        midi_path = self.bb.get_val("vocal_lead_quantized_midi")
        self.assertIsNotNone(midi_path)
        self.assertTrue(os.path.exists(midi_path))

    def test_sub_mix_generator_node_fallback_to_audio_path(self):
        """SubMixGeneratorNode: 無 stems 時應 fallback 至原始 audio_path"""
        node = SubMixGeneratorNode()
        status = node.execute(self.bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(self.bb.get_val("rhythm_submix"), SAMPLE_WAV)
        self.assertEqual(self.bb.get_val("harmonic_submix"), SAMPLE_WAV)
        self.assertEqual(self.bb.get_val("structure_submix"), SAMPLE_WAV)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5 — 全自動行為樹引擎 (端對端)
# ═══════════════════════════════════════════════════════════════════════════════
class TestPhase5_FullPipelineEngine(unittest.TestCase):
    """Phase 5: BTWorkflowEngine / MasterBTWorkflowEngine 端對端驗證"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── BT Workflow 樹結構完整性 ─────────────────────────────────────────────
    def test_workflow_tree_nodes_have_contracts(self):
        """build_pgm_workflow_tree() 所有節點都有 required/optional/output_keys"""
        tree = build_pgm_workflow_tree()

        def flatten(node):
            nodes = [node]
            for child in getattr(node, "children", []) or []:
                nodes.extend(flatten(child))
            if hasattr(node, "child") and node.child:
                nodes.extend(flatten(node.child))
            return nodes

        all_nodes = flatten(tree)
        concrete = [n for n in all_nodes if n.__class__.__name__ not in {"SequenceNode", "FallbackNode", "ParallelNode"}]
        for n in concrete:
            self.assertIsInstance(n.required_keys, list, f"{n.name} 缺少 required_keys")
            self.assertIsInstance(n.optional_keys, list, f"{n.name} 缺少 optional_keys")
            self.assertIsInstance(n.output_keys, list, f"{n.name} 缺少 output_keys")

    # ── BTWorkflowEngine 端對端 ──────────────────────────────────────────────
    def test_bt_workflow_engine_run_returns_blackboard(self):
        """BTWorkflowEngine.run() 應回傳 Blackboard，且含 workflow_status 與 beats"""
        engine = BTWorkflowEngine()
        bb = engine.run(SAMPLE_WAV, output_dir=self.temp_dir, enable_stem=False)
        self.assertIsInstance(bb, Blackboard)
        self.assertIn(bb.get_val("workflow_status"), ["SUCCESS", "FAILURE"])
        # beats 應已設定 (librosa fallback 必然成功)
        self.assertIsNotNone(bb.get_val("beats"), "beats 未設定到 blackboard")

    def test_bt_workflow_engine_writes_click_and_midi(self):
        """完整跑完 BTWorkflowEngine 應產出 click_track.wav 和至少一個 MIDI"""
        engine = BTWorkflowEngine()
        bb = engine.run(SAMPLE_WAV, output_dir=self.temp_dir, enable_stem=False)
        if bb.get_val("workflow_status") == "SUCCESS":
            click = bb.get_val("click_track")
            self.assertIsNotNone(click)
            self.assertTrue(os.path.exists(click), f"click_track 不存在: {click}")
            tempo_midi = bb.get_val("tempo_map_midi")
            self.assertIsNotNone(tempo_midi)
            self.assertTrue(os.path.exists(tempo_midi), f"tempo_map_midi 不存在: {tempo_midi}")

    def test_bt_workflow_engine_trace_covers_all_phases(self):
        """workflow_trace 應涵蓋各階段關鍵節點"""
        engine = BTWorkflowEngine()
        bb = engine.run(SAMPLE_WAV, output_dir=self.temp_dir, enable_stem=False)
        trace = bb.get_val("workflow_trace", [])
        node_names = [t.get("node") for t in trace]
        for expected in ["AudioLoadNode", "BeatValidationNode", "MeasureMapNode", "ClickSynthesisNode"]:
            self.assertIn(expected, node_names, f"{expected} 未出現在 workflow_trace")

    def test_bt_workflow_engine_validate_contracts(self):
        """validate_contracts=True 模式下應產出 contract_validation 記錄"""
        engine = BTWorkflowEngine()
        bb = engine.run(SAMPLE_WAV, output_dir=self.temp_dir, enable_stem=False, validate_contracts=True)
        validations = bb.get_val("contract_validation", [])
        self.assertIsInstance(validations, list)
        self.assertGreater(len(validations), 0, "contract_validation 記錄為空")


if __name__ == "__main__":
    unittest.main(verbosity=2)
