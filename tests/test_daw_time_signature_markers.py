"""
多變拍號 (Time Signature Markers) DAW 導出單元測試
"""

import os
import shutil
import tempfile
import unittest
from pgm_craft.daw_exporter import DAWExporter

class TestDAWTimeSignatureMarkers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.report = {
            "audio_file": "demo_complex.wav",
            "average_bpm": 120.0,
            "estimated_key": "G Major",
            "time_signatures": [
                {"measure": 1, "numerator": 4, "denominator": 4},
                {"measure": 9, "numerator": 3, "denominator": 4}
            ]
        }
        self.exporter = DAWExporter()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_reaper_time_signature_markers(self):
        """測試 Reaper RPP 專案檔正確包含 Time Signature 標籤與變拍號 Marker"""
        rpp_path = self.exporter.export_reaper_project(self.report, output_dir=self.temp_dir)
        self.assertTrue(os.path.exists(rpp_path))
        with open(rpp_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("HAS_TIME_SIGNATURE", content)

    def test_export_cubase_time_signature_markers(self):
        """測試 Cubase Tempo Track CSV 正確包含變拍號資料欄位"""
        csv_path = self.exporter.export_cubase_tempo_track(self.report, output_dir=self.temp_dir)
        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Time Signature", content)

if __name__ == '__main__':
    unittest.main()
