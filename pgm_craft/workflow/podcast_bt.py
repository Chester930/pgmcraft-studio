"""
PGMCraft Podcast Domain Behavior Tree Workflows.
Implements State Machine Workflows for Podcast & Speech Production.
"""

import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode, Blackboard
from pgm_craft.workflow.audio_nodes import AudioLoadNode
from pgm_craft.workflow.audio_quality_bt import (
    DeHumFilterNode,
    SpectralDenoiseNode,
    DeReverbFilterNode,
    LoudnessNormalizeNode
)


class SaveInterviewCleanOutputNode(BaseNode):
    """將訪談淨化狀態機成果落盤為 interview_clean_speech.wav 與 noise_report.json"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["clean_speech_path"]

    def __init__(self):
        super().__init__("SaveInterviewCleanOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        clean_path = os.path.join(output_dir, "interview_clean_speech.wav")
        # 轉存聲音資料 (並確認單/雙聲道 shape)
        if y.ndim > 1:
            sf.write(clean_path, y.T, sr)
        else:
            sf.write(clean_path, y, sr)

        blackboard.set_val("clean_speech_path", clean_path)
        print(f"[{self.name}] 🎙️ 成功落盤雙人/多人訪談淨化音檔 ➔ {clean_path}")
        return NodeStatus.SUCCESS


class SaveMasteredOutputNode(BaseNode):
    """將播客 EBU R128 Master 成果落盤為 podcast_mastered_-16lufs.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["mastered_speech_path"]

    def __init__(self):
        super().__init__("SaveMasteredOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        master_path = os.path.join(output_dir, "podcast_mastered_-16lufs.wav")
        if y.ndim > 1:
            sf.write(master_path, y.T, sr)
        else:
            sf.write(master_path, y, sr)

        blackboard.set_val("mastered_speech_path", master_path)
        print(f"[{self.name}] 🔊 成功落盤 Podcast Master 音量標準化檔 ➔ {master_path}")
        return NodeStatus.SUCCESS


def build_interview_clean_workflow() -> SequenceNode:
    """
    建立 1-1 雙人/多人訪談聲音淨化狀態機 (Interview Clean BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: DeHumFilterNode] ➔ [State 2: SpectralDenoiseNode] ➔ [State 3: DeReverbFilterNode] ➔ [State 4: LoudnessNormalizeNode] ➔ [State 5: SaveOutput]
    """
    return SequenceNode("InterviewCleanRoot", children=[
        AudioLoadNode(),
        DeHumFilterNode(),
        SpectralDenoiseNode(),
        DeReverbFilterNode(),
        LoudnessNormalizeNode(target_lufs=-16.0, force=True),
        SaveInterviewCleanOutputNode()
    ])


def build_podcast_r128_normalize_workflow() -> SequenceNode:
    """
    建立 1-2 播客音量 EBU R128 自動標準化與防剪峰狀態機 (Podcast Loudness Normalizer BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: LoudnessNormalizeNode(-16 LUFS)] ➔ [State 2: SaveMasteredOutputNode]
    """
    return SequenceNode("PodcastR128NormalizeRoot", children=[
        AudioLoadNode(),
        LoudnessNormalizeNode(target_lufs=-16.0, force=True),
        SaveMasteredOutputNode()
    ])
