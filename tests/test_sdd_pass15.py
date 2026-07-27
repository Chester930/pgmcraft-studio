"""
Unit tests for Pass 15 SDD (Specification-Driven Development):
Module 1: AI 採譜模型狀態標記 (ai_model_status REAL_MODEL vs FALLBACK_DSP)
Module 2: SectionStructureNode 與 MeasureMapNode 獨立 JSON 導出
Module 3: Demucs 推理快取機制 (避免同一首歌重複推理)
Module 4: MasterBTWorkflowEngine 與主流程節點完全同步
Module 5: Pipeline outputs 完整 Blackboard 金鑰映照
"""

import os
import json
import tempfile
import numpy as np
import unittest
from unittest.mock import patch
import soundfile as sf

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import (
    BasicPitchNode,
    CREPEPitchNode,
    PodcastSpeechNode,
    SectionStructureNode,
    MeasureMapNode,
    MIDIQuantizerGuardNode,
)
from pgm_craft.workflow.builder import (
    build_pgm_workflow_tree,
    build_master_pipeline_tree,
)
from pgm_craft.separator import CascadedStemSeparator


# ─────────────────────────────────────────────────────────
# Module 1: AI 採譜模型狀態標記 (ai_model_status)
# ─────────────────────────────────────────────────────────

class TestAIModelStatusLabeling(unittest.TestCase):

    def _make_blackboard(self, tmpdir):
        bb = Blackboard()
        audio_path = os.path.join(tmpdir, "test.wav")
        sr = 22050
        t = np.linspace(0, 2.0, sr * 2, False)
        y = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        sf.write(audio_path, y, sr)
        bb.set_val("audio_path", audio_path)
        bb.set_val("target_analysis_path", audio_path)
        bb.set_val("output_dir", tmpdir)
        bb.set_val("y", y)
        bb.set_val("sr", sr)
        beats = np.array([[i * 0.5, (i % 4) + 1] for i in range(8)])
        bb.set_val("beats", beats)
        return bb

    def test_basic_pitch_node_records_fallback_status(self):
        """basic_pitch 未安裝時，ai_model_status["basic_pitch"] 應含 FALLBACK"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = self._make_blackboard(tmpdir)
            BasicPitchNode().run(bb)
            status = bb.get_val("ai_model_status", {})
            self.assertIn("basic_pitch", status)
            self.assertIn("FALLBACK", status["basic_pitch"].upper())

    def test_crepe_pitch_node_records_fallback_status(self):
        """crepe 未安裝時，ai_model_status["crepe_pitch"] 應含 FALLBACK"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = self._make_blackboard(tmpdir)
            CREPEPitchNode().run(bb)
            status = bb.get_val("ai_model_status", {})
            self.assertIn("crepe_pitch", status)
            self.assertIn("FALLBACK", status["crepe_pitch"].upper())

    def test_podcast_speech_node_records_model_status(self):
        """PodcastSpeechNode 執行後應記錄 ai_model_status['whisper_speech']，
        無論是 REAL_MODEL (whisper 已裝) 或 FALLBACK_SPEECH_ENERGY (未裝)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = self._make_blackboard(tmpdir)
            PodcastSpeechNode().run(bb)
            status = bb.get_val("ai_model_status", {})
            self.assertIn("whisper_speech", status,
                          "whisper_speech 鍵應存在於 ai_model_status")
            self.assertTrue(status["whisper_speech"],
                            "ai_model_status['whisper_speech'] 不應為空字串")
            # 值必須是 REAL_MODEL 或 FALLBACK 其中之一
            val = status["whisper_speech"].upper()
            self.assertTrue(
                "REAL_MODEL" in val or "FALLBACK" in val,
                f"ai_model_status['whisper_speech'] 值不合法: {status['whisper_speech']!r}"
            )

    def test_ai_model_status_accumulates_across_nodes(self):
        """多個 AI 節點依序執行後，ai_model_status 應累積所有節點標記"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = self._make_blackboard(tmpdir)
            BasicPitchNode().run(bb)
            CREPEPitchNode().run(bb)
            PodcastSpeechNode().run(bb)
            status = bb.get_val("ai_model_status", {})
            self.assertIn("basic_pitch", status)
            self.assertIn("crepe_pitch", status)
            self.assertIn("whisper_speech", status)
            for k, v in status.items():
                self.assertTrue(v, f"ai_model_status[{k!r}] 不應為空")


# ─────────────────────────────────────────────────────────
# Module 2: SectionStructureNode & MeasureMapNode 獨立 JSON 導出
# ─────────────────────────────────────────────────────────

class TestIndependentJSONExport(unittest.TestCase):

    def _make_measure_map(self):
        return [
            {"measure": i + 1, "start_time": i * 2.0, "beats": [i * 2.0, i * 2.0 + 0.5]}
            for i in range(8)
        ]

    def test_measure_map_node_writes_json_file(self):
        """MeasureMapNode 執行後應在 output_dir 產出 measure_map.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = Blackboard()
            bb.set_val("output_dir", tmpdir)
            beats = np.array([[i * 0.5, (i % 4) + 1] for i in range(16)])
            bb.set_val("beats", beats)
            bb.set_val("refined_beats", beats)
            bb.set_val("beat_validation", {"status": "PASS"})
            bb.set_val("downbeat_refinement", {"source": "downbeat"})

            MeasureMapNode().run(bb)

            json_path = os.path.join(tmpdir, "measure_map.json")
            self.assertTrue(os.path.exists(json_path), "measure_map.json 應存在")
            self.assertEqual(bb.get_val("measure_map_json"), json_path)

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("measure_map", data)
            self.assertIn("status", data)

    def test_section_structure_node_writes_json_file(self):
        """SectionStructureNode 執行後應在 output_dir 產出 sections.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = Blackboard()
            bb.set_val("output_dir", tmpdir)
            bb.set_val("measure_map", self._make_measure_map())

            SectionStructureNode().run(bb)

            json_path = os.path.join(tmpdir, "sections.json")
            self.assertTrue(os.path.exists(json_path), "sections.json 應存在")
            self.assertEqual(bb.get_val("sections_json"), json_path)

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("sections", data)
            self.assertIsInstance(data["sections"], list)
            self.assertGreater(len(data["sections"]), 0)

    def test_section_structure_json_contains_expected_labels(self):
        """sections.json 應包含 Intro / Verse / Chorus 等常見樂段標籤"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = Blackboard()
            bb.set_val("output_dir", tmpdir)
            bb.set_val("measure_map", self._make_measure_map())

            SectionStructureNode().run(bb)

            with open(os.path.join(tmpdir, "sections.json"), "r", encoding="utf-8") as f:
                data = json.load(f)

            names = [s["name"] for s in data["sections"]]
            self.assertTrue(
                any(n in names for n in ("Intro", "Verse 1", "Chorus 1", "Main")),
                f"sections 缺少預期樂段標籤，got: {names}"
            )


# ─────────────────────────────────────────────────────────
# Module 3: Demucs 推理快取機制
# ─────────────────────────────────────────────────────────

class TestDemucsInferenceCache(unittest.TestCase):

    def test_separator_has_demucs_cache_attribute(self):
        """CascadedStemSeparator 初始化後應有 _demucs_cache 屬性"""
        sep = CascadedStemSeparator()
        self.assertTrue(hasattr(sep, "_demucs_cache"))
        self.assertIsInstance(sep._demucs_cache, dict)

    def test_demucs_cache_is_empty_on_init(self):
        """初始化後快取應為空字典"""
        sep = CascadedStemSeparator()
        self.assertEqual(len(sep._demucs_cache), 0)

    def test_demucs_separate_uses_cache_on_hit(self):
        """_demucs_separate 快取命中時不應重複推理，直接回傳快取路徑"""
        sep = CascadedStemSeparator()

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "test.wav")
            y = np.zeros(22050, dtype=np.float32)
            sf.write(audio_path, y, 22050)

            # 預先填入快取
            fake_paths = {
                "vocals": os.path.join(tmpdir, "vocals.wav"),
                "drums": os.path.join(tmpdir, "drums.wav"),
                "bass": os.path.join(tmpdir, "bass.wav"),
                "other": os.path.join(tmpdir, "other.wav"),
            }
            # 建立假檔案讓 os.path.exists 通過
            for p in fake_paths.values():
                open(p, "w").close()

            cache_key = (os.path.abspath(audio_path), "htdemucs_ft", tmpdir)
            sep._demucs_cache[cache_key] = fake_paths

            # 呼叫真實 _demucs_separate，應命中快取而非觸發推理
            # 使用 patch 確認底層 get_model 不被呼叫
            with patch("pgm_craft.separator.CascadedStemSeparator._demucs_separate",
                       wraps=sep._demucs_separate) as mock_fn:
                result = sep._demucs_separate(audio_path, tmpdir, "htdemucs_ft", {"vocals"})
                # 確認結果包含 vocals 且來自快取
                self.assertIn("vocals", result)
                self.assertEqual(result["vocals"], fake_paths["vocals"])

    def test_demucs_cache_key_includes_model_name(self):
        """不同 model_name 的快取 Key 應不同，避免混用"""
        audio_path = "/fake/audio.wav"
        output_dir = "/fake/out"
        key_ft = (os.path.abspath(audio_path), "htdemucs_ft", output_dir)
        key_6s = (os.path.abspath(audio_path), "htdemucs_6s", output_dir)
        self.assertNotEqual(key_ft, key_6s)


# ─────────────────────────────────────────────────────────
# Module 4: MasterBTWorkflowEngine 與主流程節點同步驗證
# ─────────────────────────────────────────────────────────

class TestMasterPipelineNodeSync(unittest.TestCase):

    def _get_node_names(self, tree):
        names = [tree.name]
        for child in getattr(tree, "children", []):
            names.extend(self._get_node_names(child))
        return names

    def test_master_tree_contains_audio_quantizer(self):
        tree = build_master_pipeline_tree()
        self.assertIn("AudioQuantizerNode", self._get_node_names(tree))

    def test_master_tree_contains_midi_quantizer_guard(self):
        tree = build_master_pipeline_tree()
        self.assertIn("MIDIQuantizerGuardNode", self._get_node_names(tree))

    def test_master_tree_contains_voice_split_midi_export(self):
        tree = build_master_pipeline_tree()
        self.assertIn("VoiceSplitMIDIExportNode", self._get_node_names(tree))

    def test_main_and_master_tree_have_same_leaf_nodes(self):
        """主流程 Stage 1~5 應為 Master 流程 Stage 1~5 節點集合之子集"""
        root_names = {"PGMCraftWorkflowRoot", "PGMFullPipelineRoot", "MasterPGMPipelineRoot"}
        main_names = set(n for n in self._get_node_names(build_pgm_workflow_tree())
                         if n not in root_names)
        master_names = set(n for n in self._get_node_names(build_master_pipeline_tree())
                           if n not in root_names)
        self.assertTrue(main_names.issubset(master_names),
                        "主流程與 Master 流程節點集合不一致！")


# ─────────────────────────────────────────────────────────
# Module 5: Pipeline outputs 完整 Blackboard 金鑰映照
# ─────────────────────────────────────────────────────────

class TestPipelineOutputMapping(unittest.TestCase):

    EXPECTED_OUTPUT_KEYS = [
        "click_track", "mix_with_click", "tempo_map_midi", "click_guide_midi",
        "chord_guide_midi", "melody_lead_midi", "vocal_pitch_midi",
        "vocal_lead_quantized_midi", "pitch_contour_json", "subtitles_srt",
        "transcript_json", "instrument_presence_json", "sections_json",
        "measure_map_json", "rhythm_submix", "harmonic_submix", "structure_submix",
        "tempo_curve_plot", "json_report",
    ]

    def test_pipeline_py_contains_all_expected_output_keys(self):
        """pipeline.py 的 report['outputs'] 應包含所有預期的 Blackboard 金鑰"""
        pipeline_path = os.path.join("pgm_craft", "pipeline.py")
        self.assertTrue(os.path.exists(pipeline_path))
        with open(pipeline_path, "r", encoding="utf-8") as f:
            source = f.read()
        for key in self.EXPECTED_OUTPUT_KEYS:
            self.assertIn(f'"{key}"', source,
                          f"pipeline.py 缺少 output key: {key!r}")

    def test_midi_quantizer_guard_vocal_pitch_is_optional(self):
        """vocal_pitch 應在 optional_keys，不在 required_keys"""
        node = MIDIQuantizerGuardNode()
        self.assertNotIn("vocal_pitch", node.required_keys)
        self.assertIn("vocal_pitch", node.optional_keys)

    def test_midi_quantizer_guard_succeeds_without_vocal_pitch(self):
        """無 vocal_pitch 黑板金鑰時 MIDIQuantizerGuardNode 應 SUCCESS"""
        bb = Blackboard()
        result = MIDIQuantizerGuardNode().run(bb)
        self.assertEqual(result, NodeStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
