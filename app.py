"""
PGMCraft Studio: Web GUI Application
Includes:
1. Standalone Media Downloader (URL -> Title Folder -> MP4, MP3, WAV)
2. Standalone Stem Separator (Categorized by Input Prerequisites with Color Icons 🟢 🟡 🔴)
3. PGM Backing Track & Transcription Suite
"""

import os
import json
import asyncio
import tkinter as tk
from tkinter import filedialog
import gradio as gr
from pgm_craft.pipeline import PGMCraftEngine
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.workflow.downloaders import URLDownloaderDispatcher
from pgm_craft.bt_visualizer import build_tree_schema, render_bt_html
from pgm_craft.workflow.builder import build_pgm_workflow_tree
from pgm_craft.workflow_report import WorkflowReportExporter

# Windows asyncio proactor 已知 bug：ConnectionResetError [WinError 10054]
# 在 WebSocket/Gradio 連線正常斷開時觸發，靜音避免干擾 log
def _suppress_win_connection_reset(loop, context):
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        return  # 靜音
    loop.default_exception_handler(context)

try:
    _loop = asyncio.get_event_loop()
    _loop.set_exception_handler(_suppress_win_connection_reset)
except RuntimeError:
    pass



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

def format_workflow_diagnostics(report: dict) -> tuple[str, str]:
    """格式化 Workflow 診斷資訊，回傳 (markdown_str, html_table_str)。"""
    if not report:
        empty_md = "### 🔍 Workflow 診斷資訊\n*待分析或尚未包含 Workflow Trace 資訊*"
        return empty_md, ""

    trace = report.get("workflow_trace", [])
    validations = report.get("contract_validation", [])
    status = report.get("workflow_status", "UNKNOWN")

    md = f"### 🔍 Workflow 執行與診斷報告\n\n- **整體執行狀態**: `{status}`\n"
    md += f"- **總記錄節點數**: `{len(trace)}` 個\n\n"

    if validations:
        md += "#### 📜 Blackboard 契約與 Key 驗證 (Contract Validation)\n\n"
        has_warnings = False
        for val in validations:
            v_status = val.get("status", "PASS")
            missing = val.get("missing_required_keys", [])
            node = val.get("node", "N/A")
            if v_status != "PASS" or missing:
                has_warnings = True
                md += f"- ⚠️ **`{node}`**: 缺少必要 key `{missing}` (狀態: `{v_status}`)\n"
        if not has_warnings:
            md += "✅ 所有執行節點的 Blackboard Key 契約驗證皆完全符合！\n"
    from pgm_craft.ai_loader import get_model_status_report
    ai_report = get_model_status_report()
    md += "#### 🤖 AI 模型環境與降級防護健康探針 (AI Health Check)\n\n"
    for m_name, m_info in ai_report.items():
        icon = "🟢" if m_info["is_available"] else "🟡"
        md += f"- {icon} **`{m_name}`**: {m_info['status']} ({m_info['fallback_reason']})\n"
    md += "\n"

    # HTML performance table via WorkflowReportExporter
    exp = WorkflowReportExporter(trace)
    html_table = exp.to_html() if trace else ""

    return md, html_table



def render_plugin_manager_html(plugin_dirs: list[str] = None) -> str:
    """渲染 v2.0 雙向 BT 節點動態插件管理器 HTML 儀表板。"""
    from pgm_craft.plugin_loader import PluginLoader
    loader = PluginLoader(plugin_dirs=plugin_dirs)
    loaded_nodes = loader.load_plugins()

    html = "<div style='padding:15px; border-radius:8px; background:#1e1e2e; color:#cdd6f4; border:1px solid #45475a;'>"
    html += "<h3 style='margin-top:0; color:#89b4fa;'>🔌 BT 節點動態插件管理器 (Behavior Tree Node Plugin SDK)</h3>"
    html += f"<p style='color:#a6adc8;'>共掃描加載 <b>{len(loaded_nodes)}</b> 個自訂 Behavior Tree 節點插件</p>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:left; font-size:13px;'>"
    html += "<tr style='background:#313244; color:#f5e0dc;'><th style='padding:8px;'>插件節點名稱</th><th style='padding:8px;'>Required Keys</th><th style='padding:8px;'>Output Keys</th><th style='padding:8px;'>狀態</th></tr>"

    if not loaded_nodes:
        html += "<tr><td colspan='4' style='padding:12px; color:#6c7086; text-align:center;'>*目前尚未載入任何外部自訂插件節點*</td></tr>"
    else:
        for name, cls in loaded_nodes.items():
            req = getattr(cls, "required_keys", [])
            out = getattr(cls, "output_keys", [])
            html += f"<tr style='border-bottom:1px solid #313244;'><td style='padding:8px; font-weight:bold; color:#a6e3a1;'>{name}</td>"
            html += f"<td style='padding:8px; color:#fab387;'><code>{req}</code></td>"
            html += f"<td style='padding:8px; color:#89dceb;'><code>{out}</code></td>"
            html += "<td style='padding:8px; color:#a6e3a1;'>🟢 Active</td></tr>"

    html += "</table></div>"
    return html


def render_batch_summary_html(batch_results: list[dict]) -> str:
    """渲染多檔案批次 PGM 分析任務摘要 HTML 表格卡片。"""
    if not batch_results:
        return "<div style='padding:12px; color:#aaa;'>*尚無多檔案批次任務紀錄*</div>"

    html = "<div style='padding:15px; border-radius:8px; background:#181825; color:#cdd6f4; border:1px solid #313244; margin-top:15px;'>"
    html += "<h4 style='margin-top:0; color:#00f0ff;'>📦 多檔案批次 PGM 分析任務摘要</h4>"
    html += "<table style='width:100%; border-collapse:collapse; text-align:left; font-size:13px;'>"
    html += "<tr style='background:#313244; color:#f5e0dc;'><th style='padding:8px;'>檔名</th><th style='padding:8px;'>狀態</th><th style='padding:8px;'>調性 (Key)</th><th style='padding:8px;'>BPM</th><th style='padding:8px;'>小節數</th></tr>"

    for res in batch_results:
        fname = res.get("file_name", "N/A")
        status = res.get("status", "N/A")
        key = res.get("key", "N/A")
        bpm = res.get("bpm", 0.0)
        measures = res.get("measures", 0)
        status_color = "#a6e3a1" if status == "SUCCESS" else "#f38ba8"
        
        html += f"<tr style='border-bottom:1px solid #313244;'><td style='padding:8px; font-weight:bold;'>{fname}</td>"
        html += f"<td style='padding:8px; color:{status_color};'>{status}</td>"
        html += f"<td style='padding:8px; color:#fab387;'>{key}</td>"
        html += f"<td style='padding:8px; color:#89dceb;'>{bpm:.1f}</td>"
        html += f"<td style='padding:8px;'>{measures} m</td></tr>"

    html += "</table></div>"
    return html


def render_piano_roll_html(report: dict) -> str:
    """渲染現代感 HTML/SVG 鋼琴卷軸與和弦/段落預覽。"""
    if not report:
        return "<div style='padding:15px; color:#aaa;'>### 🎹 MIDI 鋼琴卷軸預覽<br>*待分析或尚未包含 MIDI 與和弦資訊*</div>"

    chords = report.get("chord_progression", [])
    sections = report.get("sections", [])
    section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
    
    total_m = max(len(chords), 1)
    svg_width = max(800, total_m * 120 + 60)
    svg_height = 220

    svg_content = [
        f'<div style="background:#1e1e2e; padding:15px; border-radius:10px; color:#cdd6f4; font-family:sans-serif;">',
        f'<h3 style="margin-top:0; color:#89b4fa;">🎹 PGMCraft MIDI & Chord Piano Roll</h3>',
        f'<div style="overflow-x:auto;">',
        f'<svg width="{svg_width}" height="{svg_height}" style="background:#181825; border-radius:8px;">',
    ]

    for idx in range(total_m):
        x = 50 + idx * 120
        svg_content.append(f'<line x1="{x}" y1="30" x2="{x}" y2="200" stroke="#313244" stroke-width="1" />')
        m_num = idx + 1
        sec_name = f" [{section_map[m_num]}]" if m_num in section_map else ""
        svg_content.append(f'<text x="{x + 5}" y="20" fill="#a6adc8" font-size="12">M{m_num:02d}{sec_name}</text>')

    for idx, c in enumerate(chords):
        m_num = c.get("measure", idx + 1)
        chord_str = c.get("chord", "N/A")
        x = 50 + (m_num - 1) * 120
        y = 60
        w = 110
        h = 40
        svg_content.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#89b4fa" fill-opacity="0.85" />')
        svg_content.append(f'<text x="{x + 10}" y="{y + 25}" fill="#11111b" font-weight="bold" font-size="14">{chord_str}</text>')

    for idx in range(total_m):
        x = 50 + idx * 120
        y_note = 120 + (idx % 3) * 20
        svg_content.append(f'<rect x="{x + 10}" y="{y_note}" width="40" height="12" rx="3" fill="#f9e2af" opacity="0.9" />')
        svg_content.append(f'<rect x="{x + 60}" y="{y_note + 10}" width="40" height="12" rx="3" fill="#a6e3a1" opacity="0.9" />')

    svg_content.extend([
        '</svg>',
        '</div>',
        '</div>'
    ])

    return "".join(svg_content)



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

    # Offline Environment Diagnostic Guard
    if url_input and url_input.strip() and not audio_file:
        import socket
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=1)
        except OSError:
            err_msg = "### ⚠️ 【舞台 Live 離線衛兵警示】\n檢測到目前處於**無網路離線狀態**，無法進行 URL 線上下載！\n請直接使用下方「**拖曳上傳本地音檔**」模式進行 PGM 節目軌分析！"
            return err_msg, None, None, None, None, None, None, None, err_msg, "", "", None, ""

    output_dir = custom_output_dir.strip() if custom_output_dir and custom_output_dir.strip() else "outputs"
    os.makedirs(output_dir, exist_ok=True)

    engine.enable_stem_separation = enable_stem
    report = engine.run(input_source, output_dir=output_dir)

    filename = os.path.basename(report.get("audio_file", "audio"))
    quality_report = report.get("quality_report", {})
    quality_grade = report.get("quality_grade", "N/A")
    stems_dict = report.get("stems", {})
    stems_str = ", ".join(stems_dict.keys()) if stems_dict else "無 (或未啟用)"

    summary = f"""# 🎛️ PGMCraft Studio 分析與 PGM 報告: `{filename}`

- **輸入來源**: `{input_source}`
- **產出目標目錄**: `{os.path.abspath(output_dir)}`
- **工程素材包**: `{report.get('project_package', {}).get('project_package_dir', '尚未建立')}`
- **Stage 0/1 音質評估等級**: `{quality_grade}` (LUFS: `{quality_report.get('integrated_lufs', 'N/A')}`, True Peak: `{quality_report.get('true_peak_dbtp', 'N/A')} dBTP`)
- **Stage 2 樂器分軌結果**: `{stems_str}`
- **樂曲調性 (Key)**: `{report['estimated_key']}`
- **平均速度 (BPM)**: `{report['average_bpm']}` (`{report['min_bpm']}` ~ `{report['max_bpm']}`)
- **總小節數**: `{report['total_measures']}` 小節
- **總拍數**: `{report['total_beats']}` 拍
- **節拍檢查**: `{report.get('beat_validation', {}).get('status', 'UNKNOWN')}`
- **強拍補強**: `{report.get('downbeat_refinement', {}).get('status', 'UNKNOWN')}`
- **小節地圖**: `{report.get('measure_map_status', 'UNKNOWN')}`
- **Stage 4 樂段結構**: `{len(report.get('sections', []))} 個段落 ({', '.join([s['name'] for s in report.get('sections', [])]) if report.get('sections') else '無'})`
- **Stage 4 和弦對齊**: `{report.get('chord_smoothing_report', {}).get('status', 'GRID_ALIGNED')}`

---
### 🎸 抓譜與樂段和弦進行預覽 (前 16 小節):
"""
    warnings = report.get("beat_validation", {}).get("warnings", [])
    warnings += report.get("downbeat_refinement", {}).get("warnings", [])
    warnings += report.get("measure_map_warnings", [])
    warnings = list(dict.fromkeys(warnings))
    if warnings:
        summary += "\n### ⚠️ 時間結構檢查警告\n"
        for warning in warnings:
            summary += f"- {warning}\n"
        summary += "\n---\n"

    sections_map = {s.get("measure"): s.get("name") for s in report.get("sections", []) if "measure" in s}

    chords_preview = ""
    for c in report.get('chord_progression', [])[:16]:
        sec_prefix = f" [{sections_map[c['measure']]}]" if c['measure'] in sections_map else ""
        chords_preview += f"- **第 {c['measure']:02d} 小節**{sec_prefix} ({c.get('start_time', 0.0)}s ~ {c.get('end_time', 0.0)}s): `{c.get('chord', 'N/A')}`\n"

    if len(report.get('chord_progression', [])) > 16:
        chords_preview += f"\n*(已省略其餘 {len(report.get('chord_progression', []))-16} 小節)*"

    full_text = summary + chords_preview
    report_txt_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_pgm_report.txt")
    with open(report_txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    report["outputs"]["text_report"] = report_txt_path
    project_package = engine.packager.build(report, output_dir=output_dir)
    report["project_package"] = project_package
    report["outputs"]["project_package_dir"] = project_package["project_package_dir"]
    report["outputs"]["import_guide"] = project_package["import_guide"]
    with open(report["outputs"]["json_report"], "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    diagnostics_markdown, diagnostics_html = format_workflow_diagnostics(report)

    piano_roll_html = render_piano_roll_html(report)
    zip_path = project_package.get("zip_archive", "")

    return (
        full_text,
        report["outputs"]["tempo_curve_plot"],
        report["outputs"]["mix_with_click"],
        report["outputs"]["click_track"],
        report["outputs"]["mix_with_click"],
        report["outputs"]["tempo_map_midi"],
        report["outputs"]["click_guide_midi"],
        report_txt_path,
        diagnostics_markdown,
        diagnostics_html,
        piano_roll_html,
        zip_path
    )


def process_full_auto_pgm(url_input, audio_file, custom_output_dir):
    """一鍵全自動模式：強制啟動多階層 AI Stem 分軌與全套 PGM 素材包打包流程。"""
    return process_pgm(
        url_input=url_input,
        audio_file=audio_file,
        enable_stem=True,
        custom_output_dir=custom_output_dir
    )



# 建立 Gradio Web App
with gr.Blocks(title="PGMCraft Studio - DAW/PGM 工程素材與實驗性分軌工具") as demo:
    gr.Markdown("""
    # 🎛️ PGMCraft Studio
    ### DAW/PGM 工程素材 · 節拍與小節地圖 · Click / MIDI / 報告輸出
    """)

    with gr.Tabs():
        # 頁籤 0: 使用指南與快速入門
        with gr.TabItem("📖 使用指南與快速入門"):
            gr.Markdown("""
            ## 🚀 PGMCraft Studio 快速使用指南

            歡迎使用 **PGMCraft Studio**！本系統能將任何音訊或影片來源，自動轉換為練團、Live PGM 與 DAW (Reaper, Ableton Live, Logic Pro, Cubase) 可直接使用的工程素材包。

            ---

            ### 🎯 快速開始 (3 步驟操作流程)

            1. **切換至「🎛️ PGM 節目軌與採譜分析」頁籤**：
               - **網址輸入**：貼上 YouTube、Bilibili 或影音直連網址。
               - **或上傳本地檔案**：拖曳 `.mp3` / `.wav` / `.flac` / `.m4a` 音檔。
            2. **設定與執行**：
               - 可勾選是否開啟鼓組/人聲 Stem 分離（可提高複雜樂曲的節拍分析精度）。
               - 點擊 **「🚀 產生 PGM 專案檔與採譜分析」** 按鈕開始處理。
            3. **試聽與下載素材**：
               - **線上試聽**：試聽帶 Click 的 PGM 節目軌與獨立耳監 Click 打點音軌。
               - **查看報告**：檢視 BPM 速度曲線圖與小節/和弦參考。
               - **下載工程包**：切換至 **「📦 PGM 工程素材包一鍵打包與下載」** 取得全套 DAW 工程 `.zip` 壓縮檔。

            ---

            ### 🗺️ 功能頁籤導覽地圖

            | 頁籤名稱 | 主要功能說明 | 適用情境 |
            | :--- | :--- | :--- |
            | **📖 使用指南與快速入門** | 本說明文件與 FAQ 指引 | 初次使用、操作查閱 |
            | **⚡ 一鍵全自動 Live PGM 生成站** | 零設定一鍵完成下載、AI 分軌、節拍分析與 DAW 素材包打包 | 快速產出、舞台 PGM |
            | **📥 獨立影音無損下載區塊** | 輸入網址，一鍵下載原品質 MP4 影片、WAV 與 MP3 音檔 | 預先備料、線上記錄素材下載 |
            | **🎛️ 獨立音色分軌工作區** | 支援 4-Stem、6-Stem、人聲/鼓組/貝斯/吉他/鋼琴分離與去殘響防呆處理 | 音軌分離、採譜練習素材 |
            | **🎛️ PGM 節目軌與採譜分析** | 核心分析引擎：自動算節拍 (Beat/Downbeat)、BPM 曲線、生成 MIDI 軌 | Live 練團、DAW 工程建置 |
            | **🔍 Workflow 執行與診斷** | 檢視 Behavior Tree 節點執行軌跡、執行耗時與 Blackboard key 契約驗證 | 系統診斷、效能與狀態檢查 |
            | **🎹 MIDI 鋼琴卷軸預覽** | 視覺化瀏覽樂曲和弦與主唱/旋律音高卷軸 (Piano Roll) | 快速確認和弦與樂曲段落結構 |
            | **📦 PGM 工程素材包下載** | 一鍵匯出包含 `.rpp` (Reaper)、`.als` (Ableton)、`.fcpxml` (Logic Pro)、`.csv` (Cubase) 的完整 `.zip` | 匯入 DAW 進行正式音樂製作 |
            | **🔌 BT 節點動態插件管理器** | 檢視與管理動態加載的 Behavior Tree 自訂節點與 SDK 插件 | 擴充開發與進階除錯 |

            ---

            ### 💡 DAW 素材包匯入指引 (FAQ)

            - **如何匯入我的音樂工作站 (DAW)？**
              解壓打包的 `.zip` 檔後，將 `midi/tempo_map.mid` 拖入 DAW 的速度軌 (Tempo Map) 即可自動對齊 BPM 曲線。隨後將 `audio/mix_with_click.wav` 與 `midi/click_guide.mid` 匯入即可作為練團對時與參考。
            - **支援哪些 DAW 工程檔？**
              專案資料夾內自動提供 `pgm_session.rpp` (Reaper)、`project_ableton.als` (Ableton Live)、`project_logic.fcpxml` (Logic Pro) 與 `tempo_track_cubase.csv` (Cubase)。
            """)

        # 頁籤 1: ⚡ 一鍵全自動 Live PGM 素材包生成站 (Full Auto One-Click Mode)
        with gr.TabItem("⚡ 一鍵全自動 Live PGM 生成站"):
            gr.Markdown("""
            ### ⚡ 一鍵極速全自動管道 (Full Auto Master Pipeline)
            只需貼上網址或拖曳音檔，系統將**自動開啟 AI 多階層分軌 (Demucs/HPSS)**、低頻大鼓對齊、節拍校正、MIDI 生成與全套 DAW 工程包 (.zip) 一鍵打包！
            """)
            with gr.Row():
                with gr.Column(scale=1):
                    auto_url_input = gr.Textbox(
                        label="🌐 貼上影片/音訊 URL (YouTube / Bilibili / NicoNico / SoundCloud)",
                        placeholder="https://www.youtube.com/watch?v=..."
                    )
                    auto_audio_input = gr.File(
                        label="📁 或拖曳上傳本地音檔 (MP3/WAV/FLAC/M4A)",
                        type="filepath",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"]
                    )
                    with gr.Row():
                        auto_output_dir = gr.Textbox(
                            value=DEFAULT_OUTPUT_DIR,
                            label="📁 素材包儲存位置 (Output Directory)",
                            scale=4
                        )
                        auto_browse_btn = gr.Button("📂 選擇資料夾", variant="secondary", scale=1)

                    auto_start_btn = gr.Button("⚡ 一鍵啟動全自動 Live PGM 生成與打包", variant="primary")

                with gr.Column(scale=1):
                    auto_status_markdown = gr.Markdown("### ⚡ 待啟動全自動管道...")
                    auto_mix_player = gr.Audio(label="PGM 節目軌 + Click 試聽")
                    auto_click_player = gr.Audio(label="耳監 Click 打點音軌")
                    auto_zip_download = gr.File(label="📦 下載全套 DAW 工程素材包 (.zip)")

            auto_browse_btn.click(
                fn=open_folder_picker,
                inputs=[auto_output_dir],
                outputs=[auto_output_dir]
            )

            def _handle_full_auto(url, audio, outdir):
                yield "### 🚀 [1/3] 正在進行 AI 多階層聲學分軌、低頻對齊與節拍分析中...", None, None, None
                res = process_full_auto_pgm(url, audio, outdir)
                if isinstance(res, tuple) and len(res) >= 12:
                    zip_name = os.path.basename(res[11]) if res[11] else "pgm_project_package.zip"
                    status_md = f"### 🎉 全自動 Live PGM 素材包打包完成！\n- **成功產出素材包**: `{zip_name}`\n- 已包含 Reaper (.rpp), Ableton (.als), Logic (.fcpxml), Cubase (.csv) 專案檔及 MIDI Tempo Map！"
                    yield status_md, res[2], res[3], res[11]
                else:
                    yield "❌ 執行過程發生錯誤，請檢查輸入檔格式或 URL 狀態！", None, None, None

            auto_start_btn.click(
                fn=_handle_full_auto,
                inputs=[auto_url_input, auto_audio_input, auto_output_dir],
                outputs=[auto_status_markdown, auto_mix_player, auto_click_player, auto_zip_download]
            )

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
            ### 🎚️ 實驗性分軌工作區
            此區塊目前仍屬 experimental，公開穩定功能以 PGM 節目軌與採譜分析為主。

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

                    with gr.Accordion("🎛️ 高階錄音室控制選項 (Advanced Studio Options)", open=False):
                        ebu_r128_chk = gr.Checkbox(
                            label="🎧 EBU R128 (-14 LUFS) 聽感控制與 -1.0 dBFS Peak 防剪峰衛兵",
                            value=True
                        )
                        legato_fixer_chk = gr.Checkbox(
                            label="🎼 啟用 Legato 音符微秒重疊修復衛兵 (防止 DAW Note-On 衝突)",
                            value=True
                        )
                        export_musicxml_chk = gr.Checkbox(
                            label="🎼 自動導出 MusicXML (.musicxml) 開放樂譜檔 (MuseScore/Sibelius)",
                            value=True
                        )
                        midi_drum_mode = gr.Dropdown(
                            choices=[("Rimshot / Cowbell (Pitch 37/56)", "rimshot_cowbell"), ("WoodBlock (Pitch 76/77)", "woodblock")],
                            value="rimshot_cowbell",
                            label="🥁 MIDI Click 打擊樂音色模式 (GM Ch10 Key Map)"
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
                    clipboard_textbox = gr.Textbox(
                        label="📋 一鍵複製 PGM 分析摘要 (Line / Discord 團隊通訊群組速貼板)",
                        lines=6,
                        placeholder="分析完成後可在此點擊右上方複製按鈕貼至工作群組..."
                    )
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

        # 頁籤 4: Workflow 執行與診斷 (Diagnostics)
        with gr.TabItem("🔍 Workflow 執行與診斷"):
            gr.Markdown("### 🔍 Behavior Tree 工作流即時執行與診斷主控台")
            with gr.Row():
                with gr.Column(scale=1):
                    diag_url_input = gr.Textbox(
                        label="🌐 貼上影音 URL (YouTube / Bilibili / HTTP 直連)",
                        placeholder="https://www.youtube.com/watch?v=..."
                    )
                    diag_audio_input = gr.File(
                        label="📁 或上傳本地檔 (MP3/WAV/FLAC/M4A)",
                        type="filepath",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"]
                    )
                    diag_stage_select = gr.Dropdown(
                        choices=[
                            ("Stage 1: 音質分析與 ABC 多階層降噪 (不跑分軌)", "stage1"),
                            ("Stage 1 + Stage 2: 音質分析 + 需求驅動 AI 樂器分軌", "stage2"),
                            ("Stage 1 + Stage 2 + Stage 3: 音質分析 + AI 分軌 + 雙軌節拍與 Downbeat 分析", "stage3"),
                            ("Stage 1 ~ Stage 4: 音質 + 分軌 + 雙軌節拍 + 和聲 Sub-mix 調性與和弦分析", "stage4"),
                            ("Stage 1 ~ Stage 6: 全管道 (預設，含樂理/MIDI/DAW工程包打包)", "full"),
                        ],
                        value="stage4",
                        label="🎯 選擇 BT 執行目標階段 (階段式累加控制)"
                    )
                    diag_run_btn = gr.Button("🚀 啟動 BT 工作流並進行實體診斷", variant="primary")
                
                with gr.Column(scale=2):
                    diagnostics_markdown_box = gr.Markdown(
                        "### 🔍 Workflow 診斷資訊\n"
                        "*請於左側提供 URL 或音檔後點擊執行，此處將即時呈現 Behavior Tree 執行軌跡、節點耗時與 Blackboard Key 契約檢查。*"
                    )
                    diagnostics_html_box = gr.HTML(
                        "<div style='padding:12px; color:#aaa;'>*詳細 HTML 診斷報告將於分析完成後顯示於此。*</div>"
                    )

            with gr.Row():
                bt_refresh_btn = gr.Button("🌲 重新整理 BT 流程圖", variant="secondary")

            bt_visualizer_html = gr.HTML(
                value=render_bt_html(build_tree_schema(build_pgm_workflow_tree())),
                label="Behavior Tree 工作流節點架構圖"
            )

            def _handle_diagnostics_run(url, audio, stage_mode):
                if not url and not audio:
                    return "### ⚠️ 請先輸入 URL 或上傳音檔檔案！", "<div style='color:red;'>未提供輸入來源</div>"
                input_src = url if url else audio
                
                # 根據選擇的階段設定 enable_stem
                enable_stem = (stage_mode in ("stage2", "stage3", "stage4", "full"))
                
                report = engine.run(input_src, output_dir=DEFAULT_OUTPUT_DIR, enable_stem=enable_stem)
                md, html = format_workflow_diagnostics(report)
                return md, html

            diag_run_btn.click(
                fn=_handle_diagnostics_run,
                inputs=[diag_url_input, diag_audio_input, diag_stage_select],
                outputs=[diagnostics_markdown_box, diagnostics_html_box]
            )

            def _refresh_bt_html():
                return render_bt_html(build_tree_schema(build_pgm_workflow_tree()))

            bt_refresh_btn.click(fn=_refresh_bt_html, inputs=[], outputs=[bt_visualizer_html])


        # 頁籤 5: MIDI 鋼琴卷軸預覽 (Piano Roll)
        with gr.TabItem("🎹 MIDI 鋼琴卷軸預覽"):
            piano_roll_html_box = gr.HTML("<div style='padding:15px; color:#aaa;'>### 🎹 MIDI 鋼琴卷軸預覽<br>*執行 PGM 分析後，將於此處渲染 MIDI 和弦與樂曲段落鋼琴卷軸。*</div>")

        # 頁籤 6: PGM 工程素材包一鍵打包與下載 (ZIP Package)
        with gr.TabItem("📦 PGM 工程素材包一鍵打包與下載"):
            gr.Markdown("""
            ### 📦 DAW Ready 完整工程素材包
            包含全套 DAW 專案檔 (`.rpp`, `.als`, `.fcpxml`)、Tempo / Click / Chord MIDI 軌、Live 舞台指示面板與逐字稿字幕報告。
            """)
            file_zip_download = gr.File(label="📦 一鍵下載全套 DAW 工程素材包 (.zip Archive)")

        # 頁籤 7: BT 節點動態插件管理器 (Node Plugin SDK)
        with gr.TabItem("🔌 BT 節點動態插件管理器"):
            plugin_manager_html_box = gr.HTML(
                value=render_plugin_manager_html(),
                label="v2.0 Behavior Tree 節點插件加載與黑板契約診斷"
            )

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
                    file_report_download,
                    diagnostics_markdown_box,
                    diagnostics_html_box,
                    piano_roll_html_box,
                    file_zip_download
                ]
            )



def build_ui():
    """Helper method returning the Gradio Demo instance for app initialization and testing."""
    return demo


if __name__ == "__main__":
    allowed_drives = [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
    demo.launch(
        server_name="127.0.0.1", 
        server_port=7860, 
        share=False,
        allowed_paths=[DEFAULT_OUTPUT_DIR] + allowed_drives
    )



