"""
Gradio GUI 第 7 頁籤 - BT 節點動態插件管理器 (Plugin Manager) 單元測試
"""

import unittest
from app import render_plugin_manager_html

class TestPluginManagerTab(unittest.TestCase):
    def test_render_plugin_manager_html_output(self):
        """測試 render_plugin_manager_html 能正常產出 HTML 插件診斷面板"""
        html = render_plugin_manager_html(plugin_dirs=["plugins"])
        self.assertIn("BT 節點動態插件管理器", html)
        self.assertIn("DemoVocalEnhancerNode", html)

if __name__ == '__main__':
    unittest.main()
