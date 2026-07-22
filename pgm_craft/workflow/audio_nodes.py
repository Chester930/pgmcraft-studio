"""
PGMCraft Concrete Audio Processing Behavior Tree Nodes.
Includes Video URL Download, Audio Load, Multi-pass Cascaded Demucs Separation, Beat Tracking, and Export.
"""

import os
import re
import numpy as np
import librosa
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.workflow.downloaders import URLDownloaderDispatcher
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.synthesizer import PGMSynthesizer


class VideoURLDownloadNode(BaseNode):
    """
    下載線上影片 URL (YouTube/Bilibili/Niconico/直連音檔 等) 節點。
    透過 URLDownloaderDispatcher 分發至專屬的下載策略 (Strategy Pattern)。
    """
    def __init__(self):
        super().__init__("VideoURLDownloadNode")
        self.dispatcher = URLDownloaderDispatcher()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        input_source = blackboard.get_val("audio_path")
        
        if not input_source or not re.match(r'^https?://', input_source.strip()):
            print(f"[BT Node: {self.name}] Input is a local file path. Skipping download.")
            return NodeStatus.SUCCESS

        url = input_source.strip()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        print(f"[BT Node: {self.name}] Dispatching download strategy for: {url}")

        try:
            res = self.dispatcher.dispatch_and_download(url, output_dir)
            wav_path = res.get("wav")
            mp4_path = res.get("mp4")

            if wav_path and os.path.exists(wav_path):
                blackboard.set_val("audio_path", wav_path)
                blackboard.set_val("downloaded_video_path", mp4_path if (mp4_path and os.path.exists(mp4_path)) else None)
                print(f"[BT Node: {self.name}] Lossless WAV ready: {wav_path}")
                return NodeStatus.SUCCESS

        except Exception as e:
            print(f"[BT Node: {self.name}] Download dispatcher failed: {e}")
            return NodeStatus.FAILURE

        return NodeStatus.FAILURE


class AudioLoadNode(BaseNode):
    def __init__(self):
        super().__init__("AudioLoadNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            print(f"[BT Node: {self.name}] Audio file not found: {audio_path}")
            return NodeStatus.FAILURE
        
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)
        blackboard.set_val("target_analysis_path", audio_path)
        print(f"[BT Node: {self.name}] Loaded audio successfully ({len(y)/sr:.2f}s).")
        return NodeStatus.SUCCESS


class DemucsStemNode(BaseNode):
    """多階層遞迴剝離分軌節點 (Multi-pass Cascaded Demixing Node)"""
    def __init__(self):
        super().__init__("DemucsStemNode")
        self.separator = CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not blackboard.get_val("enable_stem", False):
            print(f"[BT Node: {self.name}] Stem separation disabled by user. Skipping.")
            return NodeStatus.SUCCESS

        audio_path = blackboard.get_val("audio_path")
        output_dir = blackboard.get_val("output_dir", "outputs")
        steps = blackboard.get_val("demix_steps", ['vocals', 'drums', 'bass'])
        
        print(f"[BT Node: {self.name}] Running Multi-pass Cascaded Demixing: {steps}")
        stems = self.separator.run_cascaded_demixing(audio_path, steps=steps, output_dir=os.path.join(output_dir, "stems"))
        blackboard.set_val("stems", stems)
        
        if 'drums' in stems and os.path.exists(stems['drums']):
            blackboard.set_val("target_analysis_path", stems['drums'])
            print(f"[BT Node: {self.name}] Using isolated drums.wav for high-precision beat tracking.")
        return NodeStatus.SUCCESS


class BeatNetNode(BaseNode):
    def __init__(self):
        super().__init__("BeatNetNode")
        self.analyzer = MusicAnalyzer(use_beatnet=True)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val("target_analysis_path")
        try:
            from BeatNet.BeatNet import BeatNet
            estimator = BeatNet(1, mode='offline', inference_model='dbn', plot=[], thread=False)
            output = estimator.process(target_path)
            if output is not None and len(output) > 0:
                blackboard.set_val("beats", output)
                print(f"[BT Node: {self.name}] Tracked {len(output)} beats via BeatNet CRNN.")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[BT Node: {self.name}] BeatNet failed or unavailable: {e}")
        return NodeStatus.FAILURE


class LibrosaBeatNode(BaseNode):
    def __init__(self):
        super().__init__("LibrosaBeatNode")
        self.analyzer = MusicAnalyzer(use_beatnet=False)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val("target_analysis_path")
        print(f"[BT Node: {self.name}] Running Librosa fallback beat tracking...")
        beats = self.analyzer._librosa_fallback(target_path)
        blackboard.set_val("beats", beats)
        return NodeStatus.SUCCESS


class KeyChordAnalysisNode(BaseNode):
    def __init__(self):
        super().__init__("KeyChordAnalysisNode")
        self.analyzer = MusicAnalyzer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        beats = blackboard.get_val("beats")

        estimated_key = self.analyzer.analyze_key(audio_path)
        chords = self.analyzer.analyze_chords(audio_path, beats)

        blackboard.set_val("estimated_key", estimated_key)
        blackboard.set_val("chord_progression", chords)
        print(f"[BT Node: {self.name}] Key: {estimated_key}, Measures: {len(chords)}")
        return NodeStatus.SUCCESS


class ClickSynthesisNode(BaseNode):
    def __init__(self):
        super().__init__("ClickSynthesisNode")
        self.synthesizer = PGMSynthesizer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        beats = blackboard.get_val("beats")
        output_dir = blackboard.get_val("output_dir", "outputs")

        click_path, mix_path = self.synthesizer.synthesize_click(audio_path, beats, output_dir=output_dir)
        blackboard.set_val("click_track", click_path)
        blackboard.set_val("mix_with_click", mix_path)
        print(f"[BT Node: {self.name}] Synthesized click WAV & mixed audio.")
        return NodeStatus.SUCCESS


class MIDIExportNode(BaseNode):
    def __init__(self):
        super().__init__("MIDIExportNode")
        self.synthesizer = PGMSynthesizer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        output_dir = blackboard.get_val("output_dir", "outputs")

        tempo_map_path = self.synthesizer.export_midi_tempo_map(beats, output_dir=output_dir)
        click_guide_path = self.synthesizer.export_midi_click_guide(beats, output_dir=output_dir)
        blackboard.set_val("tempo_map_midi", tempo_map_path)
        blackboard.set_val("click_guide_midi", click_guide_path)
        print(f"[BT Node: {self.name}] Exported MIDI Tempo Map to {tempo_map_path}.")
        print(f"[BT Node: {self.name}] Exported MIDI Click Guide to {click_guide_path}.")
        return NodeStatus.SUCCESS
