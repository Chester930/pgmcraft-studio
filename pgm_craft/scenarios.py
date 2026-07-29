"""
PGMCraft Domain-Specific Two-Tier Scenario Registry & State Machine Workflow Dispatcher.
Defines 6 Core Domains (Big Scenarios) and 20 Sub-Scenario Workflows.
"""

SCENARIO_DOMAINS = [
    {"id": "podcast", "label": "🎙️ Podcast 播客與口播節目", "desc": "適用於訪談、語音廣播、Talking Head 影片降噪與房間迴音修復"},
    {"id": "vlog", "label": "📹 影音創作者與自媒體剪輯", "desc": "適用於戶外外景、街頭錄影風切聲與對白 / BGM 背景音樂分離"},
    {"id": "vocal_karaoke", "label": "🎤 歌唱與伴奏製作", "desc": "適用於 KTV 純伴奏產出、帶和聲伴奏、主唱/和聲獨立切分與聲音純化"},
    {"id": "transcribe_practice", "label": "🎸 樂器採譜與個人練團", "desc": "適用於吉他/鋼琴/弦樂獨奏採譜、鼓組物理三分頻與電貝斯/808 聲色拆解"},
    {"id": "live_pgm", "label": "🏟️ Live 舞台 PGM 與演唱會工程", "desc": "適用於演唱會 6-Stem 解構、Click 耳監打點、預備拍與 DAW 專案素材包打包"},
    {"id": "voiceover_asmr", "label": "🎧 配音與 ASMR 語音純化", "desc": "適用於有聲書配音、CV 口播去除換氣吸氣聲與口水音極致淨化"}
]

SCENARIO_WORKFLOWS = {
    "podcast": [
        {"id": "podcast_interview_clean", "label": "1-1. 雙人/多人訪談聲音淨化 (Interview Clean)", "steps": ["interview_clean"]},
        {"id": "podcast_r128_normalize", "label": "1-2. 播客音量 EBU R128 自動標準化 (R128 Normalize)", "steps": ["r128_normalize"]},
        {"id": "podcast_voice_isolation", "label": "1-3. Talking Head 語音抽出與背景音分離 (Voice Isolation)", "steps": ["voice_isolation"]}
    ],
    "vlog": [
        {"id": "vlog_wind_env_clean", "label": "2-1. 戶外外景低頻風切聲與車流雜音降噪 (Wind & Environment Clean)", "steps": ["wind_env_clean"]},
        {"id": "vlog_dialogue_bgm_split", "label": "2-2. 影片對白與背景音樂二分抽離 (Dialogue / BGM Split)", "steps": ["dialogue_bgm_split"]},
        {"id": "vlog_speech_enhance", "label": "2-3. 展覽/街頭人聲高亮與人群雜音剝離 (Speech Enhance)", "steps": ["speech_enhance"]}
    ],
    "vocal_karaoke": [
        {"id": "vocal_pure_inst", "label": "3-1. 經典純伴奏製作 (Pure Instrumental)", "steps": ["pure_inst"]},
        {"id": "vocal_backing_inst", "label": "3-2. 帶和聲伴奏製作 (Backing Instrumental)", "steps": ["backing_inst"]},
        {"id": "vocal_lead_backing_split", "label": "3-3. 主唱與和聲雙軌獨立分離 (Lead / Backing Split)", "steps": ["lead_backing_split"]},
        {"id": "vocal_dereverb_clean", "label": "3-4. 人聲乾聲去殘響與聲音純化 (Vocal De-reverb Clean)", "steps": ["dereverb_clean"]}
    ],
    "transcribe_practice": [
        {"id": "transcribe_instrument_midi", "label": "4-1. 鋼琴/吉他獨奏轉 MIDI 音符檔 (Instrument MIDI)", "steps": ["instrument_midi"]},
        {"id": "transcribe_chord_key", "label": "4-2. 爵士/流行樂曲和弦與調性分析報告 (Chord & Key)", "steps": ["chord_key"]},
        {"id": "transcribe_drum_pattern", "label": "4-3. 爵士鼓與打擊樂器節拍聲軌採譜 (Drum Pattern)", "steps": ["drum_pattern"]}
    ],
    "live_pgm": [
        {"id": "live_multitrack_package", "label": "5-1. Live 舞台 Multi-Track 全分軌 DAW 素材包導出 (Multitrack Package)", "steps": ["multitrack_package"]},
        {"id": "live_click_cue_gen", "label": "5-2. 舞台導聽 Click & Cue Voice 指示音軌生成 (Click & Cue)", "steps": ["click_cue"]},
        {"id": "live_stage_hud", "label": "5-3. 樂手即時 HTML5 視聽同步 HUD 控制台面板 (Stage HUD)", "steps": ["stage_hud"]},
        {"id": "live_daw_native_align", "label": "5-4. Ableton Live / Logic Pro / Cubase 原生專案檔對齊 (DAW Native Align)", "steps": ["daw_native_align"]}
    ],
    "voiceover_asmr": [
        {"id": "asmr_hiss_clean", "label": "6-1. ASMR 高頻底噪與電流聲淨化 (ASMR Hiss Clean)", "steps": ["asmr_hiss_clean"]},
        {"id": "asmr_mouth_click_removal", "label": "6-2. ASMR 口腔濕潤音與唇齒音極致剝離 (ASMR Mouth Click Removal)", "steps": ["asmr_mouth_click_removal"]},
        {"id": "asmr_spatial_binaural_enhance", "label": "6-3. ASMR 雙耳 3D 空間環繞聲場增強 (Spatial Binaural)", "steps": ["spatial_binaural"]},
        {"id": "asmr_subtle_mic_booster", "label": "6-4. ASMR 助眠極微音細節增益高亮 (Subtle Mic Booster)", "steps": ["subtle_mic_booster"]}
    ]
}


class ScenarioManager:
    """管理兩階層應用場景與狀態機工作流之對接與轉換」"""

    @staticmethod
    def get_domain_choices() -> list[tuple[str, str]]:
        """回傳第一階【選擇應用場景】下拉選單元組清單 (Label, ID)"""
        return [(d["label"], d["id"]) for d in SCENARIO_DOMAINS]

    @staticmethod
    def get_workflows_by_domain(domain_id: str) -> list[tuple[str, str]]:
        """給定第一階 Domain ID，動態回傳第二階【選擇狀態機工作流】元組清單 (Label, ID)"""
        workflows = SCENARIO_WORKFLOWS.get(domain_id, [])
        return [(w["label"], w["id"]) for w in workflows]

    @staticmethod
    def get_default_workflow_id(domain_id: str) -> str:
        """回傳特定 Domain 的預設第一項 Workflow ID"""
        workflows = SCENARIO_WORKFLOWS.get(domain_id, [])
        return workflows[0]["id"] if workflows else "podcast_interview_clean"
