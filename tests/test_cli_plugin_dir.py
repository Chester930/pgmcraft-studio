"""
CLI --plugin-dir 自訂 BT 節點插件目錄參數單元測試
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pgm_craft.cli import parse_args

class TestCLIPluginDir(unittest.TestCase):
    def test_cli_parse_plugin_dir_arg(self):
        """測試 CLI 參數解析正確包含 --plugin-dir 參數"""
        test_args = ["--audio", "sample_test.wav", "--plugin-dir", "custom_plugins"]
        with patch("sys.argv", ["cli.py"] + test_args):
            args = parse_args()
            self.assertEqual(args.plugin_dir, "custom_plugins")

if __name__ == '__main__':
    unittest.main()
