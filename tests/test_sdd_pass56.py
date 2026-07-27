"""
SDD Pass 56 — P1 雙核護航 (立體聲相位反相修復與 Unicode Zip 防亂碼) 單元測試
"""

import os
import zipfile
import tempfile
import unittest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.audio_quality_bt import StereoPhaseCorrectionNode
from pgm_craft.packager import PGMProjectPackager


class TestSDDPass56P1Features(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stereo_phase_cancellation_repair(self):
        """驗證 StereoPhaseCorrectionNode 在檢測到 corr < -0.5 時成功自動翻轉修復"""
        node = StereoPhaseCorrectionNode()
        blackboard = Blackboard()

        # 創造 180 度嚴重反相音訊 (corr = -1.0)
        t = np.linspace(0, 1.0, 22050, endpoint=False)
        left = np.sin(2 * np.pi * 440 * t)
        right = -np.sin(2 * np.pi * 440 * t)
        y = np.vstack([left, right])

        blackboard.set_val("y", y)
        blackboard.set_val("quality_report", {"stereo_correlation": -1.0})

        node.execute(blackboard)

        self.assertTrue(blackboard.get_val("phase_corrected"))
        new_y = blackboard.get_val("y")
        # 翻轉後兩頻道應該 100% 同相 (corr = 1.0)
        new_corr = float(np.corrcoef(new_y[0], new_y[1])[0, 1])
        self.assertAlmostEqual(new_corr, 1.0, places=4)

    def test_unicode_zip_filename_protection(self):
        """驗證包含中文/日文與特殊符號之檔名打包為 ZIP 後保留 UTF-8 0x800 旗標」"""
        packager = PGMProjectPackager()
        pkg_dir = os.path.join(self.test_dir, "夜に駆ける_pgm_package")
        os.makedirs(pkg_dir, exist_ok=True)
        sample_file = os.path.join(pkg_dir, "日本語測試_click.wav")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("dummy audio content")

        zip_p = packager.build_zip_archive(pkg_dir)
        self.assertTrue(os.path.exists(zip_p))

        with zipfile.ZipFile(zip_p, "r") as z:
            info = z.getinfo("夜に駆ける_pgm_package/日本語測試_click.wav")
            self.assertTrue(info.flag_bits & 0x800)


if __name__ == "__main__":
    unittest.main()
