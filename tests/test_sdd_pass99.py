"""
SDD Pass 99 — Live Dashboard HTML 標題與音訊路徑安全讀取驗證測試
"""

import os
import shutil
import tempfile
import unittest
from pgm_craft.daw_exporter import DAWExporter


class TestSDDPass99LiveDashboardTitle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.report = {
            "media_title": "Test Track",
            "estimated_key": "G Major",
            "average_bpm": 128.0,
            "total_measures": 16,
            "sections": [{"measure": 1, "name": "Intro"}],
            "chord_progression": [],
            "outputs": {"mix_with_click": None}  # 測試 None 值防禦性相容
        }

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_live_dashboard_html_none_audio_safety(self):
        """驗證 generate_live_dashboard_html 在音訊 outputs 為 None 時仍能安全產出 HTML」"""
        exporter = DAWExporter()
        html_path = exporter.generate_live_dashboard_html(self.report, output_dir=self.temp_dir)

        self.assertTrue(os.path.exists(html_path))
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("PGMCraft Live 舞台視聽同步提詞器", content)


if __name__ == "__main__":
    unittest.main()
