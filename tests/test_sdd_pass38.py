import unittest
import os
import shutil
import tempfile
from pgm_craft.daw_exporter import DAWExporter

class TestSDDPass38(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.report = {
            "audio_file": "sample_test.wav",
            "average_bpm": 120.0,
            "sections": [{"measure": 1, "name": "Intro"}]
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_aaf_project(self):
        """驗證 DAWExporter 能成功導出通用 AAF / Pro Tools 相容 Session 檔」"""
        exporter = DAWExporter()
        aaf_path = exporter.export_aaf_project(self.report, output_dir=self.test_dir)
        
        self.assertTrue(os.path.exists(aaf_path))
        with open(aaf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AAF", content)

if __name__ == "__main__":
    unittest.main()
