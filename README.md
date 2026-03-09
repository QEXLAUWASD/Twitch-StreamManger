# Twitch Stream Auto-Title (OBS Helper)

Auto-detects the currently running game process and updates your Twitch stream title and category.

Chinese version: `README_zh.md`

## Features

- Auto-detect game by process name.
- Auto-update Twitch stream title.
- Auto-update Twitch stream category.
- GUI for managing game/process/category mappings.
- Exclusion editor for process names and prefixes.
- Live reload when `config.json` is modified.

## Requirements

- Windows (project currently built and tested on Windows)
- Python 3.10+ (recommended)
- Twitch account with a valid app token for channel update APIs

Python packages (from `requirements.txt`):

- `requests==2.28.2`
- `watchdog==2.2.1`
- `psutil==5.9.4`

## Installation

1. Create and activate a virtual environment (optional if you already have one):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

## First Run

Run:

```powershell
python main.py
```

On first run, if `config.ini` does not exist, the app prompts for:

- `client_id`
- `access_token`
- `streamer_id`

It will also auto-create:

- `config.json` (downloaded default template)
- `excluded_processes.json` (default exclusion template)

## Configuration Files

### `config.ini`

Stores Twitch credentials:

```ini
[Twitch]
client_id = YOUR_CLIENT_ID
access_token = YOUR_ACCESS_TOKEN
streamer_id = YOUR_STREAMER_ID
```

### `config.json`

Main mapping and title template file:

```json
{
  "base": "%game% %date%",
  "process_name": {
    "Valorant": "VALORANT-Win64-Shipping.exe"
  },
  "TwitchCategoryName": {
    "Valorant": "VALORANT"
  }
}
```

- `base`: title template (supports `%game%` and `%date%`)
- `process_name`: game display name -> process executable name
- `TwitchCategoryName`: game display name -> Twitch category name

### `excluded_processes.json`

Process filters to skip from detection:

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

## Project Structure

- `main.py`: app entrypoint (wires all modules together)
- `bootstrap.py`: startup checks and credential/file bootstrap
- `app_state.py`: shared runtime state and i18n text tables
- `config_store.py`: load/save config and exclusion data
- `twitch_client.py`: Twitch API update logic
- `process_monitor.py`: process scan and auto-update loop
- `ui.py`: Tkinter UI and user actions

## Running as EXE (PyInstaller)

A spec file already exists: `main.spec`.

Typical build command:

```powershell
pyinstaller main.spec
```

When packaged as onefile, the app uses the executable folder as runtime base directory for user-editable config files.

## Notes

- Keep your `access_token` secure. Do not commit `config.ini`.
- Twitch API failures are printed in console logs.
- If no game is detected, behavior can be changed in the UI (keep last title or fallback to `Just Chatting`).
