from dataclasses import dataclass, field


LANGUAGE_LABEL_TO_CODE = {
    "English": "en",
    "中文": "zh",
}


I18N = {
    "en": {
        "app_title": "Twitch Auto-Title - UI",
        "current_detected_game": "Current Detected Game:",
        "configured_mappings": "Configured Game -> Process mappings:",
        "reload_config": "Reload config.json",
        "remove_selected": "Remove selected",
        "edit_exclusions": "Edit Exclusions",
        "language": "Language:",
        "game_name": "Game Name:",
        "process_select": "Process (select):",
        "twitch_category": "Twitch Category:",
        "refresh": "Refresh",
        "auto_select_match": "Auto-select match",
        "custom_text_hint": "Custom Text (will be appended to the end of the title):",
        "keep_last_when_none": "When no game detected, keep last title (do not switch to Just Chatting)",
        "add_update": "Add / Update mapping",
        "manual_update": "Manual Update Title/Category",
        "excluded_window": "Edit Excluded Processes",
        "excluded_names": "Excluded Process Names (one per line)",
        "running_processes": "Running Processes (select to add to exclusions)",
        "excluded_prefixes": "Excluded Prefixes (starts-with)",
        "add": "Add",
        "save": "Save",
        "close": "Close",
        "add_to_names": "Add Selected -> Excluded Names",
        "add_to_prefixes": "Add Selected -> Excluded Prefixes",
    },
    "zh": {
        "app_title": "Twitch 自動標題 - 介面",
        "current_detected_game": "目前偵測到的遊戲:",
        "configured_mappings": "已設定 遊戲 -> 程序 對應:",
        "reload_config": "重新載入 config.json",
        "remove_selected": "移除所選",
        "edit_exclusions": "編輯排除清單",
        "language": "語言:",
        "game_name": "遊戲名稱:",
        "process_select": "程序 (選擇):",
        "twitch_category": "Twitch 分類:",
        "refresh": "重新整理",
        "auto_select_match": "自動選擇匹配",
        "custom_text_hint": "自訂文字 (會加在標題結尾):",
        "keep_last_when_none": "未偵測到遊戲時保留上一個標題 (不切換到 Just Chatting)",
        "add_update": "新增 / 更新對應",
        "manual_update": "手動更新標題/分類",
        "excluded_window": "編輯排除程序",
        "excluded_names": "排除程序名稱 (每行一個)",
        "running_processes": "執行中的程序 (可選取加入排除)",
        "excluded_prefixes": "排除前綴 (starts-with)",
        "add": "新增",
        "save": "儲存",
        "close": "關閉",
        "add_to_names": "將所選加入排除名稱",
        "add_to_prefixes": "將所選加入排除前綴",
    },
}


@dataclass
class AppState:
    app_config: dict = field(default_factory=dict)
    base_template: str = " %game% %date%"
    process_names: dict = field(default_factory=dict)
    twitch_categories: dict = field(default_factory=dict)
    current_game: str = "Unknown"
    custom_suffix: str = ""
    keep_last_when_no_game: bool = True
    language: str = "zh"
    excluded_names: set[str] = field(default_factory=set)
    excluded_prefixes: list[str] = field(default_factory=list)
