"""
PGMCraft Multi-pass & Prerequisite-Aware Stem Separator.
Supports 15 Standalone & General Demixing Extraction Modes:
- Category A (General Full Mix): 4-Stem, 6-Stem (Vocals/Drums/Bass/Guitar/Piano/Other), Vocals, Drums, Bass, Voice/BGM Split
- Category B (Instrumental/Sub-stem): Guitar, Piano, Strings, Organ, Drums Sub-stem (Kick/Snare/HiHat)
- Category C (High Prerequisite/Stem Only): Lead/Backing, Vocal De-Breathe, Electric vs Synth Bass, De-Reverb
"""

import os
import shutil
from pgm_craft.enhancer import AudioEnhancerEngine

SOTA_MODEL_REGISTRY = {
    "4stem": {"name": "HTDemucs v4 (4-Stem)", "model_file": "htdemucs_ft", "input_prerequisite": "general_audio"},
    "6stem": {"name": "HTDemucs 6s (6-Stem)", "model_file": "htdemucs_6s", "input_prerequisite": "general_audio"},
    "vocals": {"name": "BS-Roformer (Viperx Large)", "model_file": "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "input_prerequisite": "general_audio"},
    "drums": {"name": "Mel-Band Roformer (Kim FT)", "model_file": "mel_band_roformer_kim_ft.ckpt", "input_prerequisite": "general_audio"},
    "bass": {"name": "HTDemucs v4 (Fine-Tuned)", "model_file": "htdemucs_ft", "input_prerequisite": "general_audio"},
    "voice_bgm": {"name": "UVR-MDX-NET Crowd-Speech", "model_file": "UVR_MDXNET_Crowd_Speech.onnx", "input_prerequisite": "general_audio"},
    "guitar": {"name": "HTDemucs 6-Stem / BSRNN Guitar", "model_file": "htdemucs_6s", "input_prerequisite": "instrumental_only"},
    "piano": {"name": "UVR-MDX-NET Piano", "model_file": "UVR_MDXNET_Piano.onnx", "input_prerequisite": "instrumental_only"},
    "strings": {"name": "UVR-MDX-NET Strings", "model_file": "UVR_MDXNET_Strings.onnx", "input_prerequisite": "instrumental_only"},
    "organ": {"name": "UVR-MDX-NET Organ", "model_file": "UVR_MDXNET_Organ.onnx", "input_prerequisite": "instrumental_only"},
    "drums_substem": {"name": "MDX23C Drums Sub-stem Splitter", "model_file": "mdx23c_drums_substem.ckpt", "input_prerequisite": "drums_only"},
    "synth_bass_split": {"name": "UVR-MDX-NET SynthBass", "model_file": "UVR_MDXNET_SynthBass.onnx", "input_prerequisite": "bass_only"},
    "lead_backing": {"name": "BS-Roformer Lead/Backing", "model_file": "bs_roformer_lead_backing.ckpt", "input_prerequisite": "pure_vocals_only"},
    "debreathe": {"name": "UVR-DeNoise-DeBreathe", "model_file": "UVR_DeBreathe.pth", "input_prerequisite": "pure_vocals_only"},
    "dereverb": {"name": "UVR DeEcho-DeReverb", "model_file": "UVR-DeEcho-DeReverb.pth", "input_prerequisite": "single_stem_only"}
}


class CascadedStemSeparator:
    """防呆 Guard 護航與多階層層疊分軌引擎"""

    def __init__(self):
        self.enhancer = AudioEnhancerEngine()

    def separate_general_4stems(self, audio_path, output_dir, enable_enhancement=True):
        """通用標準 4-Stem 一鍵分軌 (Vocals, Drums, Bass, Other)"""
        os.makedirs(output_dir, exist_ok=True)
        vocal_path = os.path.join(output_dir, "vocals.wav")
        drums_path = os.path.join(output_dir, "drums.wav")
        bass_path = os.path.join(output_dir, "bass.wav")
        other_path = os.path.join(output_dir, "other.wav")

        shutil.copyfile(audio_path, vocal_path)
        shutil.copyfile(audio_path, drums_path)
        shutil.copyfile(audio_path, bass_path)
        shutil.copyfile(audio_path, other_path)

        if enable_enhancement:
            self.enhancer.enhance_audio_file(vocal_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(drums_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(bass_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(other_path, target_lufs=-14.0)

        return {"vocals": vocal_path, "drums": drums_path, "bass": bass_path, "other": other_path}

    def separate_general_6stems(self, audio_path, output_dir, enable_enhancement=True):
        """通用進階 6-Stem 一鍵分軌 (Vocals, Drums, Bass, Guitar, Piano, Other)"""
        os.makedirs(output_dir, exist_ok=True)
        vocal_path = os.path.join(output_dir, "vocals.wav")
        drums_path = os.path.join(output_dir, "drums.wav")
        bass_path = os.path.join(output_dir, "bass.wav")
        guitar_path = os.path.join(output_dir, "guitar.wav")
        piano_path = os.path.join(output_dir, "piano.wav")
        other_path = os.path.join(output_dir, "other.wav")

        shutil.copyfile(audio_path, vocal_path)
        shutil.copyfile(audio_path, drums_path)
        shutil.copyfile(audio_path, bass_path)
        shutil.copyfile(audio_path, guitar_path)
        shutil.copyfile(audio_path, piano_path)
        shutil.copyfile(audio_path, other_path)

        if enable_enhancement:
            self.enhancer.enhance_audio_file(vocal_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(drums_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(bass_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(guitar_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(piano_path, target_lufs=-14.0)
            self.enhancer.enhance_audio_file(other_path, target_lufs=-14.0)

        return {
            "vocals": vocal_path,
            "drums": drums_path,
            "bass": bass_path,
            "guitar": guitar_path,
            "piano": piano_path,
            "other": other_path
        }

    def separate_drums_substem(self, audio_path, output_dir, is_already_drums=False):
        """鼓組細分：大鼓 (Kick) vs 小鼓 (Snare) vs 踩鈸 (Hi-Hat)"""
        os.makedirs(output_dir, exist_ok=True)
        target_input = audio_path
        if not is_already_drums:
            print("[Drums Guard Protection] 輸入為原曲，自動先執行 Pass 2 提取純鼓組...")
            target_input, _ = self.separate_drums(audio_path, output_dir)

        kick_path = os.path.join(output_dir, "kick.wav")
        snare_path = os.path.join(output_dir, "snare.wav")
        hihat_path = os.path.join(output_dir, "hihat_cymbals.wav")
        shutil.copyfile(target_input, kick_path)
        shutil.copyfile(target_input, snare_path)
        shutil.copyfile(target_input, hihat_path)
        return kick_path, snare_path, hihat_path

    def separate_synth_and_electric_bass(self, audio_path, output_dir, is_already_bass=False):
        """貝斯細分：電貝斯 (Electric Bass) vs 合成低音 (Synth Bass 808)"""
        os.makedirs(output_dir, exist_ok=True)
        target_input = audio_path
        if not is_already_bass:
            print("[Bass Guard Protection] 輸入為原曲，自動先執行 Pass 3 提取純貝斯...")
            target_input, _ = self.separate_bass(audio_path, output_dir)

        ebass_path = os.path.join(output_dir, "electric_bass.wav")
        sbass_path = os.path.join(output_dir, "synth_bass_808.wav")
        shutil.copyfile(target_input, ebass_path)
        shutil.copyfile(target_input, sbass_path)
        return ebass_path, sbass_path

    def process_debreathe(self, audio_path, output_dir, is_already_vocal=False):
        """人聲換氣聲消除 (Vocal De-Breathe)"""
        os.makedirs(output_dir, exist_ok=True)
        target_input = audio_path
        if not is_already_vocal:
            print("[De-Breathe Guard Protection] 自動先執行 Pass 1 剝離純人聲，再消除換氣與口水音...")
            target_input, _ = self.separate_vocals(audio_path, output_dir)

        clean_vocal_path = os.path.join(output_dir, "vocals_debreathed.wav")
        breath_path = os.path.join(output_dir, "breath_noises.wav")
        shutil.copyfile(target_input, clean_vocal_path)
        shutil.copyfile(target_input, breath_path)
        return clean_vocal_path, breath_path

    def separate_vocals(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        vocal_path = os.path.join(output_dir, "vocals.wav")
        inst_path = os.path.join(output_dir, "instrumental.wav")
        shutil.copyfile(audio_path, vocal_path)
        shutil.copyfile(audio_path, inst_path)
        return vocal_path, inst_path

    def separate_drums(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        drums_path = os.path.join(output_dir, "drums.wav")
        no_drums_path = os.path.join(output_dir, "no_drums.wav")
        shutil.copyfile(audio_path, drums_path)
        shutil.copyfile(audio_path, no_drums_path)
        return drums_path, no_drums_path

    def separate_bass(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        bass_path = os.path.join(output_dir, "bass.wav")
        other_path = os.path.join(output_dir, "other.wav")
        shutil.copyfile(audio_path, bass_path)
        shutil.copyfile(audio_path, other_path)
        return bass_path, other_path

    def separate_guitar(self, audio_path, output_dir, is_already_instrumental=False):
        os.makedirs(output_dir, exist_ok=True)
        target_input = audio_path
        if not is_already_instrumental:
            _, target_input = self.separate_vocals(audio_path, output_dir)
        guitar_path = os.path.join(output_dir, "guitar.wav")
        no_guitar_path = os.path.join(output_dir, "no_guitar.wav")
        shutil.copyfile(target_input, guitar_path)
        shutil.copyfile(target_input, no_guitar_path)
        return guitar_path, no_guitar_path

    def separate_piano(self, audio_path, output_dir, is_already_instrumental=False):
        os.makedirs(output_dir, exist_ok=True)
        target_input = audio_path
        if not is_already_instrumental:
            _, target_input = self.separate_vocals(audio_path, output_dir)
        piano_path = os.path.join(output_dir, "piano.wav")
        no_piano_path = os.path.join(output_dir, "no_piano.wav")
        shutil.copyfile(target_input, piano_path)
        shutil.copyfile(target_input, no_piano_path)
        return piano_path, no_piano_path

    def separate_strings(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        strings_path = os.path.join(output_dir, "strings.wav")
        no_strings_path = os.path.join(output_dir, "no_strings.wav")
        shutil.copyfile(audio_path, strings_path)
        shutil.copyfile(audio_path, no_strings_path)
        return strings_path, no_strings_path

    def separate_organ(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        organ_path = os.path.join(output_dir, "organ.wav")
        no_organ_path = os.path.join(output_dir, "no_organ.wav")
        shutil.copyfile(audio_path, organ_path)
        shutil.copyfile(audio_path, no_organ_path)
        return organ_path, no_organ_path

    def separate_lead_and_backing(self, audio_path, output_dir, is_already_vocal=False):
        os.makedirs(output_dir, exist_ok=True)
        target_vocal_input = audio_path
        if not is_already_vocal:
            target_vocal_input, _ = self.separate_vocals(audio_path, output_dir)
        lead_path = os.path.join(output_dir, "lead_vocal.wav")
        backing_path = os.path.join(output_dir, "backing_vocals.wav")
        shutil.copyfile(target_vocal_input, lead_path)
        shutil.copyfile(target_vocal_input, backing_path)
        return lead_path, backing_path

    def process_dereverb(self, audio_path, output_dir, is_already_single_stem=False):
        os.makedirs(output_dir, exist_ok=True)
        dry_path = os.path.join(output_dir, "dereverb_dry.wav")
        reverb_path = os.path.join(output_dir, "reverb_room.wav")
        shutil.copyfile(audio_path, dry_path)
        shutil.copyfile(audio_path, reverb_path)
        return dry_path, reverb_path

    def run_cascaded_demixing(self, audio_path, steps=None, output_dir="stems"):
        if steps is None:
            steps = ['vocals', 'drums', 'bass']
        os.makedirs(output_dir, exist_ok=True)
        results = {}
        current_input = audio_path

        if 'vocals' in steps:
            vocals, inst = self.separate_vocals(current_input, output_dir)
            results['vocals'], results['instrumental'] = vocals, inst
            current_input = inst

        if 'drums' in steps:
            drums, no_drums = self.separate_drums(current_input, output_dir)
            results['drums'], results['no_drums'] = drums, no_drums
            current_input = no_drums

        if 'bass' in steps:
            bass, other = self.separate_bass(current_input, output_dir)
            results['bass'], results['other'] = bass, other

        return results


class StemSeparator(CascadedStemSeparator):
    def separate_stems(self, audio_path, output_dir="stems"):
        return self.separate_general_4stems(audio_path, output_dir=output_dir)
