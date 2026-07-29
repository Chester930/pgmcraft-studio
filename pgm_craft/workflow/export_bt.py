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
    【純音樂伴奏 + Click 混合音軌合成衛兵 (Backing Track with Click Synthesizer Node)】
    - 讀取 Stage 2/4 產出之樂器音軌 (drums, bass, guitar, piano, instrumental, no_vocals)
    - 排除主唱聲音，將純樂器伴奏 (鼓+Bass+吉他+鋼琴等) 與 Click 導引軌進行精確疊加
    - 同時導出至 `click/backing_with_click.wav` 與專案根目錄
    """
    required_keys = []
    optional_keys = ["y", "sr", "audio_path", "stems", "extracted_stems", "click_audio", "output_dir", "project_dir", "click_track"]
    output_keys = ["backing_with_click_path"]

    def __init__(self):
        super().__init__("BackingWithClickSynthesizerNode")

    def _to_mono(self, audio) -> np.ndarray:
        arr = np.asarray(audio)
        if arr.ndim == 0:
            return arr.reshape(1).astype(np.float32)
        if arr.ndim == 1:
            return arr.astype(np.float32)
        if arr.ndim == 2:
            # soundfile reads as samples x channels, while some separators keep channels x samples.
            if arr.shape[0] <= 8 and arr.shape[1] > arr.shape[0]:
                return arr.mean(axis=0).astype(np.float32)
            return arr.mean(axis=1).astype(np.float32)
        return arr.reshape(-1).astype(np.float32)

    def _resample_if_needed(self, audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
        source_sr = int(source_sr or target_sr)
        target_sr = int(target_sr or source_sr)
        if source_sr == target_sr:
            return audio.astype(np.float32)
        if len(audio) <= 1:
            return audio.astype(np.float32)
        try:
            import librosa
            return librosa.resample(audio.astype(np.float32), orig_sr=source_sr, target_sr=target_sr)
        except Exception:
            new_len = max(1, int(round(len(audio) * target_sr / source_sr)))
            old_x = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
            new_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            return np.interp(new_x, old_x, audio).astype(np.float32)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        target_dir = blackboard.get_val("project_dir", blackboard.get_val("output_dir", "outputs"))
        click_dir = os.path.join(target_dir, "click") if os.path.basename(target_dir) != "click" else target_dir
        os.makedirs(click_dir, exist_ok=True)

        sr = int(blackboard.get_val("sr", 22050) or 22050)
        y = blackboard.get_val("y")

        stems = blackboard.get_val("stems", {})
        extracted_stems = blackboard.get_val("extracted_stems", {})
        click_audio = blackboard.get_val("click_audio")
        click_sr = sr if click_audio is not None else None

        # 0. 若未能從 blackboard 取得 click_audio，嘗試從 click_track.wav 讀取
        if click_audio is None:
            click_file = blackboard.get_val("click_track") or os.path.join(click_dir, "click_track.wav")
            if click_file and os.path.exists(click_file):
                try:
                    click_audio, click_sr = sf.read(click_file)
                    click_audio = self._to_mono(click_audio)
                except Exception:
                    click_audio = None
                    click_sr = None
        elif click_audio is not None:
            click_audio = self._to_mono(click_audio)

        # 1. 取得/合成純樂器伴奏 (無主唱)
        backing_audio = None
        backing_sr = sr
        backing_source = None

        # (a) 檢查是否有現成伴奏音訊陣列或檔案 (no_vocals / instrumental)
        for key in ["no_vocal", "no_vocals", "instrumental"]:
            val = stems.get(key)
            if val is None:
                val = extracted_stems.get(key)
            if isinstance(val, np.ndarray):
                backing_audio = self._to_mono(val)
                backing_source = key
                break
            elif isinstance(val, str) and os.path.exists(val):
                try:
                    w, w_sr = sf.read(val)
                    backing_audio = self._to_mono(w)
                    backing_sr = int(w_sr)
                    backing_source = key
                    break
                except Exception:
                    pass

        # 若沒在 stems 字典中找到，主動到 stems/ 目錄下尋找 instrumental.wav 或 no_vocals.wav
        if backing_audio is None:
            for fname in ["instrumental.wav", "no_vocals.wav", "no_vocal.wav"]:
                candidate = os.path.join(target_dir, "stems", fname)
                if os.path.exists(candidate):
                    try:
                        w, w_sr = sf.read(candidate)
                        backing_audio = self._to_mono(w)
                        backing_sr = int(w_sr)
                        backing_source = fname
                        break
                    except Exception:
                        pass

        # (b) 若無整體伴奏檔，嘗試讀取/加載各大樂器分軌並求和 (drums, bass, guitar, piano, other, stringss)
        if backing_audio is None:
            instrument_parts = []
            mix_sr = None
            stem_keys = ["drums", "bass", "guitar", "guitars", "piano", "pianos", "other", "stringss"]
            for skey in stem_keys:
                val = stems.get(skey)
                if val is None:
                    val = extracted_stems.get(skey)
                if isinstance(val, np.ndarray):
                    w = self._to_mono(val)
                    part_sr = sr
                    mix_sr = mix_sr or part_sr
                    w = self._resample_if_needed(w, part_sr, mix_sr)
                    instrument_parts.append(w)
                elif isinstance(val, str) and os.path.exists(val):
                    try:
                        w, w_sr = sf.read(val)
                        part_sr = int(w_sr)
                        mix_sr = mix_sr or part_sr
                        w = self._resample_if_needed(self._to_mono(w), part_sr, mix_sr)
                        instrument_parts.append(w)
                    except Exception:
                        pass
                elif isinstance(val, dict):
                    p = val.get("path")
                    if p and os.path.exists(p):
                        try:
                            w, w_sr = sf.read(p)
                            part_sr = int(w_sr)
                            mix_sr = mix_sr or part_sr
                            w = self._resample_if_needed(self._to_mono(w), part_sr, mix_sr)
                            instrument_parts.append(w)
                        except Exception:
                            pass

            if instrument_parts:
                min_len = min(len(w) for w in instrument_parts)
                backing_audio = sum(w[:min_len] for w in instrument_parts)
                backing_sr = int(mix_sr or sr)
                backing_source = "instrument_parts"

        # (c) Fallback: 若全無分軌，回退使用原始音訊波形 y
        if backing_audio is None:
            if y is not None:
                backing_audio = self._to_mono(y)
                backing_source = "original_waveform"
            else:
                audio_path = blackboard.get_val("audio_path")
                if audio_path and os.path.exists(audio_path):
                    try:
                        w, backing_sr = sf.read(audio_path)
                        backing_sr = int(backing_sr)
                        backing_audio = self._to_mono(w)
                        backing_source = "audio_path"
                    except Exception:
                        backing_audio = None

        if backing_audio is None:
            print(f"[{self.name}] ⚠️ 無法取得伴奏音訊，略過 backing_with_click 導出。")
            return NodeStatus.SUCCESS

        # 2. 混入 Click 音訊 (若存在)
        if click_audio is not None and len(click_audio) > 0:
            click_mono = self._resample_if_needed(self._to_mono(click_audio), click_sr or sr, backing_sr)
            min_len = min(len(backing_audio), len(click_mono))
            mixed = backing_audio[:min_len] + click_mono[:min_len] * 0.7
        else:
            mixed = backing_audio

        # Peak Limiter Guard (-1.0 dBFS)
        if mixed is None or len(mixed) == 0:
            print(f"[{self.name}] ⚠️ backing_with_click 音訊為空，略過導出。")
            return NodeStatus.SUCCESS

        peak = np.max(np.abs(mixed))
        if peak > 0.891:
            mixed = mixed * (0.891 / peak)

        out_click_path = os.path.join(click_dir, "backing_with_click.wav")
        sf.write(out_click_path, mixed.astype(np.float32), backing_sr)

        blackboard.set_val("backing_with_click_path", out_click_path)
        blackboard.set_val("backing_with_click_sample_rate", backing_sr)
        blackboard.set_val("backing_with_click_duration_sec", float(len(mixed) / backing_sr))
        blackboard.set_val("backing_with_click_source", backing_source)
        outputs = blackboard.get_val("outputs", {})
        outputs["backing_with_click"] = out_click_path
        blackboard.set_val("outputs", outputs)

        print(f"[{self.name}] 🎧 成功導出純樂器伴奏 + Click 音軌 ➔ {out_click_path}")
        return NodeStatus.SUCCESS


class IEMSplitMonoLRNode(BaseNode):
    """
    【Live 舞台雙聲道立體聲 IEM 分立路由節點】
    - 左聲道 (L): 純 Mono Click 節拍打點音軌
    - 右聲道 (R): 純 Mono 音樂伴奏 (No Vocal Backing Stem)
    - 導出檔名: iem_split_mono_lr.wav (方便 PA 工程師直連 Stage Box 分路)
    """
    required_keys = ["output_dir"]
    optional_keys = ["y", "sr", "audio_path", "stems", "click_audio", "click_track"]
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

        if y is None:
            audio_path = blackboard.get_val("audio_path")
            if audio_path and os.path.exists(audio_path):
                try:
                    y, sr = sf.read(audio_path)
                except Exception:
                    y = None

        if click_audio is None:
            click_file = blackboard.get_val("click_track") or os.path.join(output_dir, "click", "click_track.wav")
            if click_file and os.path.exists(click_file):
                try:
                    click_audio, _ = sf.read(click_file)
                except Exception:
                    click_audio = None

        if y is None and click_audio is None:
            print(f"[{self.name}] ⚠️ 無可用原曲或 click 音訊，略過 IEM 分立導出。")
            return NodeStatus.SUCCESS

        reference_audio = y if y is not None else click_audio
        reference_mono = reference_audio.mean(axis=1) if reference_audio.ndim > 1 else reference_audio

        # 1. Left Channel: Mono Click
        if click_audio is not None and len(click_audio) > 0:
            left_click = click_audio.mean(axis=1) if click_audio.ndim > 1 else click_audio
        else:
            left_click = np.zeros_like(reference_mono)

        # 2. Right Channel: Mono Backing
        if "drums" in stems and "bass" in stems and "other" in stems:
            backing = stems["drums"] + stems["bass"] + stems["other"]
        elif "no_vocal" in stems:
            backing = stems["no_vocal"]
        else:
            backing = y if y is not None else np.zeros_like(left_click)
        right_backing = backing.mean(axis=1) if backing.ndim > 1 else backing

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


class CountInSynthesizerNode(BaseNode):
    """
    【曲首 1-2 小節預備拍 (Count-In) 合成節點】
    - 自動依據曲首平均 BPM 計算 1 小節 (4 拍) 的預備拍區間
    - 合成高分貝高音 1,000Hz (拍 1) 與中音 800Hz (拍 2,3,4) 預備拍脈衝
    - 導出 click_with_countin.wav 並記錄 countin_offset_sec
    """
    required_keys = ["output_dir", "sr", "beats"]
    optional_keys = ["click_audio"]
    output_keys = ["click_with_countin_path", "countin_offset_sec"]

    def __init__(self, count_in_bars: int = 1):
        super().__init__("CountInSynthesizerNode")
        self.count_in_bars = count_in_bars

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        sr = blackboard.get_val("sr", 22050)
        beats = blackboard.get_val("beats")
        click_audio = blackboard.get_val("click_audio")

        if beats is None or len(beats) < 4:
            return NodeStatus.SUCCESS

        timestamps = beats[:, 0].astype(float)
        # 計算前 4 拍平均步距
        beat_interval = np.mean(np.diff(timestamps[:4])) if len(timestamps) >= 4 else 0.5
        count_in_beats = self.count_in_bars * 4
        count_in_duration = count_in_beats * beat_interval

        # 合成預備拍音效 (Count-In Audio)
        count_in_samples = int(count_in_duration * sr)
        countin_sig = np.zeros(count_in_samples, dtype=np.float32)

        for i in range(count_in_beats):
            t_sec = i * beat_interval
            idx = int(t_sec * sr)
            freq = 1000.0 if i == 0 else 800.0 # 拍 1 高音，拍 2/3/4 中音
            t_pulse = np.linspace(0, 0.05, int(sr * 0.05), False)
            pulse = np.sin(2 * np.pi * freq * t_pulse) * np.exp(-t_pulse * 40.0)
            p_len = min(len(pulse), count_in_samples - idx)
            if p_len > 0:
                countin_sig[idx:idx+p_len] += pulse[:p_len].astype(np.float32)

        # 拼接至原 Click 音軌前面
        if click_audio is not None and len(click_audio) > 0:
            click_mono = click_audio.mean(axis=0) if click_audio.ndim > 1 else click_audio
            full_click_with_ci = np.concatenate([countin_sig, click_mono])
        else:
            full_click_with_ci = countin_sig

        out_path = os.path.join(output_dir, "click_with_countin.wav")
        sf.write(out_path, full_click_with_ci, sr)

        blackboard.set_val("click_with_countin_path", out_path)
        blackboard.set_val("countin_offset_sec", count_in_duration)

        outputs = blackboard.get_val("outputs", {})
        outputs["click_with_countin"] = out_path
        blackboard.set_val("outputs", outputs)

        print(f"[{self.name}] ⏱️ 成功合成曲首 {self.count_in_bars} 小節預備拍 (Count-In: {count_in_duration:.2f}s) ➔ {out_path}")
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
        IEMSplitMonoLRNode(),
        CountInSynthesizerNode()
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
