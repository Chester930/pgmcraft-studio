import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode
from pgm_craft.workflow.audio_nodes import KeyChordAnalysisNode, SectionStructureNode, MeasureMapNode
from pgm_craft.analyzer import MusicAnalyzer


def _to_mono(y):
    if y.ndim > 1:
        return y.mean(axis=1)
    return y


class SynthesizeHarmonicTrackNode(BaseNode):
    """
    Stage 4 和聲音軌準備：
    優先合成 (Piano + Guitar + Bass) 作為零鼓噪聲、零人聲干擾的和聲 Sub-mix 音軌 (`harmonic_track_path`)
    若個別音軌缺失，降級採用 `stems/no_vocals.wav` (高通濾波) 或 `denoised_wav_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "harmonic_submix", "denoised_wav_path"]
    output_keys = ["harmonic_track_path"]

    def __init__(self):
        super().__init__("SynthesizeHarmonicTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        harmonic_submix = blackboard.get_val("harmonic_submix", "")
        denoised_wav_path = blackboard.get_val("denoised_wav_path", "")

        piano_path = stems.get("piano") or stems.get("pianos")
        guitar_path = stems.get("guitar") or stems.get("guitars")
        bass_path = stems.get("bass") or stems.get("basses")

        # 檢視資料夾路徑補全
        if stems_dir:
            if not piano_path:
                pp = os.path.join(stems_dir, "pianos", "piano.wav")
                if os.path.exists(pp): piano_path = pp
            if not guitar_path:
                gp = os.path.join(stems_dir, "guitars", "guitar.wav")
                if os.path.exists(gp): guitar_path = gp
            if not bass_path:
                bp = os.path.join(stems_dir, "bass", "bass.wav")
                if os.path.exists(bp): bass_path = bp

        submix_dir = os.path.join(stems_dir, "submix") if stems_dir else os.path.dirname(audio_path)
        os.makedirs(submix_dir, exist_ok=True)
        harmonic_out = os.path.join(submix_dir, "track_stage4_harmonic.wav")

        mix_tracks = []
        try:
            for p in [piano_path, guitar_path, bass_path]:
                if p and os.path.exists(p):
                    y_t, sr_t = sf.read(p)
                    mix_tracks.append((_to_mono(y_t), sr_t))

            if mix_tracks:
                min_l = min(len(t[0]) for t in mix_tracks)
                sr_0 = mix_tracks[0][1]
                y_harm = sum(t[0][:min_l] for t in mix_tracks) * (1.0 / len(mix_tracks))
                sf.write(harmonic_out, y_harm.astype(np.float32), sr_0)
                blackboard.set_val("harmonic_track_path", harmonic_out)
                blackboard.set_val("harmonic_submix", harmonic_out)
                print(f"[{self.name}] ✅ 成功合成 Stage 4 和聲專屬 Sub-mix (Piano+Guitar+Bass): {harmonic_out}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 和聲 Sub-mix 合成異常: {e}")

        # 降級路徑
        fallback_target = None
        if stems_dir:
            no_voc = os.path.join(stems_dir, "no_vocals.wav")
            inst_wav = os.path.join(stems_dir, "instrumental.wav")
            if os.path.exists(no_voc):
                fallback_target = no_voc
            elif os.path.exists(inst_wav):
                fallback_target = inst_wav

        if not fallback_target:
            fallback_target = harmonic_submix or denoised_wav_path or audio_path

        blackboard.set_val("harmonic_track_path", fallback_target)
        blackboard.set_val("harmonic_submix", fallback_target)
        print(f"[{self.name}] ℹ️ 降級使用 {fallback_target} 作為和聲分析音軌。")
        return NodeStatus.SUCCESS


class SynthesizeStructureTrackNode(BaseNode):
    """
    Stage 4 樂段結構音軌準備：
    優先合成 (Vocals + Drums + Other/No_Vocals) 作為包含完整巨觀架構與動態能量的樂段結構 Sub-mix 音軌 (`structure_track_path`)
    若個別音軌缺失，降級採用 `denoised_wav_path` 或 `audio_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "structure_submix", "denoised_wav_path"]
    output_keys = ["structure_track_path"]

    def __init__(self):
        super().__init__("SynthesizeStructureTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        structure_submix = blackboard.get_val("structure_submix", "")
        denoised_wav_path = blackboard.get_val("denoised_wav_path", "")

        vocals_path = stems.get("vocals")
        drums_path = stems.get("drums")
        other_path = stems.get("other") or stems.get("instrumental")

        if stems_dir:
            if not vocals_path:
                vp = os.path.join(stems_dir, "vocals", "vocals.wav")
                if os.path.exists(vp): vocals_path = vp
            if not drums_path:
                dp = os.path.join(stems_dir, "drums", "drums.wav")
                if os.path.exists(dp): drums_path = dp
            if not other_path:
                nv = os.path.join(stems_dir, "no_vocals.wav")
                if os.path.exists(nv): other_path = nv

        submix_dir = os.path.join(stems_dir, "submix") if stems_dir else os.path.dirname(audio_path)
        os.makedirs(submix_dir, exist_ok=True)
        structure_out = os.path.join(submix_dir, "track_stage4_structure.wav")

        mix_tracks = []
        try:
            for p in [vocals_path, drums_path, other_path]:
                if p and os.path.exists(p):
                    y_t, sr_t = sf.read(p)
                    mix_tracks.append((_to_mono(y_t), sr_t))

            if mix_tracks:
                min_l = min(len(t[0]) for t in mix_tracks)
                sr_0 = mix_tracks[0][1]
                y_struct = sum(t[0][:min_l] for t in mix_tracks) * (1.0 / len(mix_tracks))
                sf.write(structure_out, y_struct.astype(np.float32), sr_0)
                blackboard.set_val("structure_track_path", structure_out)
                blackboard.set_val("structure_submix", structure_out)
                print(f"[{self.name}] ✅ 成功合成 Stage 4 樂段結構專屬 Sub-mix (Vocals+Drums+Other): {structure_out}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 樂段結構 Sub-mix 合成異常: {e}")

        fallback_target = structure_submix or denoised_wav_path or audio_path
        blackboard.set_val("structure_track_path", fallback_target)
        blackboard.set_val("structure_submix", fallback_target)
        print(f"[{self.name}] ℹ️ 降級使用 {fallback_target} 作為樂段結構分析音軌。")
        return NodeStatus.SUCCESS



def build_music_analysis_tree() -> SequenceNode:
    """
    建立 Stage 4 樂曲與和聲分析 Behavior Tree
    """
    return SequenceNode("MusicAnalysisRoot", [
        SynthesizeHarmonicTrackNode(),
        KeyChordAnalysisNode(),
        SynthesizeStructureTrackNode(),
        SectionStructureNode(),
        MeasureMapNode()
    ])


class MusicAnalysisBTEngine:
    """Stage 4 Music Analysis BT Engine wrapper."""

    def __init__(self):
        self.tree = build_music_analysis_tree()

    def run(self, blackboard: Blackboard) -> Blackboard:
        print("\n=== [MusicAnalysisBT] Stage 4 Start ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("music_analysis_status", status.name)
        if status == NodeStatus.SUCCESS:
            key = blackboard.get_val("estimated_key", "Unknown")
            chords = blackboard.get_val("chord_progression", [])
            print(f"=== [MusicAnalysisBT] Stage 4 Done key={key}, chords_count={len(chords)} ===")
        else:
            print("=== [MusicAnalysisBT] Stage 4 FAILED ===")
        return blackboard
