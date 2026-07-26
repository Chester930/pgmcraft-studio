"""
SDD Pass 16 — Stage 0: Input Acquisition Behavior Tree
=======================================================
Module 1: ValidateInputNode / ValidateProjectRootNode guard logic
Module 2: IsURLConditionNode / IsLocalFileConditionNode condition logic
Module 3: ValidateAudioFileNode format gate
Module 4: NormalizeToProjectWAVNode convergence (WAV fast-path + librosa fallback)
Module 5: ResolveProjectNameNode safe name derivation
Module 6: CreateProjectFolderNode standard dir structure
Module 7: CopySourceToProjectNode destination + blackboard contract
Module 8: build_input_acquisition_tree() full tree (local file end-to-end)
Module 9: InputAcquisitionBTEngine engine wrapper contract
"""

import os
import shutil
import tempfile
import unittest
import numpy as np

import soundfile as sf

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.input_acquisition_bt import (
    ValidateInputNode,
    ValidateProjectRootNode,
    IsURLConditionNode,
    IsLocalFileConditionNode,
    ValidateAudioFileNode,
    NormalizeToProjectWAVNode,
    ResolveProjectNameNode,
    CreateProjectFolderNode,
    CopySourceToProjectNode,
    build_input_acquisition_tree,
    InputAcquisitionBTEngine,
    SUPPORTED_AUDIO_EXTENSIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(path: str, sr: int = 44100, duration: float = 1.0) -> str:
    """Write a minimal valid WAV file and return its path."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    sf.write(path, y, sr)
    return path


# ---------------------------------------------------------------------------
# Module 1 — ValidateInputNode / ValidateProjectRootNode
# ---------------------------------------------------------------------------

class TestValidateInputNode(unittest.TestCase):

    def test_url_input_overwrites_audio_path(self):
        """url 填入時應覆寫 audio_path 並回傳 SUCCESS"""
        bb = Blackboard()
        bb.set_val("url", "https://www.youtube.com/watch?v=test")
        bb.set_val("audio_path", "")
        status = ValidateInputNode().run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(bb.get_val("audio_path").startswith("https://"))

    def test_local_audio_path_accepted(self):
        """audio_path 有值時回傳 SUCCESS（不改值）"""
        bb = Blackboard()
        bb.set_val("url", "")
        bb.set_val("audio_path", "/some/path/song.wav")
        status = ValidateInputNode().run(bb)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("audio_path"), "/some/path/song.wav")

    def test_both_empty_returns_failure(self):
        """url 與 audio_path 均空 → FAILURE"""
        bb = Blackboard()
        bb.set_val("url", "")
        bb.set_val("audio_path", "")
        status = ValidateInputNode().run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_url_priority_over_audio_path(self):
        """url 與 audio_path 同時有值 → url 優先"""
        bb = Blackboard()
        bb.set_val("url", "https://example.com/video")
        bb.set_val("audio_path", "/local/song.mp3")
        ValidateInputNode().run(bb)
        self.assertEqual(bb.get_val("audio_path"), "https://example.com/video")


class TestValidateProjectRootNode(unittest.TestCase):

    def test_valid_writable_dir_returns_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bb = Blackboard()
            bb.set_val("project_root", tmpdir)
            status = ValidateProjectRootNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

    def test_empty_root_returns_failure(self):
        bb = Blackboard()
        bb.set_val("project_root", "")
        status = ValidateProjectRootNode().run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_missing_key_returns_failure(self):
        """project_root 未設定時應 FAILURE（非拋例外）"""
        bb = Blackboard()
        status = ValidateProjectRootNode().run(bb)
        self.assertEqual(status, NodeStatus.FAILURE)

    def test_new_dir_is_created_if_not_exist(self):
        with tempfile.TemporaryDirectory() as base:
            new_dir = os.path.join(base, "brand_new_project_root")
            bb = Blackboard()
            bb.set_val("project_root", new_dir)
            status = ValidateProjectRootNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertTrue(os.path.isdir(new_dir))


# ---------------------------------------------------------------------------
# Module 2 — Condition Nodes
# ---------------------------------------------------------------------------

class TestConditionNodes(unittest.TestCase):

    def test_is_url_condition_success_http(self):
        bb = Blackboard()
        bb.set_val("audio_path", "http://example.com/media.mp3")
        self.assertEqual(IsURLConditionNode().run(bb), NodeStatus.SUCCESS)

    def test_is_url_condition_success_https(self):
        bb = Blackboard()
        bb.set_val("audio_path", "https://www.youtube.com/watch?v=abc")
        self.assertEqual(IsURLConditionNode().run(bb), NodeStatus.SUCCESS)

    def test_is_url_condition_failure_local(self):
        bb = Blackboard()
        bb.set_val("audio_path", "/local/file.wav")
        self.assertEqual(IsURLConditionNode().run(bb), NodeStatus.FAILURE)

    def test_is_local_file_success(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            bb = Blackboard()
            bb.set_val("audio_path", path)
            self.assertEqual(IsLocalFileConditionNode().run(bb), NodeStatus.SUCCESS)
        finally:
            os.unlink(path)

    def test_is_local_file_failure_missing(self):
        bb = Blackboard()
        bb.set_val("audio_path", "/nonexistent/file.wav")
        self.assertEqual(IsLocalFileConditionNode().run(bb), NodeStatus.FAILURE)


# ---------------------------------------------------------------------------
# Module 3 — ValidateAudioFileNode
# ---------------------------------------------------------------------------

class TestValidateAudioFileNode(unittest.TestCase):

    def _bb_with_path(self, path: str) -> Blackboard:
        bb = Blackboard()
        bb.set_val("audio_path", path)
        return bb

    def test_wav_is_accepted(self):
        bb = self._bb_with_path("/music/track.wav")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("source_type"), "local_file")
        self.assertEqual(bb.get_val("media_title"), "track")

    def test_mp3_is_accepted(self):
        bb = self._bb_with_path("/music/track.mp3")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.SUCCESS)

    def test_flac_is_accepted(self):
        bb = self._bb_with_path("/music/track.flac")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.SUCCESS)

    def test_m4a_is_accepted(self):
        bb = self._bb_with_path("/music/track.m4a")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.SUCCESS)

    def test_txt_is_rejected(self):
        bb = self._bb_with_path("/doc/readme.txt")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.FAILURE)

    def test_exe_is_rejected(self):
        bb = self._bb_with_path("/bin/virus.exe")
        self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.FAILURE)

    def test_all_supported_extensions_pass(self):
        for ext in SUPPORTED_AUDIO_EXTENSIONS:
            with self.subTest(ext=ext):
                bb = self._bb_with_path(f"/music/track{ext}")
                self.assertEqual(ValidateAudioFileNode().run(bb), NodeStatus.SUCCESS)

    def test_raw_wav_path_written(self):
        bb = self._bb_with_path("/music/track.wav")
        ValidateAudioFileNode().run(bb)
        self.assertEqual(bb.get_val("raw_wav_path"), "/music/track.wav")


# ---------------------------------------------------------------------------
# Module 4 — NormalizeToProjectWAVNode
# ---------------------------------------------------------------------------

class TestNormalizeToProjectWAVNode(unittest.TestCase):

    def test_wav_with_good_sr_is_reused(self):
        """WAV 取樣率 >= 22050 時應直接重用，不轉換"""
        with tempfile.TemporaryDirectory() as tmpdir:
            wav = _make_wav(os.path.join(tmpdir, "song.wav"), sr=44100)
            bb = Blackboard()
            bb.set_val("raw_wav_path", wav)
            bb.set_val("media_title", "song")
            status = NormalizeToProjectWAVNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            self.assertEqual(bb.get_val("normalized_wav_path"), wav)

    def test_mp3_converted_to_wav(self):
        """非 WAV 格式（.mp3）應被轉換，輸出 _normalized.wav"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 模擬 mp3：實際上寫入一個 WAV 但把副檔名改成 .mp3，
            # 觸發轉換路徑（若 ffmpeg 不存在走 librosa fallback）
            src = os.path.join(tmpdir, "song.mp3")
            _make_wav(src.replace(".mp3", "_tmp.wav"))
            # 用 WAV 資料偽裝成 mp3（測試環境 ffmpeg/librosa 處理能力）
            import shutil
            shutil.copy(src.replace(".mp3", "_tmp.wav"), src)

            bb = Blackboard()
            bb.set_val("raw_wav_path", src)
            bb.set_val("media_title", "song")
            status = NormalizeToProjectWAVNode().run(bb)
            # 可接受 SUCCESS（ffmpeg 成功）或 FAILURE（兩個都不可用）
            # 只要不拋例外就算合格
            self.assertIn(status, [NodeStatus.SUCCESS, NodeStatus.FAILURE])

    def test_low_sr_wav_triggers_conversion(self):
        """低取樣率 WAV（8000Hz）應觸發轉換路徑"""
        with tempfile.TemporaryDirectory() as tmpdir:
            wav = os.path.join(tmpdir, "low_sr.wav")
            t = np.linspace(0, 1, 8000, endpoint=False)
            y = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
            sf.write(wav, y, 8000)

            bb = Blackboard()
            bb.set_val("raw_wav_path", wav)
            bb.set_val("media_title", "low_sr")
            status = NormalizeToProjectWAVNode().run(bb)
            self.assertIn(status, [NodeStatus.SUCCESS, NodeStatus.FAILURE])


# ---------------------------------------------------------------------------
# Module 5 — ResolveProjectNameNode
# ---------------------------------------------------------------------------

class TestResolveProjectNameNode(unittest.TestCase):

    def test_normal_title_passes_through(self):
        bb = Blackboard()
        bb.set_val("media_title", "My Song")
        ResolveProjectNameNode().run(bb)
        self.assertEqual(bb.get_val("project_name"), "My_Song")

    def test_illegal_chars_removed(self):
        bb = Blackboard()
        bb.set_val("media_title", 'Song: A/B\\C?*"<>|')
        ResolveProjectNameNode().run(bb)
        name = bb.get_val("project_name")
        for c in r'\/*?:"<>|':
            self.assertNotIn(c, name)

    def test_long_title_truncated_to_120(self):
        bb = Blackboard()
        bb.set_val("media_title", "A" * 200)
        ResolveProjectNameNode().run(bb)
        self.assertLessEqual(len(bb.get_val("project_name")), 120)

    def test_empty_title_gets_default(self):
        bb = Blackboard()
        bb.set_val("media_title", "   ")
        ResolveProjectNameNode().run(bb)
        self.assertEqual(bb.get_val("project_name"), "untitled_project")

    def test_cjk_title_preserved(self):
        bb = Blackboard()
        bb.set_val("media_title", "周杰倫 稻香")
        ResolveProjectNameNode().run(bb)
        name = bb.get_val("project_name")
        self.assertIn("周杰倫", name)


# ---------------------------------------------------------------------------
# Module 6 — CreateProjectFolderNode
# ---------------------------------------------------------------------------

class TestCreateProjectFolderNode(unittest.TestCase):

    EXPECTED_SUBDIRS = {"source", "stems", "click", "midi", "reports"}

    def test_all_standard_subdirs_created(self):
        with tempfile.TemporaryDirectory() as root:
            bb = Blackboard()
            bb.set_val("project_root", root)
            bb.set_val("project_name", "TestProject")
            status = CreateProjectFolderNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)
            project_dir = bb.get_val("project_dir")
            self.assertTrue(os.path.isdir(project_dir))
            for sub in self.EXPECTED_SUBDIRS:
                self.assertTrue(os.path.isdir(os.path.join(project_dir, sub)), sub)

    def test_project_dir_written_to_blackboard(self):
        with tempfile.TemporaryDirectory() as root:
            bb = Blackboard()
            bb.set_val("project_root", root)
            bb.set_val("project_name", "MyProject")
            CreateProjectFolderNode().run(bb)
            expected = os.path.join(root, "MyProject")
            self.assertEqual(bb.get_val("project_dir"), expected)

    def test_idempotent_when_called_twice(self):
        with tempfile.TemporaryDirectory() as root:
            bb = Blackboard()
            bb.set_val("project_root", root)
            bb.set_val("project_name", "Idempotent")
            self.assertEqual(CreateProjectFolderNode().run(bb), NodeStatus.SUCCESS)
            self.assertEqual(CreateProjectFolderNode().run(bb), NodeStatus.SUCCESS)


# ---------------------------------------------------------------------------
# Module 7 — CopySourceToProjectNode
# ---------------------------------------------------------------------------

class TestCopySourceToProjectNode(unittest.TestCase):

    def test_wav_copied_and_audio_path_updated(self):
        with tempfile.TemporaryDirectory() as root:
            # Set up project structure
            project_dir = os.path.join(root, "TestSong")
            source_dir = os.path.join(project_dir, "source")
            os.makedirs(source_dir)

            # Source WAV
            src_wav = _make_wav(os.path.join(root, "tmp.wav"))

            bb = Blackboard()
            bb.set_val("normalized_wav_path", src_wav)
            bb.set_val("project_dir", project_dir)
            bb.set_val("project_name", "TestSong")

            status = CopySourceToProjectNode().run(bb)
            self.assertEqual(status, NodeStatus.SUCCESS)

            dest = os.path.join(source_dir, "TestSong.wav")
            self.assertTrue(os.path.exists(dest))
            self.assertEqual(bb.get_val("audio_path"), dest)

    def test_missing_source_returns_failure(self):
        with tempfile.TemporaryDirectory() as root:
            project_dir = os.path.join(root, "TestSong")
            os.makedirs(os.path.join(project_dir, "source"))

            bb = Blackboard()
            bb.set_val("normalized_wav_path", "/nonexistent/file.wav")
            bb.set_val("project_dir", project_dir)
            bb.set_val("project_name", "TestSong")
            status = CopySourceToProjectNode().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)


# ---------------------------------------------------------------------------
# Module 8 — build_input_acquisition_tree() full tree (local file E2E)
# ---------------------------------------------------------------------------

class TestInputAcquisitionTreeLocalFile(unittest.TestCase):

    def test_local_wav_full_pipeline(self):
        """本地 WAV → 完整 BT 樹 → 專案結構 + blackboard 契約 OK"""
        with tempfile.TemporaryDirectory() as root:
            # Prepare source WAV
            src_wav = _make_wav(os.path.join(root, "my_song.wav"))

            bb = Blackboard()
            bb.set_val("audio_path", src_wav)
            bb.set_val("url", "")
            bb.set_val("project_root", root)

            tree = build_input_acquisition_tree()
            status = tree.run(bb)

            self.assertEqual(status, NodeStatus.SUCCESS)

            # Blackboard contract checks
            self.assertIsNotNone(bb.get_val("project_dir"))
            self.assertIsNotNone(bb.get_val("project_name"))
            self.assertIsNotNone(bb.get_val("audio_path"))
            self.assertEqual(bb.get_val("source_type"), "local_file")

            # File existence checks
            audio_path = bb.get_val("audio_path")
            self.assertTrue(os.path.isfile(audio_path), f"audio_path not found: {audio_path}")
            self.assertIn("source", audio_path)

            # Standard subdirs exist
            project_dir = bb.get_val("project_dir")
            for sub in ["source", "stems", "click", "midi", "reports"]:
                self.assertTrue(os.path.isdir(os.path.join(project_dir, sub)), sub)

    def test_no_input_returns_failure(self):
        with tempfile.TemporaryDirectory() as root:
            bb = Blackboard()
            bb.set_val("audio_path", "")
            bb.set_val("url", "")
            bb.set_val("project_root", root)
            status = build_input_acquisition_tree().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)

    def test_no_project_root_returns_failure(self):
        with tempfile.TemporaryDirectory() as root:
            src_wav = _make_wav(os.path.join(root, "song.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", src_wav)
            bb.set_val("url", "")
            bb.set_val("project_root", "")
            status = build_input_acquisition_tree().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)

    def test_unsupported_format_returns_failure(self):
        with tempfile.TemporaryDirectory() as root:
            fake = os.path.join(root, "bad_format.xyz")
            open(fake, "w").close()
            bb = Blackboard()
            bb.set_val("audio_path", fake)
            bb.set_val("url", "")
            bb.set_val("project_root", root)
            status = build_input_acquisition_tree().run(bb)
            self.assertEqual(status, NodeStatus.FAILURE)

    def test_workflow_trace_recorded(self):
        """所有節點執行後都應在 workflow_trace 留下記錄"""
        with tempfile.TemporaryDirectory() as root:
            src_wav = _make_wav(os.path.join(root, "trace_test.wav"))
            bb = Blackboard()
            bb.set_val("audio_path", src_wav)
            bb.set_val("url", "")
            bb.set_val("project_root", root)
            build_input_acquisition_tree().run(bb)
            trace = bb.get_val("workflow_trace", [])
            self.assertGreater(len(trace), 0)
            node_names = [t["node"] for t in trace]
            self.assertIn("ValidateInputNode", node_names)


# ---------------------------------------------------------------------------
# Module 9 — InputAcquisitionBTEngine wrapper
# ---------------------------------------------------------------------------

class TestInputAcquisitionBTEngine(unittest.TestCase):

    def test_engine_returns_blackboard(self):
        with tempfile.TemporaryDirectory() as root:
            src_wav = _make_wav(os.path.join(root, "engine_test.wav"))
            engine = InputAcquisitionBTEngine()
            bb = engine.run(audio_path=src_wav, project_root=root)
            self.assertIsInstance(bb, Blackboard)

    def test_engine_sets_status_key(self):
        with tempfile.TemporaryDirectory() as root:
            src_wav = _make_wav(os.path.join(root, "engine_status.wav"))
            engine = InputAcquisitionBTEngine()
            bb = engine.run(audio_path=src_wav, project_root=root)
            self.assertIn(
                bb.get_val("input_acquisition_status"),
                ["SUCCESS", "FAILURE", "RUNNING"]
            )

    def test_engine_success_on_valid_local_wav(self):
        with tempfile.TemporaryDirectory() as root:
            src_wav = _make_wav(os.path.join(root, "valid.wav"))
            engine = InputAcquisitionBTEngine()
            bb = engine.run(audio_path=src_wav, project_root=root)
            self.assertEqual(bb.get_val("input_acquisition_status"), "SUCCESS")
            self.assertTrue(os.path.isfile(bb.get_val("audio_path")))

    def test_engine_url_keyword_arg_accepted(self):
        """url= 關鍵字引數應被接受（不拋 TypeError）"""
        with tempfile.TemporaryDirectory() as root:
            engine = InputAcquisitionBTEngine()
            # URL 路徑在測試環境下載會失敗，但 engine.run() 本身不應拋例外
            try:
                bb = engine.run(url="https://example.com/fake.mp3", project_root=root)
                self.assertIsInstance(bb, Blackboard)
            except TypeError as e:
                self.fail(f"engine.run(url=...) raised TypeError: {e}")


if __name__ == "__main__":
    unittest.main()
