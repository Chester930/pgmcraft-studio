"""
SDD Pass 58 — 獨立影音下載區塊升級單元測試
"""

import os
import tempfile
import unittest
from unittest.mock import patch
import app
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

    def test_standalone_download_calls_dispatch_and_download_not_missing_method(self):
        """迴歸測試（音檔下載/音色分軌/節拍處理稽核發現）：舊版呼叫
        downloader_dispatcher.dispatch(...)，但 URLDownloaderDispatcher 根本沒有
        這個方法，每次使用都會拋出 AttributeError 並被外層 try/except 吞掉，變成
        「下載過程發生異常」。這裡直接驗證真正呼叫的是存在的
        dispatch_and_download(...)，不會再靜默失敗。"""
        wav_path = os.path.join(self.test_dir, "song.wav")
        mp3_path = os.path.join(self.test_dir, "song.mp3")
        mp4_path = os.path.join(self.test_dir, "song.mp4")
        for path in (wav_path, mp3_path, mp4_path):
            open(path, "wb").close()

        with patch.object(
            app.downloader_dispatcher,
            "dispatch_and_download",
            return_value={"wav": wav_path, "mp3": mp3_path, "mp4": mp4_path, "title": "Song"},
        ) as mocked:
            status_msg, preview_audio, mp4, wav, mp3 = standalone_download(
                "https://www.youtube.com/watch?v=fake", self.test_dir
            )

        mocked.assert_called_once_with("https://www.youtube.com/watch?v=fake", self.test_dir)
        self.assertIn("成功完成媒體無損下載", status_msg)
        self.assertEqual(wav, wav_path)
        self.assertEqual(mp3, mp3_path)
        self.assertEqual(mp4, mp4_path)


if __name__ == "__main__":
    unittest.main()
