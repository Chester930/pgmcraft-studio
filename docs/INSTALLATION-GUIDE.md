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
