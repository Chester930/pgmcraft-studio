import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pgm_craft.pipeline import PGMCraftEngine

audio_path = r"d:\Users\666\Music\2\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】\source\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】.wav"
output_dir = r"d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass169_real_test"

os.makedirs(output_dir, exist_ok=True)

print("🚀 啟動最新 Pass 169 (雙聲部和弦鎖定 + 鼓型反推) 實體全流程生成...")
t0 = time.time()

engine = PGMCraftEngine(enable_stem_separation=True)
report = engine.run(
    audio_path,
    output_dir=output_dir,
    enable_stem=True,
    target_stage="full",
    user_meter_selection="4/4"
)

t1 = time.time()
print(f"✅ 生成完畢！耗時: {t1 - t0:.2f} 秒")
print(f"🎧 最新預聽檔位置: {os.path.join(output_dir, 'click', 'mix_with_click.wav')}")
