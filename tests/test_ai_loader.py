"""
AI 模型動態加載器 (AILoader) 單元測試
"""

import unittest
from unittest.mock import patch
from pgm_craft.ai_loader import AILoader, get_model_status_report

class TestAILoader(unittest.TestCase):
    def setUp(self):
        self.loader = AILoader()

    def test_check_model_availability_all_keys(self):
        """測試 AILoader.check_all_models() 包含所有關鍵 AI 模型的狀態字典"""
        status = self.loader.check_all_models()
        self.assertIn("BeatNet", status)
        self.assertIn("crepe", status)
        self.assertIn("basic_pitch", status)
        self.assertIn("whisper", status)
        self.assertIn("demucs", status)

    @patch('builtins.__import__')
    def test_model_status_fallback_reason(self, mock_import):
        """測試當特定模型庫缺套件時，AILoader 正確記錄 is_available: False 與原因"""
        orig_import = __import__
        def side_effect(name, *args, **kwargs):
            if name == 'crepe':
                raise ImportError("No module named 'crepe'")
            return orig_import(name, *args, **kwargs)
        mock_import.side_effect = side_effect

        report = get_model_status_report()
        self.assertIn("crepe", report)
        self.assertFalse(report["crepe"]["is_available"])
        self.assertIn("fallback_reason", report["crepe"])

if __name__ == '__main__':
    unittest.main()
