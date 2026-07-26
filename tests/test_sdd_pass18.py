"""
SDD Pass 18 — Stage 2: Stem Separation BT
===========================================
Module 1: EnsureStemsFolderNode — 專案 stems/ 目錄建立
Module 2: InstrumentPresenceDetectNode — 概率預設與重用
Module 3: HasInstrumentConditionNode — 概率門檻過濾 Guard
Module 4: SeparateVocalsNode — 人聲與伴奏分離 (Mocked separator)
Module 5: SeparateDrumsNode — 鼓組與無鼓分離
Module 6: SeparateBassNode — 貝斯與 Other 分離
Module 7: SeparateGuitarNode — 吉他分離
Module 8: RegisterStemsToBlackboardNode — 磁碟掃描與 Blackboard 註冊
Module 9: build_stem_separation_tree() — 完整 BT 樹 (含跳過未達門檻樂器)
Module 10: StemSeparationBTEngine — 引擎 wrapper 契約
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import soundfile as sf

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.stem_separation_bt import (
    EnsureStemsFolderNode,
    DetectVocalPresenceNode,
    DetectHarmonyPresenceNode,
    DetectDrumsPresenceNode,
    DetectBassPresenceNode,
    DetectGuitarPresenceNode,
    SeparateVocalsNode,
    SeparateLeadAndBackingNode,
    SeparateDrumsNode,
    SeparateBassNode,
    SeparateGuitarNode,
    RegisterStemsToBlackboardNode,
    build_stem_separation_tree,
    StemSeparationBTEngine,
)


# ---------------------------------------------------------------------------
# Mock Separator for Fast Testing
# ---------------------------------------------------------------------------

class MockStemSeparator:
    """Mock CascadedStemSeparator 防止單元測試觸發幾秒鐘的真 AI 模型或 DSP 運算"""

    def separate_vocals(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        v = os.path.join(output_dir, "vocals.wav")
        i = os.path.join(output_dir, "instrumental.wav")
        shutil.copyfile(audio_path, v)
        shutil.copyfile(audio_path, i)
        return v, i

    def separate_drums(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        d = os.path.join(output_dir, "drums.wav")
        nd = os.path.join(output_dir, "no_drums.wav")
        shutil.copyfile(audio_path, d)
        shutil.copyfile(audio_path, nd)
        return d, nd

    def separate_bass(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        b = os.path.join(output_dir, "bass.wav")
        o = os.path.join(output_dir, "other.wav")
        shutil.copyfile(audio_path, b)
        shutil.copyfile(audio_path, o)
        return b, o

    def separate_guitar(self, audio_path, output_dir, is_already_instrumental=False):
        os.makedirs(output_dir, exist_ok=True)
        g = os.path.join(output_dir, "guitar.wav")
        ng = os.path.join(output_dir, "no_guitar.wav")
        shutil.copyfile(audio_path, g)
        shutil.copyfile(audio_path, ng)
        return g, ng

    def separate_lead_and_backing(self, audio_path, output_dir, is_already_vocal=False):
        os.makedirs(output_dir, exist_ok=True)
        l = os.path.join(output_dir, "lead_vocal.wav")
        b = os.path.join(output_dir, "backing_vocals.wav")
        shutil.copyfile(audio_path, l)
        shutil.copyfile(audio_path, b)
        return l, b


def _make_wav(path: str, sr: int = 44100, duration: float = 1.0) -> str:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    sf.write(path, y, sr)
    return path


# ---------------------------------------------------------------------------
# Module 1 — EnsureStemsFolderNode
# ---------------------------------------------------------------------------

class TestEnsureStemsFolderNode(unittest.TestCase):

    def test_creates_stems_dir_in_project_dir(self):
        with tempfile.TemporaryDirectory() as root:
            project_dir = os.path.join(root, "MyProject")
            os.makedirs(project_dir)
            bb = Blackboard()
            bb.set_val("project_dir", project_dir)
            status = EnsureStemsFolderNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            expected_stems = os.path.join(project_dir, "stems")
            self.assertTrue(os.path.isdir(expected_stems))
            self.assertEqual(bb.get_val("stems_dir"), expected_stems)

    def test_fallback_to_audio_path_directory(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            status = EnsureStemsFolderNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            expected_stems = os.path.join(root, "stems")
            self.assertTrue(os.path.isdir(expected_stems))


# ---------------------------------------------------------------------------
# Module 2 & 3 — Presence Detect & Condition Guard
# ---------------------------------------------------------------------------

class TestPresenceAndConditionNodes(unittest.TestCase):

    def test_detect_vocal_presence_pass(self):
        bb = Blackboard()
        bb.set_val("instrument_presence_probabilities", {"vocals": 0.8})
        from pgm_craft.workflow.stem_separation_bt import DetectVocalPresenceNode
        node = DetectVocalPresenceNode(threshold=0.25)
        status = node.run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(bb.get_val("has_vocals_flag"))

    def test_detect_vocal_presence_skip(self):
        bb = Blackboard()
        bb.set_val("instrument_presence_probabilities", {"vocals": 0.1})
        from pgm_craft.workflow.stem_separation_bt import DetectVocalPresenceNode
        node = DetectVocalPresenceNode(threshold=0.25)
        status = node.run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)
        self.assertFalse(bb.get_val("has_vocals_flag"))


# ---------------------------------------------------------------------------
# Module 4-7 — Separation Actions
# ---------------------------------------------------------------------------

class TestSeparationActions(unittest.TestCase):

    def setUp(self):
        self.mock_sep = MockStemSeparator()

    def test_separate_vocals(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            stems_dir = os.path.join(root, "stems")
            os.makedirs(stems_dir)

            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            bb.set_val("stems_dir", stems_dir)

            node = SeparateVocalsNode(self.mock_sep)
            status = node.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(os.path.isfile(bb.get_val("vocals_path")))
            self.assertTrue(os.path.isfile(bb.get_val("instrumental_path")))

    def test_separate_drums(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            stems_dir = os.path.join(root, "stems")
            os.makedirs(stems_dir)

            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            bb.set_val("stems_dir", stems_dir)

            node = SeparateDrumsNode(self.mock_sep)
            status = node.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(os.path.isfile(bb.get_val("drums_path")))

    def test_separate_bass(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            stems_dir = os.path.join(root, "stems")
            os.makedirs(stems_dir)

            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            bb.set_val("stems_dir", stems_dir)

            node = SeparateBassNode(self.mock_sep)
            status = node.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(os.path.isfile(bb.get_val("bass_path")))

    def test_separate_guitar(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            stems_dir = os.path.join(root, "stems")
            os.makedirs(stems_dir)

            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            bb.set_val("stems_dir", stems_dir)

            from pgm_craft.workflow.stem_separation_bt import PeelCoreTrioNode
            node = PeelCoreTrioNode(self.mock_sep)
            status = node.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(bool(bb.get_val("trio_stems")))

    def test_separate_lead_and_backing(self):
        with tempfile.TemporaryDirectory() as root:
            vocal_path = _make_wav(os.path.join(root, "vocals.wav"))
            stems_dir = os.path.join(root, "stems")
            os.makedirs(stems_dir)

            bb = Blackboard()
            bb.set_val("vocals_path", vocal_path)
            bb.set_val("stems_dir", stems_dir)

            from pgm_craft.workflow.stem_separation_bt import SeparateLeadAndBackingNode
            node = SeparateLeadAndBackingNode(self.mock_sep)
            status = node.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(os.path.isfile(bb.get_val("lead_vocal_path")))
            self.assertTrue(os.path.isfile(bb.get_val("backing_vocals_path")))


# ---------------------------------------------------------------------------
# Module 8-10 — Tree & Engine E2E
# ---------------------------------------------------------------------------

class TestStemSeparationTreeAndEngine(unittest.TestCase):

    def setUp(self):
        self.mock_sep = MockStemSeparator()

    def test_full_tree_execution(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            project_dir = os.path.join(root, "TestProj")

            tree = build_stem_separation_tree(self.mock_sep)
            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            bb.set_val("project_dir", project_dir)

            status = tree.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

            stems = bb.get_val("stems", {})
            self.assertIn("vocals", stems)
            self.assertIn("drums", stems)
            self.assertIn("bass", stems)

    def test_skip_low_probability_instrument(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            tree = build_stem_separation_tree(self.mock_sep)
            bb = Blackboard()
            bb.set_val("audio_path", audio_path)
            # 人聲機率開 0.0 (該跳過)，其餘 1.0
            bb.set_val("instrument_presence_probabilities", {
                "vocals": 0.0,
                "drums": 1.0,
                "bass": 1.0,
                "guitar": 1.0,
            })

            status = tree.run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

            stems = bb.get_val("stems", {})
            self.assertIn("drums", stems)

    def test_engine_skips_when_enable_stem_false(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            engine = StemSeparationBTEngine(self.mock_sep)
            bb = engine.run(audio_path=audio_path, enable_stem=False)
            self.assertEqual(bb.get_val("stem_separation_status"), "SKIPPED")
            self.assertEqual(bb.get_val("stems", {}), {})

    def test_engine_success_on_valid_input(self):
        with tempfile.TemporaryDirectory() as root:
            audio_path = _make_wav(os.path.join(root, "audio.wav"))
            engine = StemSeparationBTEngine(self.mock_sep)
            bb = engine.run(audio_path=audio_path, project_dir=os.path.join(root, "Proj"))
            self.assertEqual(bb.get_val("stem_separation_status"), "SUCCESS")
            self.assertTrue(os.path.exists(bb.get_val("stems_dir")))


if __name__ == "__main__":
    unittest.main()
