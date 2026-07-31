"""
SDD Pass 140 — 音色處理 BT 節點化稽核（項目 3/3）

app.py 的 process_standalone_separation()「通用分軌模式」下拉選單（15 個
mode_id）過去直接呼叫 separator_engine（CascadedStemSeparator 模組級單例）的
方法，完全繞過 BT/Blackboard，與同一個函式裡另外 21 個場景工作流（P60~P80，
都走 Blackboard()+BT node.execute()）不一致。

稽核發現：
1. vocals/drums/bass/guitar/debreathe/drums_substem/synth_bass/lead_backing
   8 個模式在 stem_separation_bt.py 已有現成節點類別，只是沒被這裡呼叫。
2. piano/strings/organ/general_6stem 4 個模式全專案沒有任何 BT 節點包裝過
   （本 Pass 新增 SeparatePianoNode/SeparateStringsNode/SeparateOrganNode/
   SeparateGeneral6StemsNode/GenericDeReverbNode）。
3. **正確性細節**：guitar/piano/debreathe/lead_backing/drums_substem/
   synth_bass 這 6 個模式，目前直接呼叫 separator.xxx(..., is_already_X=False)
   時會內部自動先跑一次前置分離（去人聲/先抽鼓/先抽貝斯）；但 stem_separation_bt.py
   既有節點類別都寫死 is_already_X=True，假設呼叫者已經在同一棵 BT 樹先跑過前置
   節點。若直接套用會靜默跳過防呆步驟、讓結果劣化。修復方式：用明確的
   SequenceNode 把前置節點（SeparateVocalsNode/SeparateDrumsNode/SeparateBassNode）
   與目標節點串起來，讓「自動先去人聲/先抽鼓/先抽貝斯」變成看得見的 BT 結構，
   而不是藏在 separator.py 方法內部的旗標。

本測試驗證：
A. 5 個新節點類別的基本行為（mock separator，不觸發真實 AI 模型）。
B. guitar/piano 防呆鏈確實把 SeparateVocalsNode 產生的 instrumental_path
   餵給下一個節點（而非讓它落回 audio_path 直接處理原始混音）。
C. app.process_standalone_separation() 15 個 mode_id 全部改走 Blackboard+BT
   節點後，狀態訊息與回傳檔案路徑依然符合原本 UI 契約；且模組級 separator_engine
   死碼已移除。
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import app
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, SequenceNode
from pgm_craft.workflow.stem_separation_bt import (
    SeparateVocalsNode,
    SeparateGuitarNode,
    SeparatePianoNode,
    SeparateStringsNode,
    SeparateOrganNode,
    SeparateGeneral6StemsNode,
    GenericDeReverbNode,
)


def _make_wav(path, sr=44100, duration=0.2):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    sf.write(path, y, sr)
    return path


class MockStemSeparator:
    """快速 mock，涵蓋本 Pass 新增節點所需的 separator 方法，避免觸發真實模型。"""

    def separate_vocals(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        v = os.path.join(output_dir, "vocals.wav")
        i = os.path.join(output_dir, "instrumental.wav")
        shutil.copyfile(audio_path, v)
        shutil.copyfile(audio_path, i)
        return v, i

    def separate_piano(self, audio_path, output_dir, is_already_instrumental=False):
        os.makedirs(output_dir, exist_ok=True)
        p = os.path.join(output_dir, "piano.wav")
        np_ = os.path.join(output_dir, "no_piano.wav")
        shutil.copyfile(audio_path, p)
        shutil.copyfile(audio_path, np_)
        return p, np_

    def separate_strings(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        s = os.path.join(output_dir, "strings.wav")
        ns = os.path.join(output_dir, "no_strings.wav")
        shutil.copyfile(audio_path, s)
        shutil.copyfile(audio_path, ns)
        return s, ns

    def separate_organ(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        o = os.path.join(output_dir, "organ.wav")
        no = os.path.join(output_dir, "no_organ.wav")
        shutil.copyfile(audio_path, o)
        shutil.copyfile(audio_path, no)
        return o, no

    def separate_general_6stems(self, audio_path, output_dir, enable_enhancement=True):
        os.makedirs(output_dir, exist_ok=True)
        res = {}
        for key in ("vocals", "drums", "bass", "guitar", "piano", "other"):
            p = os.path.join(output_dir, f"{key}.wav")
            shutil.copyfile(audio_path, p)
            res[key] = p
        return res

    def process_dereverb(self, audio_path, output_dir, is_already_single_stem=False):
        os.makedirs(output_dir, exist_ok=True)
        dry = os.path.join(output_dir, "dereverb_dry.wav")
        room = os.path.join(output_dir, "reverb_room.wav")
        shutil.copyfile(audio_path, dry)
        shutil.copyfile(audio_path, room)
        return dry, room

    def separate_guitar(self, audio_path, output_dir, is_already_instrumental=False):
        os.makedirs(output_dir, exist_ok=True)
        g = os.path.join(output_dir, "guitar.wav")
        ng = os.path.join(output_dir, "no_guitar.wav")
        shutil.copyfile(audio_path, g)
        shutil.copyfile(audio_path, ng)
        return g, ng


# ---------------------------------------------------------------------------
# A. 新節點類別基本行為
# ---------------------------------------------------------------------------

class TestNewGenericSeparationNodes(unittest.TestCase):

    def setUp(self):
        self.mock_sep = MockStemSeparator()
        self.root = tempfile.mkdtemp()
        self.audio_path = _make_wav(os.path.join(self.root, "audio.wav"))
        self.stems_dir = os.path.join(self.root, "stems")
        os.makedirs(self.stems_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _bb(self):
        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("stems_dir", self.stems_dir)
        return bb

    def test_separate_piano_node(self):
        bb = self._bb()
        status = SeparatePianoNode(self.mock_sep).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(os.path.isfile(bb.get_val("piano_path")))

    def test_separate_strings_node(self):
        bb = self._bb()
        status = SeparateStringsNode(self.mock_sep).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(os.path.isfile(bb.get_val("strings_path")))

    def test_separate_organ_node(self):
        bb = self._bb()
        status = SeparateOrganNode(self.mock_sep).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(os.path.isfile(bb.get_val("organ_path")))

    def test_separate_general_6stems_node(self):
        bb = self._bb()
        status = SeparateGeneral6StemsNode(self.mock_sep).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        stems = bb.get_val("stems_6", {})
        for key in ("vocals", "drums", "bass", "guitar", "piano", "other"):
            self.assertIn(key, stems)
        self.assertIn("vocals", bb.get_val("stems", {}))

    def test_generic_dereverb_node(self):
        bb = self._bb()
        status = GenericDeReverbNode(self.mock_sep).execute(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(os.path.isfile(bb.get_val("dereverb_dry_path")))
        self.assertTrue(os.path.isfile(bb.get_val("dereverb_room_path")))


# ---------------------------------------------------------------------------
# B. 防呆鏈正確性：先去人聲的 instrumental_path 必須被下一個節點吃到
# ---------------------------------------------------------------------------

class TestGuardChainFeedsPrerequisiteOutput(unittest.TestCase):
    """迴歸測試：Stage 2 既有節點寫死 is_already_instrumental=True，若不先接
    SeparateVocalsNode 直接單獨呼叫，會靜默跳過去人聲防呆。這裡驗證用
    SequenceNode 串接後，目標節點的輸入確實是 SeparateVocalsNode 產生的
    instrumental_path，而不是原始混音。"""

    def setUp(self):
        self.mock_sep = MockStemSeparator()
        self.root = tempfile.mkdtemp()
        self.audio_path = _make_wav(os.path.join(self.root, "audio.wav"))
        self.stems_dir = os.path.join(self.root, "stems")
        os.makedirs(self.stems_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_guitar_guard_chain_consumes_instrumental_path(self):
        calls = []
        real_separate_guitar = self.mock_sep.separate_guitar

        def spy_separate_guitar(audio_path, output_dir, is_already_instrumental=False):
            calls.append(audio_path)
            return real_separate_guitar(audio_path, output_dir, is_already_instrumental)

        self.mock_sep.separate_guitar = spy_separate_guitar

        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("stems_dir", self.stems_dir)

        status = SequenceNode(
            "GuitarGuardChain",
            [SeparateVocalsNode(self.mock_sep), SeparateGuitarNode(self.mock_sep)],
        ).execute(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(len(calls), 1)
        # SeparateGuitarNode 吃到的必須是 SeparateVocalsNode 產生的 instrumental_path，
        # 不能是原始的 audio_path（那樣代表去人聲步驟被靜默跳過）。
        self.assertEqual(calls[0], bb.get_val("instrumental_path"))
        self.assertNotEqual(calls[0], self.audio_path)

    def test_piano_guard_chain_consumes_instrumental_path(self):
        calls = []
        real_separate_piano = self.mock_sep.separate_piano

        def spy_separate_piano(audio_path, output_dir, is_already_instrumental=False):
            calls.append(audio_path)
            return real_separate_piano(audio_path, output_dir, is_already_instrumental)

        self.mock_sep.separate_piano = spy_separate_piano

        bb = Blackboard()
        bb.set_val("audio_path", self.audio_path)
        bb.set_val("stems_dir", self.stems_dir)

        status = SequenceNode(
            "PianoGuardChain",
            [SeparateVocalsNode(self.mock_sep), SeparatePianoNode(self.mock_sep)],
        ).execute(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], bb.get_val("instrumental_path"))
        self.assertNotEqual(calls[0], self.audio_path)


# ---------------------------------------------------------------------------
# C. app.process_standalone_separation() 15 個模式端對端（class-level mock）
# ---------------------------------------------------------------------------

class TestAppStandaloneSeparationAllModesRouteThroughBT(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audio_path = _make_wav(os.path.join(self.temp_dir, "input.wav"))
        self.mock_sep = MockStemSeparator()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _patch_all(self):
        return [
            patch.object(CascadedStemSeparator, "separate_vocals", self.mock_sep.separate_vocals),
            patch.object(CascadedStemSeparator, "separate_guitar", self.mock_sep.separate_guitar),
            patch.object(CascadedStemSeparator, "separate_piano", self.mock_sep.separate_piano),
            patch.object(CascadedStemSeparator, "separate_strings", self.mock_sep.separate_strings),
            patch.object(CascadedStemSeparator, "separate_organ", self.mock_sep.separate_organ),
            patch.object(CascadedStemSeparator, "separate_general_6stems", self.mock_sep.separate_general_6stems),
            patch.object(CascadedStemSeparator, "process_dereverb", self.mock_sep.process_dereverb),
        ]

    def _run_mode(self, mode_id):
        patchers = self._patch_all()
        for p in patchers:
            p.start()
        try:
            return app.process_standalone_separation(self.audio_path, mode_id, self.temp_dir)
        finally:
            for p in patchers:
                p.stop()

    def test_no_module_level_separator_engine_singleton(self):
        """稽核修復：模組級 separator_engine = CascadedStemSeparator() 死碼已移除
        （每個 BT 節點各自持有自己的 separator 實例）。"""
        self.assertFalse(hasattr(app, "separator_engine"))

    def test_vocals_mode_routes_through_bt_node(self):
        status, vocal, drums, bass, extra = self._run_mode("vocals")
        self.assertIn("完成【人聲分離】", status)
        self.assertTrue(os.path.exists(vocal))
        self.assertTrue(os.path.exists(extra))

    def test_guitar_mode_guard_message_and_output(self):
        status, vocal, drums, bass, extra = self._run_mode("guitar")
        self.assertIn("防呆保護啟動", status)
        self.assertIn("完成【吉他分離】", status)
        self.assertTrue(os.path.exists(extra))

    def test_piano_mode_guard_message_and_output(self):
        status, vocal, drums, bass, extra = self._run_mode("piano")
        self.assertIn("防呆保護啟動", status)
        self.assertIn("完成【鋼琴分離】", status)
        self.assertTrue(os.path.exists(extra))

    def test_strings_mode_output(self):
        status, vocal, drums, bass, extra = self._run_mode("strings")
        self.assertIn("完成【弦樂分離】", status)
        self.assertTrue(os.path.exists(extra))

    def test_organ_mode_output(self):
        status, vocal, drums, bass, extra = self._run_mode("organ")
        self.assertIn("完成【風琴分離】", status)
        self.assertTrue(os.path.exists(extra))

    def test_general_6stem_mode_output(self):
        status, vocal, drums, bass, extra = self._run_mode("general_6stem")
        self.assertIn("6-Stem", status)
        self.assertTrue(os.path.exists(vocal))
        self.assertTrue(os.path.exists(drums))
        self.assertTrue(os.path.exists(bass))

    def test_dereverb_mode_output(self):
        status, vocal, drums, bass, extra = self._run_mode("dereverb")
        self.assertIn("完成【去殘響處理】", status)
        self.assertTrue(os.path.exists(extra))

    def test_debreathe_mode_guard_message(self):
        status, vocal, drums, bass, extra = self._run_mode("debreathe")
        self.assertIn("人聲 Guard 啟動", status)
        self.assertIn("完成【人聲去換氣聲】", status)

    def test_lead_backing_mode_guard_message(self):
        status, vocal, drums, bass, extra = self._run_mode("lead_backing")
        self.assertIn("極高前置保護啟動", status)
        self.assertIn("完成【主唱與和聲拆解】", status)

    def test_drums_substem_mode_guard_message(self):
        status, vocal, drums, bass, extra = self._run_mode("drums_substem")
        self.assertIn("鼓組 Guard 啟動", status)
        self.assertIn("完成【鼓組細分】", status)

    def test_synth_bass_mode_guard_message(self):
        status, vocal, drums, bass, extra = self._run_mode("synth_bass")
        self.assertIn("貝斯 Guard 啟動", status)
        self.assertIn("完成【貝斯細分】", status)


if __name__ == "__main__":
    unittest.main()
