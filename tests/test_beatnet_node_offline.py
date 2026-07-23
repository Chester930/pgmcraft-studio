"""
BeatNetNode 離線降級與例外防禦單元測試
"""

import unittest
from unittest.mock import patch, MagicMock
from pgm_craft.workflow.nodes import Blackboard, NodeStatus, FallbackNode
from pgm_craft.workflow.audio_nodes import BeatNetNode, LibrosaBeatNode

class TestBeatNetNodeOffline(unittest.TestCase):
    def setUp(self):
        self.blackboard = Blackboard()
        self.blackboard.set_val("target_analysis_path", "sample_test.wav")

    @patch('builtins.__import__')
    def test_beatnet_node_import_error_fallback(self, mock_import):
        """測試 BeatNet 未安裝 (ImportError) 時精確回傳 NodeStatus.FAILURE"""
        orig_import = __import__
        def side_effect(name, *args, **kwargs):
            if name == 'BeatNet' or name.startswith('BeatNet'):
                raise ImportError("No module named 'BeatNet'")
            return orig_import(name, *args, **kwargs)
        
        mock_import.side_effect = side_effect
        node = BeatNetNode()
        status = node.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.FAILURE)
        self.assertIsNone(self.blackboard.get_val("beats"))

    @patch('pgm_craft.workflow.audio_nodes.BeatNetNode.execute')
    def test_beatnet_fallback_integration(self, mock_beatnet_exec):
        """測試 BeatNet 失敗時，FallbackNode 成功觸發 LibrosaBeatNode"""
        mock_beatnet_exec.return_value = NodeStatus.FAILURE
        
        fallback_tree = FallbackNode("BeatNetFallback", [BeatNetNode(), LibrosaBeatNode()])
        status = fallback_tree.execute(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        beats = self.blackboard.get_val("beats")
        self.assertIsNotNone(beats)
        self.assertGreater(len(beats), 0)

if __name__ == '__main__':
    unittest.main()
