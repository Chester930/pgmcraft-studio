"""
PGMCraft Vlog Domain Behavior Tree Workflows.
Implements State Machine Workflows for Vlogging, Video Editing & Content Creation.
"""

import os
import soundfile as sf
import numpy as np
from scipy import signal
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode, Blackboard
from pgm_craft.workflow.audio_nodes import AudioLoadNode
from pgm_craft.workflow.audio_quality_bt import (
    SpectralDenoiseNode,
    LoudnessNormalizeNode
)


class WindCutFilterNode(BaseNode):
    """80Hz 三階 Butterworth 高通濾波，專門消除 < 80Hz 低頻風切氣流爆音 (Wind Popping & Rumble)"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self, cutoff_hz: float = 80.0):
        super().__init__("WindCutFilterNode")
        self.cutoff_hz = cutoff_hz

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)

        try:
            sos = signal.butter(3, self.cutoff_hz, btype='highpass', fs=sr, output='sos')
            if y.ndim > 1:
                y_filtered = np.zeros_like(y)
                for c in range(y.shape[0]):
                    y_filtered[c] = signal.sosfilt(sos, y[c])
            else:
                y_filtered = signal.sosfilt(sos, y)

            blackboard.set_val("y", y_filtered.astype(np.float32))
            print(f"[{self.name}] 🌪️ 成功消除 < {self.cutoff_hz}Hz 低頻風切震盪氣流聲")
        except Exception as e:
            print(f"[{self.name}] ⚠️ 風切濾波警告: {e}")

        return NodeStatus.SUCCESS


class SaveVlogWindCleanOutputNode(BaseNode):
    """將 Vlog 風切淨化成果落盤為 vlog_wind_cleaned.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["vlog_clean_path"]

    def __init__(self):
        super().__init__("SaveVlogWindCleanOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        vlog_path = os.path.join(output_dir, "vlog_wind_cleaned.wav")
        if y.ndim > 1:
            sf.write(vlog_path, y.T, sr)
        else:
            sf.write(vlog_path, y, sr)

        blackboard.set_val("vlog_clean_path", vlog_path)
        print(f"[{self.name}] 📹 成功落盤 Vlog 風切淨化音檔 ➔ {vlog_path}")
        return NodeStatus.SUCCESS


class DialogueBGMSplitNode(BaseNode):
    """將影片人物對白 (Dialogue) 與背景音樂 (BGM) 二分抽離並落盤"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["isolated_dialogue_path", "isolated_bgm_path"]

    def __init__(self):
        super().__init__("DialogueBGMSplitNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        from pgm_craft.separator import StemSeparator
        separator = StemSeparator()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        audio_path = blackboard.get_val("audio_path")
        vocal_out, inst_out = separator.separate_vocals(audio_path, output_dir)

        dialogue_p = os.path.join(output_dir, "Vlog_Dialogue_Only.wav")
        bgm_p = os.path.join(output_dir, "Vlog_Clean_BGM.wav")

        import shutil
        if vocal_out and os.path.exists(vocal_out):
            shutil.copyfile(vocal_out, dialogue_p)
        if inst_out and os.path.exists(inst_out):
            shutil.copyfile(inst_out, bgm_p)

        blackboard.set_val("isolated_dialogue_path", dialogue_p)
        blackboard.set_val("isolated_bgm_path", bgm_p)
        print(f"[{self.name}] 🎬 成功抽離 Vlog 對白 ➔ {dialogue_p} 與 背景 BGM ➔ {bgm_p}")
        return NodeStatus.SUCCESS


def build_vlog_wind_env_clean_workflow() -> SequenceNode:
    """
    建立 2-1 戶外外景低頻風切聲與車流雜音降噪狀態機 (Vlog Wind & Env Clean BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: WindCutFilterNode(80Hz)] ➔ [State 2: SpectralDenoiseNode] ➔ [State 3: LoudnessNormalizeNode(-14 LUFS)] ➔ [State 4: SaveOutput]
    """
    return SequenceNode("VlogWindCleanRoot", children=[
        AudioLoadNode(),
        WindCutFilterNode(cutoff_hz=80.0),
        SpectralDenoiseNode(),
        LoudnessNormalizeNode(target_lufs=-14.0, force=True),
        SaveVlogWindCleanOutputNode()
    ])


def build_vlog_dialogue_bgm_split_workflow() -> SequenceNode:
    """
    建立 2-2 影片對白與背景音樂 (BGM) 二分抽離狀態機 (Vlog Dialogue & BGM Split BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: DialogueBGMSplitNode]
    """
    return SequenceNode("VlogDialogueBGMSplitRoot", children=[
        AudioLoadNode(),
        DialogueBGMSplitNode()
    ])
