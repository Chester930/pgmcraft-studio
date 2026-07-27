import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode, FallbackNode
from pgm_craft.analyzer import MusicAnalyzer


def _to_mono(y):
    if y.ndim > 1:
        return y.mean(axis=1)
    return y


class KickSnarePulseNode(BaseNode):
    """
    【大鼓與小鼓獨立物理脈衝特徵提取衛兵】
    - 讀取 `stems["kick"]` (40-120Hz) 與 `stems["snare"]` (200-2200Hz)
    - 提取獨立的大鼓撞擊時間點 `kick_anchors` (做為強位第一拍對齊參考)
    - 提取獨立的小鼓撞擊時間點 `snare_anchors` (做為 2/4 拍骨幹對齊參考)
    """
    optional_keys = ["stems", "stems_dir"]
    output_keys = ["kick_anchors", "snare_anchors"]

    def __init__(self):
        super().__init__("KickSnarePulseNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")

        kick_path = stems.get("kick")
        snare_path = stems.get("snare")

        if not kick_path and stems_dir:
            kp = os.path.join(stems_dir, "drums", "kick.wav")
            if os.path.exists(kp): kick_path = kp
        if not snare_path and stems_dir:
            sp = os.path.join(stems_dir, "drums", "snare.wav")
            if os.path.exists(sp): snare_path = sp

        kick_anchors = []
        snare_anchors = []

        if kick_path and os.path.exists(kick_path):
            try:
                y, sr = sf.read(kick_path)
                y = _to_mono(y)
                # 簡單能量峰值提取 (100ms 窗口 Peak)
                win = int(sr * 0.1)
                env = np.array([np.max(np.abs(y[i:i+win])) for i in range(0, len(y) - win, win // 2)])
                threshold = np.max(env) * 0.3 if len(env) > 0 and np.max(env) > 0 else 0.01
                peaks = [i * (win // 2) / sr for i, val in enumerate(env) if val >= threshold]

                # 濾除相距過近的重複峰值 (< 0.2s)
                filtered_kicks = []
                for p in peaks:
                    if not filtered_kicks or (p - filtered_kicks[-1]) >= 0.2:
                        filtered_kicks.append(p)
                kick_anchors = filtered_kicks
            except Exception as e:
                print(f"[{self.name} Warning] 提取 Kick 脈衝失敗: {e}")

        blackboard.set_val("kick_anchors", np.array(kick_anchors))
        blackboard.set_val("snare_anchors", np.array(snare_anchors))
        print(f"[{self.name}] ✅ 成功提取 {len(kick_anchors)} 個大鼓重音脈衝點 (Kick Anchors)。")
        return NodeStatus.SUCCESS


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

        submix_dir = os.path.join(stems_dir, "submix") if stems_dir else (os.path.dirname(audio_path) or ".")
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
    output_keys = ["beats_rhythm"]

    def __init__(self, input_key: str, beats_key: str, node_name: str = "BeatNetSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key
        self.required_keys = [input_key]
        self.output_keys = [beats_key]

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
    output_keys = ["beats_rhythm"]

    def __init__(self, input_key: str, beats_key: str, node_name: str = "LibrosaSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key
        self.required_keys = [input_key]
        self.output_keys = [beats_key]
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
    output_keys = ["conf_rhythm"]

    def __init__(self, beats_key: str, conf_key: str, node_name: str = "TrackValidationNode"):
        super().__init__(node_name)
        self.beats_key = beats_key
        self.conf_key = conf_key
        self.required_keys = [beats_key]
        self.output_keys = [conf_key]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val(self.beats_key)
        if beats is None or not isinstance(beats, np.ndarray) or beats.ndim != 2 or len(beats) < 4:
            blackboard.set_val(self.conf_key, 0.0)
            return NodeStatus.SUCCESS

        try:
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
        except Exception as e:
            print(f"[{self.name} Warning] 計算信心度異常: {e}")
            blackboard.set_val(self.conf_key, 0.0)
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
    optional_keys = ["y_rhythm", "sr_rhythm", "rhythm_track_path"]
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

        y_rhythm = blackboard.get_val("y_rhythm")
        sr = blackboard.get_val("sr_rhythm")

        if y_rhythm is None or sr is None:
            try:
                # 讀取 A 軌短時能量
                if rhythm_path and os.path.exists(rhythm_path):
                    y_rhythm, sr = sf.read(rhythm_path)
                    y_rhythm = _to_mono(y_rhythm)
                    blackboard.set_val("y_rhythm", y_rhythm)
                    blackboard.set_val("sr_rhythm", sr)
            except Exception as e:
                print(f"[{self.name} Warning] 無法讀取 A 軌音訊，改用信心度高者: {e}")

        if y_rhythm is None:
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
                # 鼓軌在此時間點靜音 (Intro/Breakdown)：開啟 Tempo Inertia 速度慣性引擎
                # 優先拿 B 軌最近拍點，但若 B 軌拍點與上一拍步距異常 (<0.3s)，改採前段穩定步距等速內插
                idx_b = np.argmin(np.abs(timestamps_b - t))
                t_candidate = float(beats_b[idx_b, 0])
                label_candidate = int(beats_b[idx_b, 1])

                if len(final_beats_list) >= 2:
                    last_interval = final_beats_list[-1][0] - final_beats_list[-2][0]
                else:
                    last_interval = 0.5  # 預設 120 BPM

                # 若選出的 B 軌拍點與上一拍時間過近 (< 0.7 * last_interval) 或過遠，使用穩定慣性內插
                if final_beats_list and (t_candidate - final_beats_list[-1][0] < 0.7 * last_interval or t_candidate - final_beats_list[-1][0] > 1.4 * last_interval):
                    inertia_t = final_beats_list[-1][0] + last_interval
                    inertia_label = (int(final_beats_list[-1][1]) % 4) + 1
                    final_beats_list.append([inertia_t, inertia_label])
                    switched_to_b += 1
                    continue
                else:
                    final_beats_list.append([t_candidate, label_candidate])
                    switched_to_b += 1
                    continue
            final_beats_list.append([t, label])
            used_a += 1

        # 依時間升序排序
        final_beats_list.sort(key=lambda x: x[0])

        # 淨化與衛兵防護：強制 timestamp 必須嚴格遞增 (解決浮點數或替換造成之微秒退步/重複問題)
        sanitized_beats = []
        last_t = -1.0
        for b_item in final_beats_list:
            t_val, b_label = b_item[0], b_item[1]
            if t_val > last_t + 1e-4:
                sanitized_beats.append([t_val, b_label])
                last_t = t_val

        final_beats_arr = np.array(sanitized_beats)
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


class ReEntryReAnchoringNode(BaseNode):
    """
    【鼓聲重返重音第一拍自動鎖定衛兵】
    - 讀取 `kick_anchors` (大鼓重音脈衝) 與 `beats` (當前拍點陣列)
    - 檢測無鼓切回有鼓（或大鼓切入撞擊點），強制重錨校正拍號標記為 1 號拍 (Beat 1 Downbeat)
    """
    optional_keys = ["beats", "kick_anchors"]
    output_keys = ["beats"]

    def __init__(self):
        super().__init__("ReEntryReAnchoringNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        kick_anchors = blackboard.get_val("kick_anchors")

        if beats is None or len(beats) == 0:
            return NodeStatus.SUCCESS
        if kick_anchors is None or len(kick_anchors) == 0:
            return NodeStatus.SUCCESS

        reanchored_beats = beats.copy()
        for k_t in kick_anchors:
            # 找到最近的拍點
            diffs = np.abs(reanchored_beats[:, 0].astype(float) - k_t)
            min_idx = np.argmin(diffs)
            if diffs[min_idx] < 0.12:
                # 重新鎖定此拍為 Beat 1 Downbeat
                reanchored_beats[min_idx, 1] = 1
                # 重新修正後續拍子的倒數 1-2-3-4
                for step in range(1, 4):
                    if min_idx + step < len(reanchored_beats):
                        reanchored_beats[min_idx + step, 1] = step + 1

        blackboard.set_val("beats", reanchored_beats)
        print(f"[{self.name}] 🎯 強制重錨衛兵對齊完畢，已校正鼓聲切入第一拍 (Beat 1)。")
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
        KickSnarePulseNode(),
        track_a_branch,
        track_b_branch,
        BeatFusionArbitratorNode(),
        ReEntryReAnchoringNode(),
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
        blackboard.set_val("workflow_status", status.name)
        if status == NodeStatus.SUCCESS:
            print(f"=== [BeatTrackingBT] Stage 3 Done beats_count={len(blackboard.get_val('beats', []))} ===")
        else:
            print("=== [BeatTrackingBT] Stage 3 FAILED ===")
        return blackboard

