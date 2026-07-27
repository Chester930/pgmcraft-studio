import unittest
import os
import shutil
import tempfile
from pgm_craft.daw_exporter import DAWExporter

class TestSDDPass36(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.report = {
            "estimated_key": "C Major",
            "average_bpm": 120.0,
            "total_measures": 8,
            "sections": [{"measure": 1, "name": "Intro"}, {"measure": 5, "name": "Chorus"}],
            "chord_progression": [{"measure": 1, "start_time": 0.0, "end_time": 2.0, "chord": "C"}],
            "subtitles_srt": "1\n00:00:00,000 --> 00:00:02,000\nHello Live PGM World",
            "outputs": {"mix_with_click": "mix_with_click.wav"}
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_live_dashboard_html_dynamic_teleprompter(self):
        """驗證 generate_live_dashboard_html 能成功產生包含動態 Web Audio JS 與歌詞高亮之 HTML」"""
        exporter = DAWExporter()
        html_path = exporter.generate_live_dashboard_html(self.report, output_dir=self.test_dir)
        
        self.assertTrue(os.path.exists(html_path))
        
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        # 驗證包含了歌詞、JS 播放滾動腳本與和弦卡片
        self.assertIn("Live 舞台", html_content)
        self.assertIn("currentTime", html_content)
        self.assertIn("Hello Live PGM World", html_content)

if __name__ == "__main__":
    unittest.main()
