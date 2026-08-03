# Pass 170 任務書：小節網格合理性過濾與 Ghost 小節合併 (BarGridSanityPrunerNode)

**狀態**：待處理（尚未實作）
**目標**：移除切分音搶拍修復後殘留的「Ghost 小節」（duration < 0.6 * global_median 的超短殘片），並將其合併回前一個小節，消除 MeasureMapNode 警告的 [1,1,1,1,1] 異常小節長度與 10 次 BPM 跳動超過 35% 的問題，目標使商用品質分數從 70.2 提升至 85+。

---

## 0. 背景與問題

Pass 168 TwoWayAnchorBacktraceNode 修復了 105 處切分搶拍，但在部分修復點留下了超短殘片小節：
- 殘片小節 duration 約 0.36s（正常小節 1.45s 的 25%）
- 這 5 個 1-beat ghost 小節造成相鄰 BPM 跳動超過 35%
- `CommercialBeatQualityNode` 給分 70.2/100 (NEEDS_MANUAL_EDIT)

## 1. 演算法實作

1. 計算全曲 `global_median` 小節步距。
2. 掃描所有小節，若 `duration < 0.6 * global_median`（約 < 0.87s @ 165 BPM），判定為 Ghost 殘片。
3. 將 Ghost 殘片的起始時間點**合併到前一個小節**（延伸前一個小節的結束點），刪除 Ghost 殘片節點。
4. 重新計算合併後的小節步距，確保後續節點使用乾淨網格。

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass170.py`：
   - 注入 5 個 ghost 殘片小節（duration = 0.36s），驗證 BarGridSanityPrunerNode 能正確識別並移除 5 個 ghost 殘片。
   - 驗證移除後小節總數減少，且最終小節列表中不存在 duration < 0.6 * median 的殘片。
2. 執行單元測試與全套測試回歸。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
