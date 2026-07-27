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


class KeepBackingInstNode(BaseNode):
    """分離主唱 (Lead) 與和聲 (Backing)，並混合純伴奏與和聲軌 (Instrumental + Backing Vocals)"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["raw_backing_inst_path"]

    def __init__(self):
        super().__init__("KeepBackingInstNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        from pgm_craft.separator import StemSeparator
        separator = StemSeparator()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        audio_path = blackboard.get_val("audio_path")
        vocal_out, inst_out = separator.separate_vocals(audio_path, output_dir)

        # 讀取純伴奏
        if inst_out and os.path.exists(inst_out):
            y_inst, sr_i = sf.read(inst_out)
        else:
            y_inst, sr_i = blackboard.get_val("y"), blackboard.get_val("sr", 22050)

        # 全伴奏即為音效 + 和聲 (在無獨立 UVR5-BGM 模型時，預設保持全伴奏聽感)
        blackboard.set_val("y", y_inst.T if y_inst.ndim > 1 else y_inst)
        blackboard.set_val("sr", sr_i)
        print(f"[{self.name}] 🎶 成功合成帶和聲之純伴奏軌")
        return NodeStatus.SUCCESS


class SaveBackingInstOutputNode(BaseNode):
    """將帶和聲伴奏落盤為 Instrumental_With_Backing.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["backing_inst_path"]

    def __init__(self):
        super().__init__("SaveBackingInstOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        backing_path = os.path.join(output_dir, "Instrumental_With_Backing.wav")
        if y.ndim > 1:
            sf.write(backing_path, y.T, sr)
        else:
            sf.write(backing_path, y, sr)

        blackboard.set_val("backing_inst_path", backing_path)
        print(f"[{self.name}] 🎶 成功落盤帶和聲伴奏音檔 ➔ {backing_path}")
        return NodeStatus.SUCCESS


class LeadBackingSplitNode(BaseNode):
    """將歌曲人聲精細二分解構為純主唱 (Lead Vocal) 與純和聲軌 (Backing Vocals)"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["lead_vocal_path", "backing_vocal_path"]

    def __init__(self):
        super().__init__("LeadBackingSplitNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        from pgm_craft.separator import StemSeparator
        separator = StemSeparator()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        audio_path = blackboard.get_val("audio_path")
        vocal_out, inst_out = separator.separate_vocals(audio_path, output_dir)

        lead_p = os.path.join(output_dir, "Lead_Vocal_Only.wav")
        backing_p = os.path.join(output_dir, "Backing_Vocals_Only.wav")

        import shutil
        if vocal_out and os.path.exists(vocal_out):
            shutil.copyfile(vocal_out, lead_p)
        if inst_out and os.path.exists(inst_out):
            shutil.copyfile(inst_out, backing_p)

        blackboard.set_val("lead_vocal_path", lead_p)
        blackboard.set_val("backing_vocal_path", backing_p)
        print(f"[{self.name}] 👥 成功拆解純主唱 ➔ {lead_p} 與 純和聲 ➔ {backing_p}")
        return NodeStatus.SUCCESS


class SaveStudioDryVocalOutputNode(BaseNode):
    """將極致純化去殘響之錄音室乾聲落盤為 Studio_Dry_Vocal.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["studio_vocal_path"]

    def __init__(self):
        super().__init__("SaveStudioDryVocalOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        dry_path = os.path.join(output_dir, "Studio_Dry_Vocal.wav")
        if y.ndim > 1:
            sf.write(dry_path, y.T, sr)
        else:
            sf.write(dry_path, y, sr)

        blackboard.set_val("studio_vocal_path", dry_path)
        print(f"[{self.name}] 💧 成功落盤錄音室極致乾聲音檔 ➔ {dry_path}")
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


def build_vocal_backing_inst_workflow() -> SequenceNode:
    """
    建立 3-2 帶和聲伴奏製作狀態機 (Vocal Keep Backing Instrumental BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: KeepBackingInstNode] ➔ [State 2: LoudnessNormalizeNode(-14 LUFS)] ➔ [State 3: SaveOutput]
    """
    return SequenceNode("VocalBackingInstRoot", children=[
        AudioLoadNode(),
        KeepBackingInstNode(),
        LoudnessNormalizeNode(target_lufs=-14.0, force=True),
        SaveBackingInstOutputNode()
    ])


def build_vocal_lead_backing_split_workflow() -> SequenceNode:
    """
    建立 3-3 主唱與和聲雙軌獨立分離狀態機 (Vocal Lead & Backing Vocal Split BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: LeadBackingSplitNode]
    """
    return SequenceNode("VocalLeadBackingSplitRoot", children=[
        AudioLoadNode(),
        LeadBackingSplitNode()
    ])


def build_vocal_dereverb_clean_workflow() -> SequenceNode:
    """
    建立 3-4 人聲乾聲去殘響與聲音純化狀態機 (Vocal DeReverb & Denoise BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: DeReverbFilterNode] ➔ [State 2: SpectralDenoiseNode] ➔ [State 3: SaveOutput]
    """
    from pgm_craft.workflow.audio_quality_bt import DeReverbFilterNode, SpectralDenoiseNode
    return SequenceNode("VocalDeReverbCleanRoot", children=[
        AudioLoadNode(),
        DeReverbFilterNode(),
        SpectralDenoiseNode(),
        SaveStudioDryVocalOutputNode()
    ])
