"""
PGMCraft Vocal & Karaoke Domain Behavior Tree Workflows.
Implements State Machine Workflows for Vocal Removal, Harmony Isolation & Voice Purification.
"""

import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode, Blackboard
from pgm_craft.workflow.audio_nodes import AudioLoadNode
from pgm_craft.workflow.audio_quality_bt import LoudnessNormalizeNode


class PureInstrumentalNode(BaseNode):
    """使用 BS-Roformer 演算法高精度分離人聲，產出極致純伴奏"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["raw_inst_path"]

    def __init__(self):
        super().__init__("PureInstrumentalNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        from pgm_craft.separator import StemSeparator
        separator = StemSeparator()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        audio_path = blackboard.get_val("audio_path")
        vocal_out, inst_out = separator.separate_vocals(audio_path, output_dir)

        if inst_out and os.path.exists(inst_out):
            # 讀取純伴奏音訊波形更新至黑板
            y_inst, sr_i = sf.read(inst_out)
            blackboard.set_val("y", y_inst.T if y_inst.ndim > 1 else y_inst)
            blackboard.set_val("sr", sr_i)
            blackboard.set_val("raw_inst_path", inst_out)
            print(f"[{self.name}] 🎤 成功提取純伴奏軌 ➔ {inst_out}")
            return NodeStatus.SUCCESS
        else:
            print(f"[{self.name}] ❌ 人聲分離提取失敗！")
            return NodeStatus.FAILURE


class SavePureInstOutputNode(BaseNode):
    """將完成響度標準化的純伴奏落盤為 Pure_Instrumental.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["pure_inst_path"]

    def __init__(self):
        super().__init__("SavePureInstOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        pure_path = os.path.join(output_dir, "Pure_Instrumental.wav")
        if y.ndim > 1:
            sf.write(pure_path, y.T, sr)
        else:
            sf.write(pure_path, y, sr)

        blackboard.set_val("pure_inst_path", pure_path)
        print(f"[{self.name}] 🎤 成功落盤經典純伴奏音檔 ➔ {pure_path}")
        return NodeStatus.SUCCESS


def build_vocal_pure_inst_workflow() -> SequenceNode:
    """
    建立 3-1 經典純伴奏製作狀態機 (Vocal Pure Instrumental BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: PureInstrumentalNode] ➔ [State 2: LoudnessNormalizeNode(-14 LUFS)] ➔ [State 3: SaveOutput]
    """
    return SequenceNode("VocalPureInstRoot", children=[
        AudioLoadNode(),
        PureInstrumentalNode(),
        LoudnessNormalizeNode(target_lufs=-14.0, force=True),
        SavePureInstOutputNode()
    ])
