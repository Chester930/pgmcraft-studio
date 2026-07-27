"""
SDD Pass 57 — Ableton Live .als 原生工程檔導出器單元測試
"""

import os
import gzip
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pgm_craft.daw_exporter import DAWExporter


class TestSDDPass57AbletonALSExporter(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ableton_als_exporter_gzip_and_xml_structure(self):
        """驗證 generate_ableton_als 產出合法且可解壓的 .als Gzip XML 專案檔」"""
        exporter = DAWExporter()
        report = {
            "song_title": "Ableton Test Track",
            "average_bpm": 124.0,
            "chord_progression": [
                {"measure": 1, "start_time": 0.0, "chord": "C"},
                {"measure": 2, "start_time": 2.0, "chord": "G"}
            ],
            "sections": [{"measure": 1, "name": "Intro"}]
        }
        als_path = exporter.generate_ableton_als(report, self.test_dir)
        self.assertTrue(os.path.exists(als_path))
        self.assertTrue(als_path.endswith(".als"))

        # 驗證可以用 Gzip 解壓讀取 XML
        with gzip.open(als_path, "rb") as f:
            xml_bytes = f.read()

        xml_str = xml_bytes.decode("utf-8")
        self.assertIn("Ableton", xml_str)
        self.assertIn("MasterTrack", xml_str)
        self.assertIn("Intro", xml_str)

        root = ET.fromstring(xml_bytes)
        self.assertEqual(root.tag, "Ableton")
        self.assertEqual(root.attrib.get("Creator"), "PGMCraft Studio v2.1.0")


if __name__ == "__main__":
    unittest.main()
