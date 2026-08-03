# Pass 167 任務書：升級 ProjectPackageZipNode UTF-8 編碼與素材包完整性

**狀態**：待處理（尚未實作）
**目標**：升級 Stage 6 素材打包節點 `ProjectPackageZipNode`，為所有壓縮檔案顯式設定 UTF-8 標誌以防跨平台/DAW 解壓亂碼，並增強素材包完整性檢驗。

---

## 0. 背景與問題

1. **跨平台解壓亂碼風險**：使用預設 `zipfile.ZipFile` 在 Windows/Mac/Linux 跨平台或某些 DAW（如 Cubase / Ableton Live）解壓含有 Unicode/中日文字元的素材包時，若未設定 UTF-8 標誌 (`flag_bits |= 0x800`) 易出現亂碼。
2. **完整性保護**：打包時需安全確保必要報告與導引文件皆正確寫入素材包內。

---

## 1. 具體升級細節

### A. 顯式 UTF-8 ZipInfo 封裝
在 `ProjectPackageZipNode.execute()` 內：
- 使用 `zipfile.ZipInfo.from_file()` 建立條目，並顯式設定 `zinfo.flag_bits |= 0x800` (UTF-8 編碼標誌)。
- 確保所有檔名在各大 DAW 及作業系統解壓時 100% 正確顯示。

### B. 素材包導引 `IMPORT_GUIDE.md`
- 確保 `IMPORT_GUIDE.md` 包含正確的拍點、BPM 與素材說明，一同寫入 Zip 根目錄。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass167.py`：
   - 驗證 `ProjectPackageZipNode` 打包含 Unicode / 中文字元檔名時 `flag_bits` 包含 0x800。
   - 驗證生成的 zip 檔案結構完整且無損。
2. 執行單元測試與全套測試回歸。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
