# PGMCraft Studio v2.0 雙向 Behavior Tree 節點插件架構規格書 (Node Plugin Architecture)

**版本：** v2.0-Draft  
**發布日期：** 2026-07-23  

---

## 1. 核心理念 (Core Principles)

PGMCraft Studio v2.0 旨在提供開放式 Behavior Tree (BT) 音訊處理與素材產出節點插件化 SDK：

1. **零侵入式擴充 (Zero-Intrusion)**: 開發者無需修改核心 `pgm_craft` 原始碼，只需繼承 `BaseNode` 並落盤於 `plugins/` 目錄即可完成註冊。
2. **Blackboard 型別契約綁定**: 插件節點遵循 `required_keys` 與 `output_keys` 聲明，享有自動化 Contract Validation 防護。
3. **Graceful Fallback 保護鎖**: 插件若執行出錯，可設定預設防禦降級路徑，不致中斷整個工程素材產出流程。

---

## 2. 插件介面規範 (Plugin Interface)

```python
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard

class CustomVocalHarmonizerNode(BaseNode):
    """客製化人聲和聲分離與和絃推論插件"""
    required_keys = ["y", "sr", "stems"]
    output_keys = ["vocal_harmony_midi"]

    def __init__(self):
        super().__init__("CustomVocalHarmonizerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        # 讀取黑板狀態
        y = blackboard.get_val("y")
        # 進行客製化 processing...
        
        # 寫回黑板
        blackboard.set_val("vocal_harmony_midi", "path/to/harmony.mid")
        return NodeStatus.SUCCESS
```

---

## 3. 插件目錄結構 (Plugin Directory Structure)

```text
pgmcraft-studio/
├── plugins/
│   ├── vocal_harmonizer/
│   │   ├── __init__.py
│   │   └── harmonizer_node.py
│   └── custom_eq/
│       └── eq_node.py
```

---

## 4. 動態加載機制 (Dynamic Discovery)

`PluginLoader` 會自動掃描 `.plugins/` 或指定的第三方目錄，載入所有 `BaseNode` 的子類別，並提供 `register_to_workflow(builder)` 綁定至主 Behavior Tree 鏈上。
