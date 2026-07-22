import os
import gradio as gr
from beat_tracker import BeatTrackingSystem

tracker = BeatTrackingSystem(use_beatnet=True)

def process_audio(uploaded_file, custom_output_dir):
    """處理上傳的音軌，並將結果儲存至指定的產出資料夾"""
    if uploaded_file is None:
        return "⚠️ 請上傳或選擇音訊檔案！", None, None, None, None, None, None

    output_dir = custom_output_dir.strip() if custom_output_dir and custom_output_dir.strip() else "outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # 執行節拍追蹤與分析 pipeline
    report = tracker.run_full_pipeline(uploaded_file, output_dir=output_dir)

    filename = os.path.basename(uploaded_file)
    summary = f"""### 🎵 音響與節拍分析結果報告: `{filename}`

- **產出目標資料夾**: `{os.path.abspath(output_dir)}`
- **主調 / 調性 (Key)**: `{report['estimated_key']}`
- **平均速度 (Average BPM)**: `{report['average_bpm']}` (範圍: `{report['min_bpm']}` ~ `{report['max_bpm']}`)
- **總小節數 (Total Measures)**: `{report['total_measures']}` 小節
- **總拍數 (Total Beats)**: `{report['total_beats']}` 拍

---
#### 🎼 小節和弦進行 (前 16 小節預覽):
"""
    chords_preview = ""
    for c in report['chord_progression'][:16]:
        chords_preview += f"- **第 {c['measure']:02d} 小節** ({c['start_time']}s~{c['end_time']}s): `{c['chord']}`\n"
    
    if len(report['chord_progression']) > 16:
        chords_preview += f"\n*(已省略其餘 {len(report['chord_progression'])-16} 小節，完整內容請見導出檔案)*"

    full_text = summary + chords_preview

    click_track_path = report["outputs"]["click_track"]
    mix_track_path = report["outputs"]["mix_with_click"]
    midi_path = report["outputs"]["tempo_map_midi"]
    curve_png_path = report["outputs"]["tempo_curve_plot"]
    report_txt_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_report.txt")

    # 寫入文字報告至產出資料夾
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    return (
        full_text,
        curve_png_path,
        mix_track_path,
        click_track_path,
        mix_track_path,
        midi_path,
        report_txt_path
    )

# 構建 Gradio 介面
with gr.Blocks(title="自動動態節拍追蹤系統") as demo:
    gr.Markdown("""
    # 🥁 自動動態節拍追蹤與音樂分析系統
    選擇或拖曳音檔，並指定產出資料夾，自動進行動態節拍追蹤並生成 Click 音軌與 MIDI Tempo Map。
    """)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. 選擇音檔與設定產出資料夾")
            audio_input = gr.File(
                label="🎵 上傳音檔 (支援點擊選檔或拖曳 MP3/WAV/FLAC/M4A)", 
                type="filepath",
                file_types=[".mp3", ".wav", ".flac", ".m4a"]
            )

            output_folder_box = gr.Textbox(
                value=r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs", 
                label="📁 產出目標資料夾路徑 (Output Destination Folder Path)"
            )
            
            analyze_btn = gr.Button("🚀 開始自動追蹤與分析", variant="primary")
            
        with gr.Column(scale=2):
            gr.Markdown("### 2. 分析結果與導出")
            result_markdown = gr.Markdown("### 待分析...")
            tempo_curve_img = gr.Image(label="節拍速度時間變化圖 (BPM Curve)")

    gr.Markdown("### 🎧 音訊試聽與產出檔案")
    with gr.Row():
        mix_audio_player = gr.Audio(label="原曲 + 節拍器打點混合試聽 (Mix Player)")
        click_audio_player = gr.Audio(label="純節拍器打點音軌 (Click Only)")

    with gr.Row():
        file_mix_download = gr.File(label="下載 mix_with_click.wav")
        file_midi_download = gr.File(label="下載 tempo_map.mid (DAW 速度軌)")
        file_report_download = gr.File(label="下載完整文字分析報告")

    # 事件綁定
    analyze_btn.click(
        fn=process_audio,
        inputs=[audio_input, output_folder_box],
        outputs=[
            result_markdown,
            tempo_curve_img,
            mix_audio_player,
            click_audio_player,
            file_mix_download,
            file_midi_download,
            file_report_download
        ]
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)
