"""
v2.0 雙向 Behavior Tree 節點插件加載器 (PluginLoader) 單元測試
"""

import os
import shutil
import tempfile
import unittest
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.plugin_loader import PluginLoader

class TestPluginLoader(unittest.TestCase):
    def setUp(self):
        self.plugin_dir = tempfile.mkdtemp()
        
        # 建立動態 Mock 插件 Python 檔案
        self.plugin_file = os.path.join(self.plugin_dir, "demo_custom_node.py")
        code = """
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard

class CustomGuitarNode(BaseNode):
    def __init__(self):
        super().__init__("CustomGuitarNode")
    def execute(self, blackboard: Blackboard) -> NodeStatus:
        blackboard.set_val("guitar_processed", True)
        return NodeStatus.SUCCESS
"""
        with open(self.plugin_file, "w", encoding="utf-8") as f:
            f.write(code)

    def tearDown(self):
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def test_load_external_node_plugins(self):
        """測試 PluginLoader 能動態探測外部目錄並實體化 BaseNode 插件"""
        loader = PluginLoader(plugin_dirs=[self.plugin_dir])
        loaded_nodes = loader.load_plugins()
        
        self.assertIn("CustomGuitarNode", loaded_nodes)
        custom_node = loaded_nodes["CustomGuitarNode"]()
        
        self.assertIsInstance(custom_node, BaseNode)
        
        blackboard = Blackboard()
        status = custom_node.execute(blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(blackboard.get_val("guitar_processed"))

if __name__ == '__main__':
    unittest.main()
