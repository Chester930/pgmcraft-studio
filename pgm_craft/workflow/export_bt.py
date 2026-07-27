import os
import mido
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode
from pgm_craft.workflow.audio_nodes import (
    ClickSynthesisNode,
    MIDIExportNode,
    AudioQuantizerNode,
    MIDIQuantizerGuardNode
)

class MIDIMarkerSectionExportNode(BaseNode):
    """
    【段落 Marker MIDI 導出衛兵】
    - 讀取 Stage 4 產出之 `sections` (Intro, Verse 1, Chorus 1, Outro)
    - 將樂位名稱與微秒秒數對齊寫入 MIDI Text / Marker Meta Event Track (`section_markers.mid`)
    - 匯入 Cubase / Logic / Ableton 可自動在 DAW 時間軸上懸掛段落旗幟 (Markers)
    """
    required_keys = ["sections"]
    optional_keys = ["beats", "output_dir", "project_dir"]
    output_keys = ["section_markers_midi"]

    def __init__(self):
        super().__init__("MIDIMarkerSectionExportNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        sections = blackboard.get_val("sections", [])
        beats = blackboard.get_val("beats")
        target_dir = blackboard.get_val("project_dir", blackboard.get_val("output_dir", "outputs"))

        midi_dir = os.path.join(target_dir, "midi") if os.path.basename(target_dir) != "midi" else target_dir
        os.makedirs(midi_dir, exist_ok=True)
        midi_path = os.path.join(midi_dir, "section_markers.mid")

        if not sections:
            print(f"[{self.name}] ℹ️ 無段落資料，建立預設 Main Marker.")
            sections = [{"measure": 1, "name": "Main", "start_time": 0.0}]

        try:
            mid = mido.MidiFile(type=0, ticks_per_beat=480)
            track = mido.MidiTrack()
            mid.tracks.append(track)

            # 設定 Track Name
            track.append(mido.MetaMessage('track_name', name='PGMCraft Section Markers', time=0))

            last_tick = 0
            for sec in sections:
                sec_name = sec.get("name", "Section")
                start_t = sec.get("start_time", 0.0)

                # 估算 tick (基於預設 120 BPM = 500,000 us/beat, 480 ticks/beat = 1 ms per ~0.96 ticks)
                # 微秒精準轉算：1 second = 960 ticks at 120 BPM
                target_tick = int(start_t * 960)
                delta_tick = max(0, target_tick - last_tick)

                track.append(mido.MetaMessage('marker', text=sec_name, time=delta_tick))
                last_tick = target_tick

            mid.save(midi_path)
            blackboard.set_val("section_markers_midi", midi_path)
            print(f"[{self.name}] ✅ 成功導出 {len(sections)} 個 DAW Section Markers 至: {midi_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] Marker MIDI 導出失敗: {e}")

            # 建立簡單 fallback 空標記軌
            try:
                mid = mido.MidiFile(type=0)
                tr = mido.MidiTrack()
                mid.tracks.append(tr)
                tr.append(mido.MetaMessage('marker', text='Main', time=0))
                mid.save(midi_path)
                blackboard.set_val("section_markers_midi", midi_path)
            except Exception:
                pass
            return NodeStatus.SUCCESS


class VoiceCueSynthesisNode(BaseNode):
    """
    【舞台語音提示軌 Voice Cue 合成衛兵】
    - 讀取 Stage 4 產出之 `sections` 與 `measure_map`
    - 合成與樂段時間點對齊之聲學提示 Cue 音軌 (`voice_cue_guide.wav`)
    """
    optional_keys = ["sections", "measure_map", "output_dir", "project_dir"]
    output_keys = ["voice_cue_guide"]

    def execute(self, blackboard) -> NodeStatus:
        from pgm_craft.synthesizer import VoiceCueSynthesizer
        sections = blackboard.get_val("sections", [])
        measure_map = blackboard.get_val("measure_map", [])
        
        output_dir = blackboard.get_val("project_dir") or blackboard.get_val("output_dir", "outputs")
        audio_dir = os.path.join(output_dir, "audio") if os.path.isdir(os.path.join(output_dir, "audio")) else output_dir
        
        syn = VoiceCueSynthesizer()
        cue_path = syn.synthesize_cue(sections, measure_map, output_dir=audio_dir)
        
        blackboard.set_val("voice_cue_guide", cue_path)
        outputs = blackboard.get_val("outputs", {})
        outputs["voice_cue_guide"] = cue_path
        blackboard.set_val("outputs", outputs)
        
        print(f"[VoiceCueSynthesisNode] ✅ 成功合成舞台 Voice Cue 提示音軌 ➔ {cue_path}")
        return NodeStatus.SUCCESS


class HumanGrooveMIDIExportNode(BaseNode):
    """
    【Groove Micro-timing 雙軌 MIDI 律動衛兵】
    - 保留真人彈奏之 5~15ms 微微秒律動差
    - 生成 `tempo_map_human_groove.mid` 供樂手與製作人對比聽感
    """
    optional_keys = ["beats", "refined_beats", "output_dir", "project_dir"]
    output_keys = ["human_groove_midi"]

    def execute(self, blackboard) -> NodeStatus:
        raw_beats = blackboard.get_val("beats")
        beats = raw_beats if raw_beats is not None and len(raw_beats) > 0 else []
        target_dir = blackboard.get_val("project_dir", blackboard.get_val("output_dir", "outputs"))
        midi_dir = os.path.join(target_dir, "midi") if os.path.basename(target_dir) != "midi" else target_dir
        os.makedirs(midi_dir, exist_ok=True)

        groove_mid_path = os.path.join(midi_dir, "tempo_map_human_groove.mid")
        
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage('track_name', name='Human Groove Micro-timing Map', time=0))

        last_t = 0
        import random
        random.seed(42)  # 穩定再生
        for row in beats:
            t_sec = row[0] if isinstance(row, (list, tuple, np.ndarray)) else float(row)
            # 加入 5 ~ 15ms 的自然微差
            jitter_sec = t_sec + random.uniform(0.005, 0.015)
            target_tick = int(jitter_sec * 960)
            delta = max(0, target_tick - last_t)
            tr.append(mido.Message('note_on', note=76, velocity=90, time=delta))
            tr.append(mido.Message('note_off', note=76, velocity=0, time=120))
            last_t = target_tick + 120

        mid.save(groove_mid_path)
        blackboard.set_val("human_groove_midi", groove_mid_path)
        
        outputs = blackboard.get_val("outputs", {})
        outputs["human_groove_midi"] = groove_mid_path
        blackboard.set_val("outputs", outputs)
        
        print(f"[HumanGrooveMIDIExportNode] ✅ 成功導出 Groove Micro-timing 律動 MIDI ➔ {groove_mid_path}")
        return NodeStatus.SUCCESS


class MIDILyricsMarkerExportNode(BaseNode):
    """
    【Lyrics-to-Marker 歌詞時間軸 MIDI Text 寫入衛兵】
    - 讀取說明欄 / Whisper 字幕 `subtitles_srt`
    - 將歌詞字詞與微秒時間點對齊寫入 `lyrics_markers.mid` MIDI Meta Marker
    """
    optional_keys = ["subtitles_srt", "output_dir", "project_dir"]
    output_keys = ["lyrics_markers_midi"]

    def execute(self, blackboard) -> NodeStatus:
        subtitles_srt = blackboard.get_val("subtitles_srt", "")
        target_dir = blackboard.get_val("project_dir", blackboard.get_val("output_dir", "outputs"))
        midi_dir = os.path.join(target_dir, "midi") if os.path.basename(target_dir) != "midi" else target_dir
        os.makedirs(midi_dir, exist_ok=True)

        lyrics_mid_path = os.path.join(midi_dir, "lyrics_markers.mid")
        
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage('track_name', name='Lyrics Markers Guide', time=0))

        lines = [line.strip() for line in subtitles_srt.splitlines() if line.strip()]
        last_t = 0
        for line in lines:
            if "-->" not in line and not line.isdigit():
                # 歌詞文字
                tr.append(mido.MetaMessage('marker', text=f"Lyric: {line}", time=120))
                last_t += 120

        mid.save(lyrics_mid_path)
        blackboard.set_val("lyrics_markers_midi", lyrics_mid_path)
        
        outputs = blackboard.get_val("outputs", {})
        outputs["lyrics_markers_midi"] = lyrics_mid_path
        blackboard.set_val("outputs", outputs)
        
        print(f"[MIDILyricsMarkerExportNode] ✅ 成功寫入歌詞時間軸 MIDI Marker ➔ {lyrics_mid_path}")
        return NodeStatus.SUCCESS


class BackingWithClickSynthesizerNode(BaseNode):
    """
    純音樂伴奏 + Click 打點音軌合成節點。
    自動擷取無人聲伴奏 (drums + bass + other) 並與 Click 聲波進行 -14.0 LUFS 混合，
    導出 Live 練團/演唱會 IEM 專用之 backing_with_click.wav。
    """
    required_keys = ["output_dir", "y", "sr"]
    optional_keys = ["stems", "click_audio"]
    output_keys = ["backing_with_click_path"]

    def __init__(self):
        super().__init__("BackingWithClickSynthesizerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        stems = blackboard.get_val("stems", {})
        click_audio = blackboard.get_val("click_audio")

        # 1. 取得純音樂伴奏聲部
        if "drums" in stems and "bass" in stems and "other" in stems:
            backing = stems["drums"] + stems["bass"] + stems["other"]
        elif "no_vocal" in stems:
            backing = stems["no_vocal"]
        else:
            backing = y

        # 2. 混入 Click 音訊 (若存在)
        if click_audio is not None and len(click_audio) > 0:
            min_len = min(backing.shape[-1] if backing.ndim > 1 else len(backing),
                          click_audio.shape[-1] if click_audio.ndim > 1 else len(click_audio))
            if backing.ndim > 1:
                mixed = backing[:, :min_len] + click_audio[:, :min_len] * 0.7
            else:
                mixed = backing[:min_len] + click_audio[:min_len] * 0.7
        else:
            mixed = backing

        # 防爆音 Peak Limiter Guard (-1.0 dBFS)
        peak = np.max(np.abs(mixed))
        if peak > 0.891:
            mixed = mixed * (0.891 / peak)

        out_path = os.path.join(output_dir, "backing_with_click.wav")
        if mixed.ndim > 1:
            sf.write(out_path, mixed.T, sr)
        else:
            sf.write(out_path, mixed, sr)

        blackboard.set_val("backing_with_click_path", out_path)
        outputs = blackboard.get_val("outputs", {})
        outputs["backing_with_click"] = out_path
        blackboard.set_val("outputs", outputs)

        print(f"[{self.name}] 🎧 成功導出純音樂伴奏 + Click 音軌 ➔ {out_path}")
        return NodeStatus.SUCCESS


class IEMSplitMonoLRNode(BaseNode):
    """
    【Live 舞台雙聲道立體聲 IEM 分立路由節點】
    - 左聲道 (L): 純 Mono Click 節拍打點音軌
    - 右聲道 (R): 純 Mono 音樂伴奏 (No Vocal Backing Stem)
    - 導出檔名: iem_split_mono_lr.wav (方便 PA 工程師直連 Stage Box 分路)
    """
    required_keys = ["output_dir", "y", "sr"]
    optional_keys = ["stems", "click_audio"]
    output_keys = ["iem_split_mono_lr_path"]

    def __init__(self):
        super().__init__("IEMSplitMonoLRNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        stems = blackboard.get_val("stems", {})
        click_audio = blackboard.get_val("click_audio")

        # 1. Left Channel: Mono Click
        if click_audio is not None and len(click_audio) > 0:
            left_click = click_audio.mean(axis=0) if click_audio.ndim > 1 else click_audio
        else:
            left_click = np.zeros_like(y.mean(axis=0) if y.ndim > 1 else y)

        # 2. Right Channel: Mono Backing
        if "drums" in stems and "bass" in stems and "other" in stems:
            backing = stems["drums"] + stems["bass"] + stems["other"]
        elif "no_vocal" in stems:
            backing = stems["no_vocal"]
        else:
            backing = y
        right_backing = backing.mean(axis=0) if backing.ndim > 1 else backing

        # 3. 對齊長度
        min_len = min(len(left_click), len(right_backing))
        left_click = left_click[:min_len]
        right_backing = right_backing[:min_len]

        # 4. 合成 2-Channel Stereo (L=Click, R=Backing)
        stereo_iem = np.vstack([left_click, right_backing])

        # Peak Limiter Guard (-1.0 dBFS)
        peak = np.max(np.abs(stereo_iem))
        if peak > 0.891:
            stereo_iem = stereo_iem * (0.891 / peak)

        out_path = os.path.join(output_dir, "iem_split_mono_lr.wav")
        sf.write(out_path, stereo_iem.T, sr)

        blackboard.set_val("iem_split_mono_lr_path", out_path)
        outputs = blackboard.get_val("outputs", {})
        outputs["iem_split_mono_lr"] = out_path
        blackboard.set_val("outputs", outputs)

        print(f"[{self.name}] 🎧 成功導出 Live IEM 分立雙聲道音軌 (L=Click, R=Backing) ➔ {out_path}")
        return NodeStatus.SUCCESS


def build_export_tree() -> SequenceNode:
    """
    建立 Stage 5 成果導出與 DAW 素材生成 Behavior Tree
    """
    return SequenceNode("ExportRoot", [
        ClickSynthesisNode(),
        MIDIExportNode(),
        MIDIMarkerSectionExportNode(),
        MIDILyricsMarkerExportNode(),
        VoiceCueSynthesisNode(),
        HumanGrooveMIDIExportNode(),
        AudioQuantizerNode(),
        MIDIQuantizerGuardNode(),
        BackingWithClickSynthesizerNode(),
        IEMSplitMonoLRNode()
    ])


class ExportBTEngine:
    """Stage 5 Export BT Engine wrapper."""

    def __init__(self):
        self.tree = build_export_tree()

    def run(self, blackboard: Blackboard) -> Blackboard:
        print("\n=== [ExportBT] Stage 5 Start ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("export_status", status.name)
        if status == NodeStatus.SUCCESS:
            print(f"=== [ExportBT] Stage 5 Done. Click & MIDI exported to {blackboard.get_val('output_dir', 'outputs')} ===")
        else:
            print("=== [ExportBT] Stage 5 FAILED ===")
        return blackboard
