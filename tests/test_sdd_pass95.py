"""
SDD Pass 95 — BT 建構進度文檔 (BT-BUILD-PROGRESS.md) 完整性與 SDD 測試歸檔測試
"""

import os
import unittest


class TestSDDPass95BTBuildProgressDoc(unittest.TestCase):

    def setUp(self):
        self.doc_path = os.path.join("docs", "BT-BUILD-PROGRESS.md")

    def test_bt_build_progress_file_exists(self):
        """驗證 BT-BUILD-PROGRESS.md 存在且非空"""
        self.assertTrue(os.path.exists(self.doc_path))
        self.assertGreater(os.path.getsize(self.doc_path), 100)

    def test_bt_build_progress_contains_sdd_pass_93_and_94(self):
        """驗證 BT-BUILD-PROGRESS.md 包含最新 Pass 93 與 Pass 94 實作紀錄"""
        with open(self.doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Pass 93", content)
        self.assertIn("Pass 94", content)


if __name__ == "__main__":
    unittest.main()
