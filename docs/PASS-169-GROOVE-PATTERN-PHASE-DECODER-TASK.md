# Pass 169 任務書：實作鼓型拍位解碼與雙聲部和弦鎖定節點 (GroovePatternPhaseDecoderNode)

**狀態**：待處理（尚未實作）
**目標**：解決重音不在第 1 拍（如反拍/雷鬼/切分重音或小鼓打在第 2、4 拍）導致節拍器第 1 拍出現相位平移 (Phase Shift) 的問題。透過「Bass根音+和弦切換鎖定」與「鼓組相對拍位解碼」，精確計算非 1 拍重音的相位（Phase=2,4），並反推出真正的第 1 拍 (Downbeat)。

---

## 0. 背景與問題

當樂曲重音落在第 2 拍、第 4 拍或 2&/4& 切分拍時：
- 傳統僅看音量/瞬態特徵的演算法會誤把「最強音」直接標記為第 1 拍，導致節拍器產生 1~2 拍的整體相位位移。
- 需結合 Bass 根音、和弦切換點（流行樂中 95% 精確在 1 拍）與鼓型相對拍位來解碼真正的 Downbeat。

---

## 1. 演算法實作架構 (`GroovePatternPhaseDecoderNode`)

1. **雙聲部和弦與 Bass 根音鎖定 (Chord & Bass Lock)**：
   - 提取 `chord_progression` 的和弦切換點 $T_{\text{chord}}$ 與 `bass_anchors` 根音作為物理第 1 拍的最高信心標誌 ($C = 0.95$)。
2. **鼓組相對拍位解碼 (Groove Phase Decoding)**：
   - 計算強重音 $T_{\text{accent}}$ 相對於 $T_{\text{chord}}$ 的拍位偏移量：
     $$\text{Phase} = \operatorname{round}\left(\frac{T_{\text{accent}} - T_{\text{chord}}}{\text{BeatInterval}}\right) + 1$$
   - 當 $\text{Phase} \in \{2, 4\}$ 時，識別其為反拍重音，反推真正的第 1 拍：
     $$\text{Inferred Beat 1} = T_{\text{accent}} - (\text{Phase} - 1) \times \text{BeatInterval}$$
3. **信心度打分與低分拍點刪除**：
   - 設定信心打分機制。將低於信心門檻 ($C < 0.6$) 的切分音/模糊拍點刪除，由前後確信錨點雙向補齊。

---

## 2. 驗證方式

1. 撰寫 `tests/test_sdd_pass169.py`：
   - 驗證當重音落在第 2 拍（反拍）時，節點能正確識別 Phase=2 並反推出第 1 拍，而不把第 2 拍誤設為第 1 拍。
   - 驗證和弦切換點與 Bass 根音雙聲部鎖定功能。
2. 執行單元測試與全套測試回歸。
3. 更新 `BT-BUILD-PROGRESS.md` 並 commit/push/PR。
