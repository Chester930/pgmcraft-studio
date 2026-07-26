import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode, FallbackNode
from pgm_craft.analyzer import MusicAnalyzer


def _to_mono(y):
    if y.ndim > 1:
        return y.mean(axis=1)
    return y


class SynthesizeRhythmTrackNode(BaseNode):
    """
    A 軌音訊準備：合成 Drums + Bass 作為節奏骨幹軌 (`rhythm_track_path`)
    如果鼓或貝斯缺失，降級使用已有的 `rhythm_submix` 或 `audio_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "rhythm_submix"]
    output_keys = ["rhythm_track_path"]

    def __init__(self):
        super().__init__("SynthesizeRhythmTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        rhythm_submix = blackboard.get_val("rhythm_submix", "")

        drums_path = stems.get("drums")
        bass_path = stems.get("bass")

        # 若 stems 字典沒拿著，嘗試直接看資料夾
        if not drums_path and stems_dir:
            dp = os.path.join(stems_dir, "drums", "drums.wav")
            if os.path.exists(dp): drums_path = dp
        if not bass_path and stems_dir:
            bp = os.path.join(stems_dir, "bass", "bass.wav")
            if os.path.exists(bp): bass_path = bp

        submix_dir = os.path.join(stems_dir, "submix") if stems_dir else os.path.dirname(audio_path)
        os.makedirs(submix_dir, exist_ok=True)
        rhythm_out = os.path.join(submix_dir, "track_a_rhythm.wav")

        try:
            if drums_path and bass_path and os.path.exists(drums_path) and os.path.exists(bass_path):
                y_d, sr_d = sf.read(drums_path)
                y_b, sr_b = sf.read(bass_path)
                y_d_m, y_b_m = _to_mono(y_d), _to_mono(y_b)
                min_l = min(len(y_d_m), len(y_b_m))
                y_mix = (y_d_m[:min_l] + y_b_m[:min_l]) * 0.5
                sf.write(rhythm_out, y_mix.astype(np.float32), sr_d)
                blackboard.set_val("rhythm_track_path", rhythm_out)
                print(f"[{self.name}] ✅ 成功合成 A 軌 (Drums + Bass) 節奏骨幹軌: {rhythm_out}")
                return NodeStatus.SUCCESS
            elif drums_path and os.path.exists(drums_path):
                blackboard.set_val("rhythm_track_path", drums_path)
                print(f"[{self.name}] ℹ️ 僅有鼓軌，設定 A 軌為: {drums_path}")
                return NodeStatus.SUCCESS
            elif rhythm_submix and os.path.exists(rhythm_submix):
                blackboard.set_val("rhythm_track_path", rhythm_submix)
                print(f"[{self.name}] ℹ️ 降級使用 rhythm_submix 為 A 軌: {rhythm_submix}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] A 軌合成過程異常: {e}")

        fallback_path = audio_path or rhythm_submix
        blackboard.set_val("rhythm_track_path", fallback_path)
        print(f"[{self.name}] 最終 Fallback 使用: {fallback_path}")
        return NodeStatus.SUCCESS


class PrepareInstrumentalTrackNode(BaseNode):
    """
    B 軌音訊準備：提取 no_vocals.wav 或 instrumental.wav 作為全音軌伴奏軌 (`inst_track_path`)
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path"]
    output_keys = ["inst_track_path"]

    def __init__(self):
        super().__init__("PrepareInstrumentalTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")

        candidate_inst = None
        if stems_dir:
            no_voc = os.path.join(stems_dir, "no_vocals.wav")
            inst_wav = os.path.join(stems_dir, "instrumental.wav")
            if os.path.exists(no_voc):
                candidate_inst = no_voc
            elif os.path.exists(inst_wav):
                candidate_inst = inst_wav

        if not candidate_inst:
            stems = blackboard.get_val("stems", {})
            candidate_inst = stems.get("instrumental") or audio_path

        blackboard.set_val("inst_track_path", candidate_inst)
        print(f"[{self.name}] ✅ 設定 B 軌 (伴奏軌) 為: {candidate_inst}")
        return NodeStatus.SUCCESS


class BeatNetSingleTrackNode(BaseNode):
    """通用單軌 BeatNet 節拍分析節點"""

    def __init__(self, input_key: str, beats_key: str, node_name: str = "BeatNetSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val(self.input_key)
        if not target_path or not os.path.exists(target_path):
            print(f"[{self.name}] target_path empty or not exists ({target_path})")
            return NodeStatus.FAILURE

        try:
            from BeatNet.BeatNet import BeatNet
            estimator = BeatNet(1, mode='offline', inference_model='DBN', plot=[], thread=False)
            output = estimator.process(target_path)
            if output is not None and len(output) > 0:
                blackboard.set_val(self.beats_key, output)
                print(f"[{self.name}] Tracked {len(output)} beats via BeatNet DBN.")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name}] BeatNet failed: {e}")

        return NodeStatus.FAILURE


class LibrosaSingleTrackNode(BaseNode):
    """通用單軌 Librosa Fallback 節拍分析節點"""

    def __init__(self, input_key: str, beats_key: str, node_name: str = "LibrosaSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key
        self.analyzer = MusicAnalyzer(use_beatnet=False)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val(self.input_key)
        if not target_path or not os.path.exists(target_path):
            return NodeStatus.FAILURE

        print(f"[{self.name}] Running Librosa fallback beat tracking on {target_path}...")
        beats = self.analyzer._librosa_fallback(target_path)
        blackboard.set_val(self.beats_key, beats)
        return NodeStatus.SUCCESS


class TrackValidationNode(BaseNode):
    """對特定單軌節拍進行品質指標與 Confidence 分數計算」"""

    def __init__(self, beats_key: str, conf_key: str, node_name: str = "TrackValidationNode"):
        super().__init__(node_name)
        self.beats_key = beats_key
        self.conf_key = conf_key

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val(self.beats_key)
        if beats is None or len(beats) < 4:
            blackboard.set_val(self.conf_key, 0.0)
            return NodeStatus.SUCCESS

        timestamps = beats[:, 0].astype(float)
        intervals = np.diff(timestamps)
        if len(intervals) == 0 or np.any(intervals <= 0):
            blackboard.set_val(self.conf_key, 0.0)
            return NodeStatus.SUCCESS

        bpms = 60.0 / intervals
        bpm_std = float(np.std(bpms))
        mean_bpm = float(np.mean(bpms))

        # 計算信心分數：穩定度高的標準差越小、BPM在常態 50-200 之間得分高
        stability_score = max(0.0, 1.0 - (bpm_std / (mean_bpm + 1e-6)))
        has_downbeats = bool(np.any(beats[:, 1] == 1))
        downbeat_bonus = 0.2 if has_downbeats else 0.0

        confidence = float(np.clip(stability_score + downbeat_bonus, 0.1, 1.0))
        blackboard.set_val(self.conf_key, confidence)
        print(f"[{self.name}] Track ({self.beats_key}) confidence score: {confidence:.2f}")
        return NodeStatus.SUCCESS


class BeatFusionArbitratorNode(BaseNode):
    """
    【雙軌融合仲裁衛兵】
    - 動態切割 A 軌 (Drums+Bass) 與 B 軌 (Instrumental) 能量段落
    - 當 A 軌在該段落能量強時，使用 A 軌的高精度撞擊點
    - 當 A 軌在該段落（如無鼓 Intro/Breakdown）無能量時，動態接管 B 軌，確保 Click 全曲無斷拍
    - 對齊雙軌 Downbeat (小節 1 號拍) 標籤
    """
    required_keys = ["beats_rhythm", "beats_inst"]
    output_keys = ["beats", "fusion_report"]

    def __init__(self, energy_threshold: float = 0.02):
        super().__init__("BeatFusionArbitratorNode")
        self.energy_threshold = energy_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats_a = blackboard.get_val("beats_rhythm")
        beats_b = blackboard.get_val("beats_inst")
        conf_a = blackboard.get_val("conf_rhythm", 0.5)
        conf_b = blackboard.get_val("conf_inst", 0.5)
        rhythm_path = blackboard.get_val("rhythm_track_path")

        # 防呆降級：若某軌缺失直接拿另一軌
        if beats_a is None or len(beats_a) == 0:
            print(f"[{self.name}] ⚠️ A 軌節拍缺失，直接採用 B 軌。")
            blackboard.set_val("beats", beats_b)
            return NodeStatus.SUCCESS
        if beats_b is None or len(beats_b) == 0:
            print(f"[{self.name}] ⚠️ B 軌節拍缺失，直接採用 A 軌。")
            blackboard.set_val("beats", beats_a)
            return NodeStatus.SUCCESS

        try:
            # 讀取 A 軌短時能量
            y_rhythm, sr = sf.read(rhythm_path)
            y_rhythm = _to_mono(y_rhythm)
        except Exception as e:
            print(f"[{self.name} Warning] 無法讀取 A 軌音訊，改用信心度高者: {e}")
            selected_beats = beats_a if conf_a >= conf_b else beats_b
            blackboard.set_val("beats", selected_beats)
            return NodeStatus.SUCCESS

        # 融合計算
        fused_beats = []
        timestamps_a = beats_a[:, 0].astype(float)
        timestamps_b = beats_b[:, 0].astype(float)

        switched_to_b = 0
        used_a = 0

        # 以時間為主軸融合
        max_time = max(timestamps_a[-1], timestamps_b[-1])
        all_times = np.union1d(timestamps_a, timestamps_b)
        all_times = np.sort(all_times)

        # 簡單高保真融合演算法：以 A 軌的時間軸為基本骨架，在 A 軌能量過低時補入 B 軌
        final_beats_list = []
        for row in beats_a:
            t, label = float(row[0]), int(row[1])
            start_sample = int(max(0, (t - 0.1) * sr))
            end_sample = int(min(len(y_rhythm), (t + 0.1) * sr))
            segment_rms = np.sqrt(np.mean(y_rhythm[start_sample:end_sample] ** 2)) if end_sample > start_sample else 0.0

            if segment_rms < self.energy_threshold:
                # 鼓軌在此時間點靜音 (Intro/Breakdown)，從 B 軌中找最近的打點
                idx_b = np.argmin(np.abs(timestamps_b - t))
                if abs(timestamps_b[idx_b] - t) < 0.2:
                    t_b = float(beats_b[idx_b, 0])
                    label_b = int(beats_b[idx_b, 1])
                    final_beats_list.append([t_b, label_b])
                    switched_to_b += 1
                    continue
            final_beats_list.append([t, label])
            used_a += 1

        final_beats_arr = np.array(final_beats_list)
        blackboard.set_val("beats", final_beats_arr)

        report = {
            "used_track_a_count": used_a,
            "switched_to_track_b_count": switched_to_b,
            "conf_a": conf_a,
            "conf_b": conf_b,
            "total_fused_beats": len(final_beats_arr)
        }
        blackboard.set_val("beat_fusion_report", report)

        print(f"[{self.name}] 🎯 雙軌融合成功！主動採納 A 軌 (鼓+Bass): {used_a} 拍，無鼓段切換 B 軌補全: {switched_to_b} 拍。")
        return NodeStatus.SUCCESS


def build_beat_tracking_tree() -> SequenceNode:
    """
    建立 Stage 3 雙軌併行節拍分析與動態融合 Behavioral Tree
    """
    from pgm_craft.workflow.nodes import SequenceNode, FallbackNode
    from pgm_craft.workflow.audio_nodes import BeatValidationNode, DownbeatRefineNode

    # Track A Branch (Drums + Bass)
    track_a_branch = SequenceNode("TrackA_RhythmBranch", [
        FallbackNode("BeatNetFallbackA", [
            BeatNetSingleTrackNode(input_key="rhythm_track_path", beats_key="beats_rhythm", node_name="BeatNetNode_TrackA"),
            LibrosaSingleTrackNode(input_key="rhythm_track_path", beats_key="beats_rhythm", node_name="LibrosaBeatNode_TrackA")
        ]),
        TrackValidationNode(beats_key="beats_rhythm", conf_key="conf_rhythm", node_name="TrackValidationNode_TrackA")
    ])

    # Track B Branch (Instrumental / No Vocals)
    track_b_branch = SequenceNode("TrackB_InstrumentalBranch", [
        FallbackNode("BeatNetFallbackB", [
            BeatNetSingleTrackNode(input_key="inst_track_path", beats_key="beats_inst", node_name="BeatNetNode_TrackB"),
            LibrosaSingleTrackNode(input_key="inst_track_path", beats_key="beats_inst", node_name="LibrosaBeatNode_TrackB")
        ]),
        TrackValidationNode(beats_key="beats_inst", conf_key="conf_inst", node_name="TrackValidationNode_TrackB")
    ])

    return SequenceNode("BeatTrackingRoot", [
        SynthesizeRhythmTrackNode(),
        PrepareInstrumentalTrackNode(),
        track_a_branch,
        track_b_branch,
        BeatFusionArbitratorNode(),
        BeatValidationNode(),
        DownbeatRefineNode()
    ])


class BeatTrackingBTEngine:
    """Stage 3 Beat Tracking BT Engine wrapper."""

    def __init__(self):
        self.tree = build_beat_tracking_tree()

    def run(self, blackboard: Blackboard) -> Blackboard:
        print("\n=== [BeatTrackingBT] Stage 3 Start ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("beat_tracking_status", status.name)
        if status == NodeStatus.SUCCESS:
            print(f"=== [BeatTrackingBT] Stage 3 Done beats_count={len(blackboard.get_val('beats', []))} ===")
        else:
            print("=== [BeatTrackingBT] Stage 3 FAILED ===")
        return blackboard

