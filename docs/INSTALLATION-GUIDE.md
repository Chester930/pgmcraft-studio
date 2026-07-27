# PGMCraft Studio 詳細環境安裝與避坑指南 (Installation Guide)

本指南提供跨平台 (Windows / macOS / Linux) 的環境建置流程，包含 Python 虛擬環境、PyTorch (GPU/CPU)、FFmpeg 影音解碼工具與 UVR5 模型依賴之避坑步驟。

---

## 💻 1. 系統依賴要求 (System Requirements)

- **作業系統**: Windows 10/11, macOS 12+, 或 Linux (Ubuntu 20.04+)
- **Python 版本**: **Python 3.10 ~ Python 3.13** (推薦 3.11/3.13)
- **硬體需求**:
  - **最低配置**: 4 核 CPU + 8GB RAM (僅 CPU 模式下分軌需較長時間)
  - **推薦配置**: NVIDIA GPU (支持 CUDA 11.8 / 12.1+, 6GB+ VRAM) + 16GB RAM

---

## 🚀 2. 快速安裝步驟

### Step 1: 複製儲存庫並建立虛擬環境

```bash
# 複製專案
git clone https://github.com/Chester930/pgmcraft-studio.git
cd pgmcraft-studio

# 建立 Python 虛擬環境
python -m venv .venv

# 啟用虛擬環境
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate
```

---

### Step 2: 安裝核心 Python 依賴

```bash
# 升級 pip
pip install --upgrade pip

# 安裝基本與音訊分析套件
pip install -r requirements.txt
```

---

### Step 3: 安裝 PyTorch (GPU 加速選填)

預設 `requirements.txt` 會安裝 CPU 版 PyTorch。若你的電腦擁有 NVIDIA 獨立顯示卡，強烈建議安裝 CUDA 版本的 PyTorch 以獲得 **10 倍以上的 AI 分軌加速**：

```bash
# CUDA 12.1 顯示卡加速版 (NVIDIA GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

### Step 4: 安裝 FFmpeg 影音解碼器 (關鍵依賴)

`ffmpeg` 是讀取 MP3, MP4, FLAC 影音檔及網址下載的必要核心，請確保系統已安裝 `ffmpeg` 並加至 PATH 環境變數：

#### **Windows 安裝法**:
1. 使用 `winget` 快速安裝：
   ```powershell
   winget install Gyan.FFmpeg
   ```
2. 或下載 [FFmpeg 官方建置包](https://www.gyan.dev/ffmpeg/builds/)，解壓後將 `bin` 目錄新增至系統 PATH。

#### **macOS 安裝法**:
```bash
brew install ffmpeg
```

#### **Linux (Ubuntu/Debian) 安裝法**:
```bash
sudo apt update && sudo apt install -y ffmpeg
```

---

### Step 5: (選填) 安裝進階 AI 採譜與音高追蹤套件 (`basic-pitch` & `crepe`)

PGMCraft Studio 本身內建高精度 DSP 降級備援機制（即使未安裝任何第三方 AI 採譜模型，系統仍能 100% 順暢運行並導出 MIDI 導引軌）。

如果你希望發揮 **Spotify 神經網路高精度 MIDI 採譜** 與 **CREPE 深度學習人聲音高追蹤** 的最佳效果，可手動安裝以下選填套件：

```bash
# 安裝 Spotify Basic Pitch (高精度多音音高採譜)
pip install basic-pitch

# 安裝 CREPE (單音人聲音高追蹤)
pip install crepe tensorflow
```

> 💡 **避坑提示 (Windows 用戶)**：
> - 安裝 `crepe` 或 `basic-pitch` 時若遇到 `numba` 或 `resampy` 編譯錯誤，請先確保系統已安裝 [Visual Studio C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)。
> - 未安裝上述套件時，系統會自動優雅降級為 **Librosa pyin & DSP 和聲/旋律採譜引擎**，不影響 DAW 素材包之匯出。

---

## 🧪 3. 安裝驗證

執行以下命令驗證系統與單元測試是否運作正常：

```bash
# 執行核心測試套件
python -m pytest -q
```

如果看到 `PASSED` 綠燈，代表環境建置完成！

---

## 🌐 4. 啟動 Web UI 服務

```bash
python app.py
```

瀏覽器訪問 `http://127.0.0.1:7860` 即可開啟 **PGMCraft Studio 旗艦級 Web 介面**。
