"""
SDD Pass 90 — HTML5 互動式 Web Audio API 多軌視聽同播與 Mute/Solo 控制器單元測試
"""

import os
import tempfile
import unittest
from pgm_craft.daw_exporter import DAWExporter


class TestSDDPass90WebAudioMultitrackPlayer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_dashboard_html_generation_with_multitrack_console(self):
        """驗證 generate_live_dashboard_html 成功生成包含 Mute/Solo 控制邏輯之 HTML5 檔案」"""
        exporter = DAWExporter()
        report = {
            "audio_file": "test_song.wav",
            "estimated_key": "A Minor",
            "average_bpm": 120.0,
            "min_bpm": 120.0,
            "max_bpm": 120.0,
            "total_measures": 16,
            "chord_progression": ["Am", "F", "C", "G"],
            "sections": [{"measure": 1, "name": "Intro"}],
            "outputs": {
                "mix_with_click": "mix.wav",
                "backing_with_click": "backing.wav",
                "iem_split_mono_lr": "iem.wav",
                "click_track": "click.wav"
            }
        }

        html_p = exporter.generate_live_dashboard_html(report, output_dir=self.test_dir)
        self.assertTrue(os.path.exists(html_p))

        with open(html_p, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("HTML5 Web Audio API 4-Track Console", content)
        self.assertIn("toggleMute", content)
        self.assertIn("toggleSolo", content)


if __name__ == "__main__":
    unittest.main()
