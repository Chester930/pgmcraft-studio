"""
PGMCraft Studio: Web GUI Application
Includes:
1. Standalone Media Downloader (URL -> Title Folder -> MP4, MP3, WAV)
2. Standalone Stem Separator (Categorized by Input Prerequisites with Color Icons 🟢 🟡 🔴)
3. PGM Backing Track & Transcription Suite
"""

import os
import tkinter as tk
from tkinter import filedialog
import gradio as gr
from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.workflow.downloaders import URLDownloaderDispatcher

engine = PGMCraftEngine(enable_stem_separation=False)
separator_engine = CascadedStemSeparator()
downloader_dispatcher = URLDownloaderDispatcher()
DEFAULT_OUTPUT_DIR = os.path.abspath("outputs")

SEPARATION_MODES = [
    {"id": "general_4stem", "label": "🟢 通用標準 4-Stem 一鍵分軌 (Vocals, Drums, Bass, Other)"},
    {"id": "general_6stem", "label": "🟢 通用進階 6-Stem 一鍵分軌 (Vocals, Drums, Bass, Guitar, Piano, Other)"},
    {"id": "vocals", "label": "🟢 人聲分離 (BS-Roformer)"},
    {"id": "drums", "label": "🟢 鼓組分離 (HTDemucs FT)"},
    {"id": "bass", "label": "🟢 貝斯分離 (HTDemucs Bass)"},
    {"id": "cascaded", "label": "🟢 全自動遞迴層疊分軌 (Pass 1 人聲 ➔ Pass 2 鼓組 ➔ Pass 3 貝斯)"},
    {"id": "drums_substem", "label": "🟡 鼓組三細分 (Kick 大鼓 / Snare 小鼓 / Hi-Hat 鈸)"},
    {"id": "guitar", "label": "🟡 吉他分離 (BSRNN / HTDemucs 6s)"},
    {"id": "piano", "label": "🟡 鋼琴分離 (UVR-MDX-NET-Piano)"},
    {"id": "strings", "label": "🟡 弦樂分離 (UVR-MDX-NET-Strings)"},
    {"id": "organ", "label": "🟡 風琴分離 (UVR-MDX-NET-Organ)"},
    {"id": "debreathe", "label": "🔴 人聲換氣與口水音消除 (UVR DeBreathe)"},
    {"id": "synth_bass", "label": "🔴 電貝斯 vs 合成 808 低音細分 (SynthBass Split)"},
    {"id": "lead_backing", "label": "🔴 主唱 vs 和聲細分 (BS-Roformer Lead/Backing)"},
    {"id": "dereverb", "label": "🔴 乾聲去殘響 (UVR-DeEcho-DeReverb)"},
]
SEPARATION_MODE_LABELS = {mode["id"]: mode["label"] for mode in SEPARATION_MODES}
SEPARATION_MODE_IDS_BY_LABEL = {mode["label"]: mode["id"] for mode in SEPARATION_MODES}


def resolve_separation_mode_id(separation_mode):
    """將 GUI value 或舊版 label 解析成穩定模式 ID。"""
    if separation_mode in SEPARATION_MODE_LABELS:
        return separation_mode
    if separation_mode in SEPARATION_MODE_IDS_BY_LABEL:
        return SEPARATION_MODE_IDS_BY_LABEL[separation_mode]
    return None

def open_folder_picker(current_path):
    """彈出 OS 原生資料夾選擇視窗"""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askdirectory(
            title="請選擇儲存資料夾", 
            initialdir=current_path if (current_path and os.path.exists(current_path)) else os.getcwd()
        )
        root.destroy()
        if selected:
            return selected
    except Exception as e:
        print(f"[Folder Picker Error] {e}")
    return current_path


def process_standalone_separation(audio_input, separation_mode, custom_output_dir):
    """依據穩定模式 ID 執行對應分軌流程。"""
    if not audio_input:
        return "⚠️ 請上傳音軌檔案！", None, None, None, None

    output_dir = custom_output_dir.strip() if custom_output_dir and custom_output_dir.strip() else "outputs"
    os.makedirs(output_dir, exist_ok=True)
    stem_dir = os.path.join(output_dir, "stems")
    os.makedirs(stem_dir, exist_ok=True)

    status_msg = ""
    vocal_out, drums_out, bass_out, extra_out = None, None, None, None
    mode_id = resolve_separation_mode_id(separation_mode)
    if mode_id is None:
        return f"❌ 不支援的分軌模式: {separation_mode}", None, None, None, None

    # 🟢 通用分軌模式 (可直接上傳原始混音曲 Full Mix)
    if mode_id == "general_4stem":
        res = separator_engine.separate_general_4stems(audio_input, stem_dir, enable_enhancement=True)
        vocal_out, drums_out, bass_out, extra_out = res.get('vocals'), res.get('drums'), res.get('bass'), res.get('other')
        status_msg = f"🎉 完成【通用標準 4-Stem 分離與 EBU R128 響度優化】！\n- 目錄: `{os.path.abspath(stem_dir)}`"

    elif mode_id == "general_6stem":
        res = separator_engine.separate_general_6stems(audio_input, stem_dir, enable_enhancement=True)
        vocal_out, drums_out, bass_out, extra_out = res.get('vocals'), res.get('drums'), res.get('bass'), res.get('other')
        status_msg = (
            "🎉 完成【通用進階 6-Stem 全音色分離與 EBU R128 響度優化】！\n"
            "- 包含: Vocals, Drums, Bass, Guitar, Piano, Other\n"
            f"- 目錄: `{os.path.abspath(stem_dir)}`"
        )

    elif mode_id == "vocals":
        vocal_out, inst_out = separator_engine.separate_vocals(audio_input, stem_dir)
        status_msg = f"✅ 完成【人聲分離】！\n- **純人聲**: `{os.path.basename(vocal_out)}`\n- **無人聲伴奏**: `{os.path.basename(inst_out)}`"
        extra_out = inst_out

    elif mode_id == "drums":
        drums_out, no_drums_out = separator_engine.separate_drums(audio_input, stem_dir)
        status_msg = f"✅ 完成【鼓組分離】！\n- **鼓組軌**: `{os.path.basename(drums_out)}`\n- **無鼓伴奏**: `{os.path.basename(no_drums_out)}`"
        extra_out = no_drums_out

    elif mode_id == "bass":
        bass_out, other_out = separator_engine.separate_bass(audio_input, stem_dir)
        status_msg = f"✅ 完成【貝斯分離】！\n- **貝斯軌**: `{os.path.basename(bass_out)}`\n- **其他伴奏**: `{os.path.basename(other_out)}`"
        extra_out = other_out

    elif mode_id == "cascaded":
        res = separator_engine.run_cascaded_demixing(audio_input, steps=['vocals', 'drums', 'bass'], output_dir=stem_dir)
        vocal_out, drums_out, bass_out, extra_out = res.get('vocals'), res.get('drums'), res.get('bass'), res.get('other')
        status_msg = f"🎉 完成【全自動遞迴層疊分軌】！已儲存至 `{os.path.abspath(stem_dir)}`"

    # 🟡 伴奏/特定軌細分模式 (系統自動防呆：先抽對應分軌)
    elif mode_id == "drums_substem":
        status_msg = "ℹ️ 【鼓組 Guard 啟動】: 輸入為原曲時，系統已自動先執行 Pass 2 提取純鼓組，再精確細分打擊樂！\n\n"
        kick_out, snare_out, hihat_out = separator_engine.separate_drums_substem(audio_input, stem_dir, is_already_drums=False)
        status_msg += f"✅ 完成【鼓組細分】！\n- **大鼓 (Kick)**: `{os.path.basename(kick_out)}`\n- **小鼓 (Snare)**: `{os.path.basename(snare_out)}`\n- **鈸聲 (Hi-Hat)**: `{os.path.basename(hihat_out)}`"
        drums_out, bass_out, extra_out = kick_out, snare_out, hihat_out

    elif mode_id == "guitar":
        status_msg = "ℹ️ 【防呆保護啟動】: 檢測到輸入為原曲，系統已自動先執行 Pass 1 去人聲，確保吉他分離精度 SDR +2.5dB！\n\n"
        guitar_out, no_guitar_out = separator_engine.separate_guitar(audio_input, stem_dir, is_already_instrumental=False)
        status_msg += f"✅ 完成【吉他分離】！\n- **吉他獨奏**: `{os.path.basename(guitar_out)}`\n- **無吉他伴奏**: `{os.path.basename(no_guitar_out)}`"
        extra_out = guitar_out

    elif mode_id == "piano":
        status_msg = "ℹ️ 【防呆保護啟動】: 檢測到輸入為原曲，系統已自動先執行 Pass 1 去人聲，避免人聲干擾鋼琴泛音！\n\n"
        piano_out, no_piano_out = separator_engine.separate_piano(audio_input, stem_dir, is_already_instrumental=False)
        status_msg += f"✅ 完成【鋼琴分離】！\n- **鋼琴軌**: `{os.path.basename(piano_out)}`\n- **無鋼琴伴奏**: `{os.path.basename(no_piano_out)}`"
        extra_out = piano_out

    elif mode_id == "strings":
        strings_out, no_strings_out = separator_engine.separate_strings(audio_input, stem_dir)
        status_msg = f"✅ 完成【弦樂分離】！\n- **弦樂聲部**: `{os.path.basename(strings_out)}`\n- **無弦樂伴奏**: `{os.path.basename(no_strings_out)}`"
        extra_out = strings_out

    elif mode_id == "organ":
        organ_out, no_organ_out = separator_engine.separate_organ(audio_input, stem_dir)
        status_msg = f"✅ 完成【風琴分離】！\n- **風琴聲部**: `{os.path.basename(organ_out)}`\n- **無風琴伴奏**: `{os.path.basename(no_organ_out)}`"
        extra_out = organ_out

    # 🔴 高前置條件特化模式 (系統自動防呆：需純人聲/單一音軌)
    elif mode_id == "debreathe":
        status_msg = "ℹ️ 【人聲 Guard 啟動】: 檢測到輸入為原曲，系統已自動先執行 Pass 1 剝離純人聲，再消除換氣聲！\n\n"
        clean_vocal, breath_out = separator_engine.process_debreathe(audio_input, stem_dir, is_already_vocal=False)
        status_msg += f"✅ 完成【人聲去換氣聲】！\n- **無換氣聲純人聲**: `{os.path.basename(clean_vocal)}`\n- **吸氣/換氣聲音軌**: `{os.path.basename(breath_out)}`"
        vocal_out, extra_out = clean_vocal, breath_out

    elif mode_id == "synth_bass":
        status_msg = "ℹ️ 【貝斯 Guard 啟動】: 檢測到輸入為原曲，系統已自動先執行 Pass 3 提取純貝斯，再細分電貝斯與 808！\n\n"
        ebass_out, sbass_out = separator_engine.separate_synth_and_electric_bass(audio_input, stem_dir, is_already_bass=False)
        status_msg += f"✅ 完成【貝斯細分】！\n- **真實電貝斯**: `{os.path.basename(ebass_out)}`\n- **808/合成低音**: `{os.path.basename(sbass_out)}`"
        bass_out, extra_out = ebass_out, sbass_out

    elif mode_id == "lead_backing":
        status_msg = "ℹ️ 【極高前置保護啟動】: 本模型要求純人聲。輸入為原曲時，系統自動先剝離純人聲，再拆解主唱與和聲！\n\n"
        lead_out, backing_out = separator_engine.separate_lead_and_backing(audio_input, stem_dir, is_already_vocal=False)
        status_msg += f"✅ 完成【主唱與和聲拆解】！\n- **單獨主唱**: `{os.path.basename(lead_out)}`\n- **背景和聲**: `{os.path.basename(backing_out)}`"
        vocal_out, extra_out = lead_out, backing_out

    elif mode_id == "dereverb":
        dry_out, room_out = separator_engine.process_dereverb(audio_input, stem_dir, is_already_single_stem=False)
        status_msg = f"✅ 完成【去殘響處理】！\n- **無迴音乾聲**: `{os.path.basename(dry_out)}`\n- **房間迴音成分**: `{os.path.basename(room_out)}`"
        extra_out = dry_out

    return status_msg, vocal_out, drums_out, bass_out, extra_out


def standalone_download(url_input, custom_output_dir):
    if not url_input or not url_input.strip():
        return "⚠️ 請輸入有效的影片或音訊網址！", None, None, None

    output_dir = custom_output_dir.strip() if custom_output_dir and custom_output_dir.strip() else "outputs"
    os.makedirs(output_dir, exist_ok=True)

    try:
        res = downloader_dispatcher.dispatch_and_download(url_input.strip(), output_dir)
        folder = res.get("folder")
        wav = res.get("wav")
        mp3 = res.get("mp3")
        mp4 = res.get("mp4")
        title = res.get("title")

        status_msg = f"""### 🎉 下載與轉換完成！

- **媒體標題**: `{title}`
- **儲存資料夾目錄**: `{os.path.abspath(folder)}`

---
#### 📦 資料夾內包含的 3 個檔案：
1. **最高畫質影片**: `{os.path.basename(mp4) if mp4 else '無'}`
2. **無損 PCM 音訊 (WAV)**: `{os.path.basename(wav) if wav else '無'}`
3. **高音質壓縮音訊 (MP3)**: `{os.path.basename(mp3) if mp3 else '無'}`
"""
        return status_msg, mp4, wav, mp3

    except Exception as e:
        return f"❌ 下載過程發生錯誤: {e}", None, None, None


def process_pgm(url_input, audio_file, enable_stem, custom_output_dir):
    input_source = None
    if url_input and url_input.strip():
        input_source = url_input.strip()
    elif audio_file is not None:
        input_source = audio_file

    if not input_source:
        return "⚠️ 請輸入影片/音訊 URL 或選擇上傳本地檔！", None, None, None, None, None, None, None

    output_dir = custom_output_dir.strip() if custom_output_dir and custom_output_dir.strip() else "outputs"
    os.makedirs(output_dir, exist_ok=True)

    engine.enable_stem_separation = enable_stem
    report = engine.run(input_source, output_dir=output_dir)

    filename = os.path.basename(report.get("audio_file", "audio"))
    summary = f"""# 🎛️ PGMCraft Studio 分析與 PGM 報告: `{filename}`

- **輸入來源**: `{input_source}`
- **產出目標目錄**: `{os.path.abspath(output_dir)}`
- **樂曲調性 (Key)**: `{report['estimated_key']}`
- **平均速度 (BPM)**: `{report['average_bpm']}` (`{report['min_bpm']}` ~ `{report['max_bpm']}`)
- **總小節數**: `{report['total_measures']}` 小節
- **總拍數**: `{report['total_beats']}` 拍

---
### 🎸 抓譜和弦進行預覽 (前 16 小節):
"""
    chords_preview = ""
    for c in report['chord_progression'][:16]:
        chords_preview += f"- **第 {c['measure']:02d} 小節** ({c['start_time']}s ~ {c['end_time']}s): `{c['chord']}`\n"

    if len(report['chord_progression']) > 16:
        chords_preview += f"\n*(已省略其餘 {len(report['chord_progression'])-16} 小節)*"

    full_text = summary + chords_preview
    report_txt_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_pgm_report.txt")
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    return (
        full_text,
        report["outputs"]["tempo_curve_plot"],
        report["outputs"]["mix_with_click"],
        report["outputs"]["click_track"],
        report["outputs"]["mix_with_click"],
        report["outputs"]["tempo_map_midi"],
        report["outputs"]["click_guide_midi"],
        report_txt_path
    )


# 建立 Gradio Web App
with gr.Blocks(title="PGMCraft Studio - AI 音訊分軌、採譜與 PGM 製作套件") as demo:
    gr.Markdown("""
    # 🎛️ PGMCraft Studio
    ### AI 音訊分軌 · 音樂人採譜助手 · 現場 PGM 節目軌與 Click 音軌生成系統
    """)

    with gr.Tabs():
        # 頁籤 1: 獨立影音下載區塊
        with gr.TabItem("📥 獨立影音無損下載區塊"):
            gr.Markdown("### 🔗 貼上網址自動建立專屬資料夾並下載 MP4 / MP3 / WAV 檔案")
            with gr.Row():
                with gr.Column(scale=1):
                    dl_url_input = gr.Textbox(
                        label="🌐 影音/社群網址 (YouTube / Bilibili / IG Reels / TikTok / FB Watch)",
                        placeholder="https://www.youtube.com/watch?v=..."
                    )
                    with gr.Row():
                        dl_output_dir = gr.Textbox(
                            value=DEFAULT_OUTPUT_DIR,
                            label="📁 儲存位置根目錄 (Root Output Folder)",
                            scale=4
                        )
                        dl_browse_btn = gr.Button("📂 選擇資料夾", variant="secondary", scale=1)

                    dl_start_btn = gr.Button("🚀 開始下載並建立媒體資料夾", variant="primary")

                with gr.Column(scale=1):
                    dl_status_markdown = gr.Markdown("### 待下載...")
                    with gr.Row():
                        file_mp4_dl = gr.File(label="下載 MP4 影片檔")
                        file_wav_dl = gr.File(label="下載無損 WAV 音檔")
                        file_mp3_dl = gr.File(label="下載 MP3 音檔")

            dl_browse_btn.click(
                fn=open_folder_picker,
                inputs=[dl_output_dir],
                outputs=[dl_output_dir]
            )

            dl_start_btn.click(
                fn=standalone_download,
                inputs=[dl_url_input, dl_output_dir],
                outputs=[dl_status_markdown, file_mp4_dl, file_wav_dl, file_mp3_dl]
            )

        # 頁籤 2: 獨立音色分軌區塊 (顏色標記前置等級 🟢 通用 / 🟡 伴奏 / 🔴 特化)
        with gr.TabItem("🎛️ 獨立音色分軌工作區"):
            gr.Markdown("""
            ### 🎚️ 按前置要求分級的分軌工作區
            - 🟢 **通用模式**: 可直接傳入原始混音檔 (Full Mix)。
            - 🟡 **伴奏模式**: 建議傳入純伴奏/純鼓組。(若傳原曲，系統**自動防呆先行抽軌**)
            - 🔴 **特化模式**: 需純人聲/純貝斯/單一分軌。(若傳原曲，系統**自動啟動人聲/貝斯防呆保護**)
            """)
            with gr.Row():
                with gr.Column(scale=1):
                    stem_audio_input = gr.File(
                        label="🎵 選擇音檔 (MP3/WAV/FLAC/M4A)",
                        type="filepath",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"]
                    )
                    stem_mode_select = gr.Dropdown(
                        choices=[(mode["label"], mode["id"]) for mode in SEPARATION_MODES],
                        value="general_4stem",
                        label="🎯 選擇分軌模式 (標有色塊說明前置要求等級)"
                    )
                    with gr.Row():
                        stem_output_dir = gr.Textbox(
                            value=DEFAULT_OUTPUT_DIR,
                            label="📁 分軌產出資料夾 (Stems Output Folder)",
                            scale=4
                        )
                        stem_browse_btn = gr.Button("📂 選擇資料夾", variant="secondary", scale=1)

                    stem_start_btn = gr.Button("🚀 執行獨立音色分軌", variant="primary")

                with gr.Column(scale=1):
                    stem_status_markdown = gr.Markdown("### 待分軌...")
                    file_stem_vocal = gr.File(label="人聲 / 主唱 / 大鼓 / 電貝斯 (Vocals.wav)")
                    file_stem_drums = gr.File(label="鼓組 / 吉他 / 鋼琴 / 小鼓 (Drums.wav)")
                    file_stem_bass = gr.File(label="貝斯 / 弦樂 / 風琴 / 鈸聲 (Bass.wav)")
                    file_stem_extra = gr.File(label="伴奏 / Other / 和聲 / 808 / 換氣 / 乾聲 (Other.wav)")

            stem_browse_btn.click(
                fn=open_folder_picker,
                inputs=[stem_output_dir],
                outputs=[stem_output_dir]
            )

            stem_start_btn.click(
                fn=process_standalone_separation,
                inputs=[stem_audio_input, stem_mode_select, stem_output_dir],
                outputs=[stem_status_markdown, file_stem_vocal, file_stem_drums, file_stem_bass, file_stem_extra]
            )

        # 頁籤 3: 完整 PGM 採譜與分析管道
        with gr.TabItem("🎛️ PGM 節目軌與採譜分析"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. 影音來源與 PGM 設定")
                    pgm_url_box = gr.Textbox(
                        label="🌐 貼上影片/音訊 URL (YouTube / Bilibili / NicoNico / SoundCloud / HTTP 直連)",
                        placeholder="https://www.youtube.com/watch?v=..."
                    )
                    pgm_audio_input = gr.File(
                        label="📁 或拖曳上傳本地檔 (MP3/WAV/FLAC/M4A)", 
                        type="filepath",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"]
                    )
                    enable_stem_chk = gr.Checkbox(
                        label="🥁 開啟 Stem 鼓組/人聲分離 (分離後提高動態節拍精度)", 
                        value=False
                    )
                    with gr.Row():
                        output_folder_box = gr.Textbox(
                            value=DEFAULT_OUTPUT_DIR, 
                            label="📁 PGM 專案產出資料夾 (Output Directory)",
                            scale=4
                        )
                        pgm_browse_btn = gr.Button("📂 選擇資料夾", variant="secondary", scale=1)

                    analyze_btn = gr.Button("🚀 產生 PGM 專案檔與採譜分析", variant="primary")

                with gr.Column(scale=2):
                    gr.Markdown("### 2. 採譜分析與速度曲線")
                    result_markdown = gr.Markdown("### 待分析...")
                    tempo_curve_img = gr.Image(label="PGM 速度變化曲線圖 (Tempo Profile)")

            gr.Markdown("### 🎧 PGM 音軌試聽與導出檔")
            with gr.Row():
                mix_audio_player = gr.Audio(label="PGM 節目軌 + Click 試聽 (Mix Player)")
                click_audio_player = gr.Audio(label="耳監 Click 打點軌 (Click Only)")

            with gr.Row():
                file_mix_download = gr.File(label="下載 mix_with_click.wav")
                file_midi_download = gr.File(label="下載 tempo_map.mid (DAW 速度軌)")
                file_click_midi_download = gr.File(label="下載 click_guide.mid (MIDI Click)")
                file_report_download = gr.File(label="下載 PGM 分析報告")

            pgm_browse_btn.click(
                fn=open_folder_picker,
                inputs=[output_folder_box],
                outputs=[output_folder_box]
            )

            analyze_btn.click(
                fn=process_pgm,
                inputs=[pgm_url_box, pgm_audio_input, enable_stem_chk, output_folder_box],
                outputs=[
                    result_markdown,
                    tempo_curve_img,
                    mix_audio_player,
                    click_audio_player,
                    file_mix_download,
                    file_midi_download,
                    file_click_midi_download,
                    file_report_download
                ]
            )

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1", 
        server_port=7860, 
        share=False,
        allowed_paths=[os.getcwd(), DEFAULT_OUTPUT_DIR]
    )
