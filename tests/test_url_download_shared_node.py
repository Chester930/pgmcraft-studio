"""
URLDownloadToTempNode now also preserves mp3/mp4 paths (not just wav) so it
can be shared between Stage 0 of the main pipeline (which only needs wav)
and the standalone download tab (app.standalone_download, which needs all
three formats) -- a single node instead of two separate download call paths.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from pgm_craft.workflow.downloaders import URLDownloaderDispatcher
from pgm_craft.workflow.input_acquisition_bt import URLDownloadToTempNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


class TestURLDownloadToTempNodePreservesAllFormats(unittest.TestCase):
    def setUp(self):
        self.project_root = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _mock_result(self):
        temp_dir = os.path.join(self.project_root, "_pgmcraft_temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        wav_path = os.path.join(temp_dir, "song.wav")
        mp3_path = os.path.join(temp_dir, "song.mp3")
        mp4_path = os.path.join(temp_dir, "song.mp4")
        for path in (wav_path, mp3_path, mp4_path):
            open(path, "wb").close()
        return {"wav": wav_path, "mp3": mp3_path, "mp4": mp4_path, "title": "Song"}

    def test_wav_mp3_mp4_all_written_to_blackboard(self):
        result = self._mock_result()
        bb = Blackboard()
        bb.set_val("audio_path", "https://example.invalid/watch?v=fake")
        bb.set_val("project_root", self.project_root)

        with patch.object(URLDownloaderDispatcher, "dispatch_and_download", return_value=result):
            status = URLDownloadToTempNode().execute(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("raw_wav_path"), result["wav"])
        self.assertEqual(bb.get_val("raw_mp3_path"), result["mp3"])
        self.assertEqual(bb.get_val("raw_mp4_path"), result["mp4"])
        self.assertEqual(bb.get_val("media_title"), "Song")

    def test_missing_optional_formats_become_none_not_missing_key(self):
        temp_dir = os.path.join(self.project_root, "_pgmcraft_temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        wav_path = os.path.join(temp_dir, "song.wav")
        open(wav_path, "wb").close()
        # handler only produced a wav this time (e.g. audio-only source)
        result = {"wav": wav_path, "mp3": None, "mp4": None, "title": "Song"}

        bb = Blackboard()
        bb.set_val("audio_path", "https://example.invalid/watch?v=fake")
        bb.set_val("project_root", self.project_root)

        with patch.object(URLDownloaderDispatcher, "dispatch_and_download", return_value=result):
            status = URLDownloadToTempNode().execute(bb)

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertEqual(bb.get_val("raw_wav_path"), wav_path)
        self.assertIsNone(bb.get_val("raw_mp3_path"))
        self.assertIsNone(bb.get_val("raw_mp4_path"))


if __name__ == "__main__":
    unittest.main()
