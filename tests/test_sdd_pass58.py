"""
SDD Pass 58 — 獨立影音下載區塊升級單元測試
"""

import os
import tempfile
import unittest
from app import standalone_download


class TestSDDPass58DownloaderOptimization(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_standalone_download_empty_url_guard(self):
        """驗證當輸入空 URL 時防呆保護運作」"""
        res = standalone_download("", self.test_dir)
        self.assertIn("請先輸入有效的影音或社群網址", res[0])
        self.assertIsNone(res[1])


if __name__ == "__main__":
    unittest.main()
