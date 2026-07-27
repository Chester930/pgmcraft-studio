# PGMCraft Studio 初學者快速上手指南 (Quick Start)

歡迎使用 **PGMCraft Studio**！本系統是一套專為 **樂隊/Live PGM、採譜樂手與 DAW 音樂製作人** 設計的「自動節拍器與 DAW 素材產生系統」。

無論你是第一次接觸的新手、練團 PGM 負責人，或是 DAW 錄音室製作人，本指南都能幫你在 **3 分鐘內獲得最佳效果**。

---

## 🎯 根據你的角色，選擇使用情境

```text
 ┌─────────────────────────────────────────────────────────────┐
 │                      PGMCraft Studio                        │
 └──────────────────────────────┬──────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
【情境 A：樂手 / PGM】    【情境 B：DAW 製作人】   【情境 C：Python 開發者】
獲得 Click 軌與動態提詞器  匯入 Pro Tools/Cubase   使用 SDK 調用 BT 樹鏈
```

---

## 🎤 情境 A：我是樂手 / Live PGM 控制員

**你的目標**：快速從音檔/影片取得乾淨的 Click 節拍器 Wav、原曲+Click 預聽檔，以及舞台顯示用的 HTML 動態滾動提詞器。

### 步驟：
1. 開啟 Web UI 介面：
   ```bash
   python app.py
   ```
2. 在瀏覽器打開 `http://127.0.0.1:7860`。
3. 切換至 **「🎛️ PGM 節目軌與採譜分析」** 頁籤。
4. 貼上 YouTube 網址或拖曳上傳音檔。
5. 勾選 **「🥁 開啟 Stem 鼓組/人聲分離」**（推薦開啟，可顯著提升無鼓區間與大鼓重音精度）。
6. 按下 **「🚀 執行 PGM 節目軌與採譜分析」**。
7. **獲得產出**：
   - 播放器可試聽 `mix_with_click.wav` (原曲+Click)。
   - 下載 `live_dashboard.html`（可以在 iPad / 筆電瀏覽器打開，隨音樂平滑自動滾動顯示小節、和弦與歌詞）。
   - 下載 `voice_cue_guide.wav`（舞台導唱/數拍語音倒數軌）。

---

## 🎧 情境 B：我是 DAW 音樂製作人

**你的目標**：將 MIDI 速度曲線 (Tempo Map)、和弦 Marker 與音軌無縫匯入 DAW (Pro Tools, Cubase, REAPER, Ableton, Logic Pro)。

### 步驟：
1. 執行 Pipeline 產出完整專案包（Web UI 選擇 Stage 6 或 CLI `python main.py <file.wav>`）。
2. 在輸出的 `outputs/` 資料夾中找到 `pgm_project_package.zip` 並解壓。
3. **根據你的 DAW 進行匯入**：
   - **Pro Tools**: 匯入 `project_protools.aaf` 專案檔，或導入 `tempo_map.mid` 匯入速度曲線。
   - **Cubase**: 選擇 `File -> Import -> Tempo Track` 匯入 `cubase_tempo_map.csv`。
   - **REAPER**: 直接點擊開啟 `pgm_session.rpp`（自動建置 Rhythm Bus, Music Bus, Vocal Bus 軌道）。
   - **Ableton Live**: 將 `tempo_map.mid` 與 `click_guide.mid` 拖入 Arrange View。
4. 詳細操作請參閱 [DAW 匯入指南 (DAW-IMPORT-GUIDE.md)](DAW-IMPORT-GUIDE.md)。

---

## 💻 情境 C：我是 Python 開發者 / AI 音訊研究員

**你的目標**：將 PGMCraft Studio 的 Behavior Tree (行為樹) 音訊工作流整合至你自己的 SDK 或自動化 Pipeline。

### 範例程式碼：

```python
from pgm_craft.pipeline import PGMFullPipelineEngine

# 初始化全管道 BT 引擎
engine = PGMFullPipelineEngine()

# 執行分析 (支援指定標的階段 target_stage='stage1' ~ 'stage6'/'full')
report = engine.run(
    audio_path="sample_test.wav",
    output_dir="outputs",
    enable_stem=True,
    target_stage="full"
)

print(f"解析主調: {report['estimated_key']}")
print(f"平均速度: {report['average_bpm']} BPM")
print(f"專案包位置: {report['project_package']['project_package_dir']}")
```

---

## ❓ 常見問題 QA

### Q1: 為什麼鼓聲停止時，節拍器不會亂跳？
PGMCraft Studio 內建 **Tempo Inertia (速度慣性脈衝引擎)**。當檢測到鼓聲靜音時，系統會自動切換為硬體級電子節拍器等速內插，確保極度穩定。

### Q2: 鼓聲重新進場時，第一拍會不會錯位？
系統設有 **Re-Entry Re-Anchoring (鼓聲重返衛兵)**，當無鼓段落結束大鼓 (Kick) 切入時，BT 會強制將該點鎖定重錨為小節第 1 拍 (Downbeat = 1)。

### Q3: 可以在完全沒有外網的 Live 舞台使用嗎？
**可以！** 本系統支援 100% 本地離線運作，只需直接拖曳上傳本地 `.wav` / `.mp3` 即可完成全套分析與導出。
