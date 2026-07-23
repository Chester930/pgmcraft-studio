"""
PGMCraft Studio v2.0 官方範例 BT 節點插件：人聲頻譜增強器 (DemoVocalEnhancerNode)
此檔案供開發者參考，展示如何無侵入式擴充客製化 Behavior Tree 音訊節點。
"""

from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard

class DemoVocalEnhancerNode(BaseNode):
    """官方範例插件：動態音訊頻譜增強與噪聲抑制預處理節點。"""
    
    required_keys = ["y", "sr"]
    output_keys = ["vocal_enhanced_status"]

    def __init__(self):
        super().__init__("DemoVocalEnhancerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        
        if y is None or len(y) == 0:
            print(f"[BT Plugin Node: {self.name}] Audio signal empty. Skipping enhancement.")
            return NodeStatus.FAILURE

        print(f"[BT Plugin Node: {self.name}] Executing vocal spectrum enhancement (sr={sr})...")
        blackboard.set_val("vocal_enhanced_status", True)
        return NodeStatus.SUCCESS
