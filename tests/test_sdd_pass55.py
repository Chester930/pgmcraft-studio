"""
SDD Pass 55 — P1 雙核升級 (Sub-Bass 脈衝對位與 Live HTML Web Audio 視聽同步) 單元測試
"""

import os
import tempfile
import unittest
from pgm_craft.packager import PGMProjectPackager


class TestSDDPass55P1Features(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_live_dashboard_contains_web_audio_player(self):
        """驗證 export_live_dashboard 正確產出包含 Web Audio 播放器與動態滾動 DOM 的 HTML 檔案」"""
        packager = PGMProjectPackager()
        report = {
            "song_title": "Test Track",
            "bpm": 128,
            "key": "G Major",
            "chords": ["G", "D", "Em", "C"]
        }
        html_p = packager.export_live_dashboard(report, self.test_dir)
        self.assertTrue(os.path.exists(html_p))
        with open(html_p, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pgmAudio", content)
        self.assertIn("bar-card", content)
        self.assertIn("scrollIntoView", content)


if __name__ == "__main__":
    unittest.main()
