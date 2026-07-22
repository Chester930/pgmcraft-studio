import unittest
from pgm_craft.workflow.downloaders import (
    URLDownloaderDispatcher,
    YouTubeHandler,
    BilibiliHandler,
    InstagramHandler,
    TikTokHandler,
    GenericYtdlpHandler
)

class TestURLDownloaders(unittest.TestCase):
    def setUp(self):
        self.dispatcher = URLDownloaderDispatcher()

    def test_domain_matching(self):
        """測試影音與社群平台 URL 域名自動偵測匹配邏輯"""
        yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        bilibili_url = "https://www.bilibili.com/video/BV1xx411c7mD"
        ig_url = "https://www.instagram.com/reels/C123456789/"
        tiktok_url = "https://www.tiktok.com/@user/video/7123456789"

        self.assertTrue(YouTubeHandler().can_handle(yt_url))
        self.assertTrue(BilibiliHandler().can_handle(bilibili_url))
        self.assertTrue(InstagramHandler().can_handle(ig_url))
        self.assertTrue(TikTokHandler().can_handle(tiktok_url))

if __name__ == '__main__':
    unittest.main()
