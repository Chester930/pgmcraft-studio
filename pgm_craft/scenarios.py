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
        {"id": "podcast_interview_clean", "label": "1-1. 雙人/多人訪談去噪與房間迴音修復", "steps": ["dehum", "denoise", "dereverb"]},
        {"id": "podcast_r128_normalize", "label": "1-2. 播客音量 EBU R128 自動標準化 (-16 LUFS)", "steps": ["r128_loudness"]},
        {"id": "podcast_voice_isolation", "label": "1-3. 單人 Talking Head 獨立語音抽出與背景墊音分離", "steps": ["vocals_isolation"]}
    ],
    "vlog": [
        {"id": "vlog_wind_env_clean", "label": "2-1. 戶外外景低頻風切聲與車流雜音降噪", "steps": ["low_cut", "crowd_cheering_split"]},
        {"id": "vlog_dialogue_bgm_split", "label": "2-2. 影片對白與背景音樂 (BGM) 二分抽離", "steps": ["vocals_isolation"]},
        {"id": "vlog_speech_enhance", "label": "2-3. 展覽/街頭人聲高亮與人群雜音剝離", "steps": ["crowd_cheering_split", "speech_enhance"]}
    ],
    "vocal_karaoke": [
        {"id": "vocal_pure_inst", "label": "3-1. 經典純伴奏製作 (Full Vocal Removal)", "steps": ["vocals_isolation"]},
        {"id": "vocal_backing_inst", "label": "3-2. 帶和聲伴奏製作 (Keep Backing Vocals)", "steps": ["vocals_isolation", "lead_backing_split"]},
        {"id": "vocal_lead_backing_split", "label": "3-3. 主唱與和聲雙軌獨立分離", "steps": ["vocals_isolation", "lead_backing_split"]},
        {"id": "vocal_dereverb_clean", "label": "3-4. 人聲乾聲去殘響與聲音純化", "steps": ["vocals_isolation", "dereverb", "debreathe"]}
    ],
    "transcribe_practice": [
        {"id": "transcribe_drums_subsplit", "label": "4-1. 爵士/流行鼓組物理三細分 (Kick / Snare / HiHat)", "steps": ["drums_subsplit"]},
        {"id": "transcribe_guitar_solo", "label": "4-2. 吉他 Solo 採譜與減吉他伴奏", "steps": ["guitar_isolation"]},
        {"id": "transcribe_piano_solo", "label": "4-3. 鋼琴/鍵盤獨奏採譜分離", "steps": ["piano_isolation"]},
        {"id": "transcribe_bass_808_split", "label": "4-4. 電貝斯 vs 合成 808 低音聲色拆解", "steps": ["synth_bass_split"]},
        {"id": "transcribe_strings_isolation", "label": "4-5. 弦樂與管弦樂聲部隔離", "steps": ["strings_isolation"]}
    ],
    "live_pgm": [
        {"id": "live_6stem_package", "label": "5-1. 樂團 6-Stem 精密解構與素材包歸檔", "steps": ["general_6stem", "package"]},
        {"id": "live_click_countin", "label": "5-2. Live PGM 耳監 Click 打點與 1-Bar 預備拍合成", "steps": ["click_synthesis"]},
        {"id": "live_daw_session_export", "label": "5-3. REAPER (.RPP) / Ableton Live (.ALS) 原生工程檔導出", "steps": ["daw_export"]},
        {"id": "live_dashboard_html_sync", "label": "5-4. Live 舞台視聽同步 HTML 提詞儀表板導出", "steps": ["live_dashboard_export"]}
    ],
    "voiceover_asmr": [
        {"id": "asmr_debreathe_clean", "label": "6-1. ASMR / 配音員去氣音與口水音淨化", "steps": ["debreathe"]},
        {"id": "voiceover_studio_dry", "label": "6-2. 有聲書極致乾聲與直流偏置消除", "steps": ["dc_offset", "dereverb"]}
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
