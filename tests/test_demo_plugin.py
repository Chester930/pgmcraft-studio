"""
官方範例 BT 節點插件 (DemoVocalEnhancerNode) 載入與執行單元測試
"""

import unittest
from pgm_craft.plugin_loader import PluginLoader
from pgm_craft.workflow.nodes import Blackboard, NodeStatus

class TestDemoPlugin(unittest.TestCase):
    def test_demo_plugin_discovery_and_execution(self):
        """測試 PluginLoader 能自動掃描 plugins/demo_plugin/ 並執行 DemoVocalEnhancerNode"""
        loader = PluginLoader(plugin_dirs=["plugins"])
        nodes = loader.load_plugins()
        
        self.assertIn("DemoVocalEnhancerNode", nodes)
        
        node_cls = nodes["DemoVocalEnhancerNode"]
        node_inst = node_cls()
        
        blackboard = Blackboard()
        blackboard.set_val("y", [0.1, 0.2, 0.3])
        blackboard.set_val("sr", 22050)
        
        status = node_inst.execute(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(blackboard.get_val("vocal_enhanced_status"))

if __name__ == '__main__':
    unittest.main()
