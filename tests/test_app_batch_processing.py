"""
Gradio GUI 批次處理摘要 (render_batch_summary_html) 單元測試
"""

import unittest
from app import render_batch_summary_html

class TestAppBatchProcessing(unittest.TestCase):
    def test_render_batch_summary_html_output(self):
        """測試 render_batch_summary_html 能正常處理多檔批次分析結果並產出 HTML 表格卡片"""
        results = [
            {"file_name": "song1.mp3", "status": "SUCCESS", "bpm": 120.0, "key": "C Major", "measures": 16},
            {"file_name": "song2.wav", "status": "SUCCESS", "bpm": 128.5, "key": "A Minor", "measures": 32}
        ]
        
        html = render_batch_summary_html(results)
        self.assertIn("多檔案批次 PGM 分析任務摘要", html)
        self.assertIn("song1.mp3", html)
        self.assertIn("C Major", html)
        self.assertIn("song2.wav", html)
        self.assertIn("A Minor", html)

if __name__ == '__main__':
    unittest.main()
