import unittest
import os
import shutil
import tempfile
from pgm_craft.separator import CascadedStemSeparator

class TestCascadedStemSeparatorPrerequisites(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_audio = "sample_test.wav"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_separate_general_4stems(self):
        """測試通用標準 4-Stem 一鍵分軌 (Vocals, Drums, Bass, Other)"""
        separator = CascadedStemSeparator()
        res = separator.separate_general_4stems(self.test_audio, self.temp_dir, enable_enhancement=True)
        self.assertTrue(os.path.exists(res["vocals"]))
        self.assertTrue(os.path.exists(res["drums"]))
        self.assertTrue(os.path.exists(res["bass"]))
        self.assertTrue(os.path.exists(res["other"]))

    def test_separate_general_6stems(self):
        """測試通用進階 6-Stem 一鍵分軌 (Vocals, Drums, Bass, Guitar, Piano, Other)"""
        separator = CascadedStemSeparator()
        res = separator.separate_general_6stems(self.test_audio, self.temp_dir, enable_enhancement=True)
        self.assertTrue(os.path.exists(res["vocals"]))
        self.assertTrue(os.path.exists(res["drums"]))
        self.assertTrue(os.path.exists(res["bass"]))
        self.assertTrue(os.path.exists(res["guitar"]))
        self.assertTrue(os.path.exists(res["piano"]))
        self.assertTrue(os.path.exists(res["other"]))

    def test_guitar_prerequisite_guard(self):
        """測試吉他分軌防呆 Guard (自動先執行 Pass 1 去人聲)"""
        separator = CascadedStemSeparator()
        guitar_path, no_guitar_path = separator.separate_guitar(self.test_audio, self.temp_dir, is_already_instrumental=False)
        self.assertTrue(os.path.exists(guitar_path))
        self.assertTrue(os.path.exists(no_guitar_path))

    def test_lead_backing_prerequisite_guard(self):
        """測試主唱/和聲細分防呆 Guard (自動先執行 Pass 1 剝離純人聲)"""
        separator = CascadedStemSeparator()
        lead_path, backing_path = separator.separate_lead_and_backing(self.test_audio, self.temp_dir, is_already_vocal=False)
        self.assertTrue(os.path.exists(lead_path))
        self.assertTrue(os.path.exists(backing_path))

if __name__ == '__main__':
    unittest.main()
