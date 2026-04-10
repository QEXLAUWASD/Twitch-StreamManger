# Twitch Stream Auto-Title (OBS 輔助工具)

> **維護模式：** 此專案不再新增功能。往後僅提供錯誤修復。

自動偵測目前執行中的遊戲程序，並更新 Twitch 直播標題與分類。

## 功能特色

- 依程序名稱自動偵測遊戲。
- 自動更新 Twitch 直播標題。
- 自動更新 Twitch 直播分類。
- 提供 GUI 介面管理遊戲/程序/分類對應。
- 提供排除清單編輯器（程序名稱與前綴）。
- `config.json` 修改後可即時重新載入。
- 深色模式切換（重啟後保留設定）。
- UI 語言選擇（English / 中文，重啟後保留設定）。
- 「保留上一個標題」設定重啟後保留。

## 環境需求

- Windows（目前專案主要在 Windows 環境測試）
- Python 3.10+（建議）
- 具備可呼叫 Twitch 頻道更新 API 的帳號與 Token

Python 套件（來自 `requirements.txt`）：

- `requests==2.28.2`
- `watchdog==2.2.1`
- `psutil==5.9.4`

## 安裝方式

1. 建立並啟用虛擬環境（若你已有環境可略過）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. 安裝相依套件：

```powershell
pip install -r requirements.txt
```

## 第一次執行

執行：

```powershell
python main.py
```

首次啟動且不存在 `config.ini` 時，程式會要求輸入：

- `client_id`
- `access_token`
- `streamer_id`

另外也會自動建立：

- `config.json`（下載預設範本）
- `excluded_processes.json`（建立預設排除範本）

## 設定檔說明

### `config.ini`

存放 Twitch 憑證：

```ini
[Twitch]
client_id = YOUR_CLIENT_ID
access_token = YOUR_ACCESS_TOKEN
streamer_id = YOUR_STREAMER_ID
```

### `config.json`

主要對應、標題模板與 UI 偏好設定檔：

```json
{
  "base": "%game% %date%",
  "language": "zh",
  "keep_last_when_none": true,
  "dark_mode": false,
  "process_name": {
    "Valorant": "VALORANT-Win64-Shipping.exe"
  },
  "TwitchCategoryName": {
    "Valorant": "VALORANT"
  }
}
```

- `base`：標題模板（支援 `%game%` 與 `%date%`）
- `language`：UI 語言 — `"en"` 或 `"zh"`（在 UI 中切換語言時自動儲存）
- `keep_last_when_none`：為 `true` 時，偵測不到遊戲會保留上一個標題而非切換到 `Just Chatting`（切換時自動儲存）
- `dark_mode`：為 `true` 時啟用深色模式（切換時自動儲存）
- `process_name`：遊戲顯示名稱 -> 程序執行檔名稱
- `TwitchCategoryName`：遊戲顯示名稱 -> Twitch 分類名稱

### `excluded_processes.json`

用於排除不參與偵測的程序：

```json
{
  "exclude_process_names": [
    "System",
    "explorer.exe"
  ],
  "exclude_prefixes": [
    "chrome",
    "msedge"
  ]
}
```

## 專案結構

- `main.py`：程式入口（負責組裝與啟動各模組）
- `bootstrap.py`：啟動檢查、憑證讀取與初始檔案建立
- `app_state.py`：共享執行狀態與 i18n 文案
- `config_store.py`：設定檔與排除清單的讀寫
- `twitch_client.py`：Twitch API 更新邏輯
- `process_monitor.py`：程序掃描與自動更新循環
- `ui.py`：Tkinter 圖形介面與使用者操作

## 打包成 EXE（PyInstaller）

專案已提供 `main.spec`。

常見打包指令：

```powershell
pyinstaller main.spec
```

若使用 onefile 打包，程式會以可執行檔所在資料夾作為可編輯設定檔的基準路徑。

## 注意事項

- 請妥善保管 `access_token`，不要把 `config.ini` 上傳到公開儲存庫。
- Twitch API 呼叫失敗時，會在主控台顯示錯誤資訊。
- 偵測不到遊戲時，可在 UI 設定「保留上一個標題」或切換回 `Just Chatting`。
- 語言、深色模式與「保留上一個標題」設定在 UI 中變更時會自動儲存至 `config.json`。
