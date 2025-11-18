import subprocess
import requests
import json
import time
import psutil
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import configparser
import threading
def obs():
    subprocess.call("C:/Program Files/obs-studio/bin/64bit/obs64.exe", cwd='C:/Program Files/obs-studio/bin/64bit/')
t = threading.Thread(target = obs)



# Load credentials from config.ini
auth_config = configparser.ConfigParser()
auth_config.read('config.ini')
creds = {
    'client_id': auth_config.get('Twitch', 'client_id'),
    'access_token': auth_config.get('Twitch', 'access_token'),
    'streamer_id': auth_config.get('Twitch', 'streamer_id')
}
CLIENT_ID = creds['client_id']
ACCESS_TOKEN = creds['access_token']
TWITCH_API_URL = 'https://api.twitch.tv/helix/channels'
HEADERS = {
    'Client-ID': CLIENT_ID,
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'Content-Type': 'application/json'
}
STREAMER_ID = creds['streamer_id']

# Read config file for title templates and process names
def load_config():
    try:
        with open("config.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return {}

app_config = load_config()
base_template = app_config.get('base', '[粵/普/EN] | %game% | %date% |  @liulian_channel')
process_names = app_config.get('process_name', {})
twitch_categories = app_config.get('TwitchCategoryName', {})

def get_current_game():
    print("Scanning running processes...")
    detected_processes = []
    game_processes_found = []
    
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            process_name = proc.info['name']
            detected_processes.append(process_name)
            
            # Check against our game processes
            for game, expected_proc in process_names.items():
                # Try exact match first, then case-insensitive
                if process_name == expected_proc or process_name.lower() == expected_proc.lower():
                    print(f"🎮 FOUND GAME: {game} (Process: {process_name})")
                    game_processes_found.append((game, process_name))
                    return game
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Debug output
    if game_processes_found:
        print(f"Multiple game processes found: {game_processes_found}")
    
    print(f"Looking for: {list(process_names.values())}")
    print("Recent processes detected:")
    for proc in detected_processes[-10:]:  # Last 10 processes
        print(f"  - {proc}")
    
    return 'Just Chatting'  # default game if none found

# Enhanced debug function
def debug_all_processes():
    print("\n=== DEBUG: All Running Processes (Full Scan) ===")
    all_processes = []
    
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            all_processes.append(proc.info['name'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Remove duplicates and sort
    unique_processes = sorted(set(all_processes))
    
    print(f"Total unique processes: {len(unique_processes)}")
    print("\nLooking for these game processes:")
    for game, proc_name in process_names.items():
        print(f"  - {game}: '{proc_name}'")
    
    print("\nAll running processes:")
    for i, proc in enumerate(unique_processes):
        # Highlight potential matches
        for expected_proc in process_names.values():
            if expected_proc.lower() in proc.lower():
                print(f"  {i:3d}. 🎯 {proc}  <-- POTENTIAL MATCH!")
                break
        else:
            print(f"  {i:3d}. {proc}")
    
    print("=== END DEBUG ===\n")

def update_stream_category(category):
    try:
        print(f"Attempting to update category to: {category}")
        game_search_url = 'https://api.twitch.tv/helix/games'
        params = {'name': category}
        
        response = requests.get(game_search_url, headers=HEADERS, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                game_id = data['data'][0]['id']
                game_name = data['data'][0]['name']
                
                url = f'{TWITCH_API_URL}?broadcaster_id={STREAMER_ID}'
                data = {'game_id': game_id}
                response = requests.patch(url, headers=HEADERS, json=data, timeout=10)
                if response.status_code == 204:
                    print(f'✅ Stream category updated to: {game_name}')
                else:
                    print(f'❌ Failed to update stream category: {response.status_code}')
            else:
                print(f'❌ Game category "{category}" not found on Twitch')
                # Fallback to Just Chatting
                update_stream_category('Just Chatting')
        else:
            print(f'❌ Failed to search for game: {response.status_code}')
    except Exception as e:
        print(f'❌ Error updating category: {e}')

def update_stream_title(title):
    try:
        url = f'{TWITCH_API_URL}?broadcaster_id={STREAMER_ID}'
        data = {'title': title}
        response = requests.patch(url, headers=HEADERS, json=data, timeout=10)
        if response.status_code == 204:
            print(f'✅ Stream title updated to: {title}')
        else:
            print(f'❌ Failed to update stream title: {response.status_code} - {response.text}')
    except Exception as e:
        print(f'❌ Error updating title: {e}')

def format_title(template, game):
    current_date = time.strftime('%Y-%m-%d')
    title = template.replace('%date%', current_date).replace('%game%', game)
    return title

def monitor_game_and_update_title():
    last_game = None
    debug_count = 0
    
    print("🎮 Starting game monitoring...")
    print(f"Monitoring for {len(process_names)} games")
    
    # Initial debug scan
    debug_all_processes()
    
    while True:
        current_game = get_current_game()
        
        if current_game != last_game:
            last_game = current_game
            print(f'🔄 Game changed to: {current_game}')
            
            # Format and update title
            new_title = format_title(base_template, current_game)
            update_stream_title(new_title)
            
            # Get category name
            category_name = twitch_categories.get(current_game, 'Just Chatting')
            update_stream_category(category_name)
        
        # Periodic debug every 10 checks (5 minutes)
        debug_count += 1
        if debug_count >= 10:
            print("\n--- Periodic Process Check ---")
            get_current_game()  # This will show recent processes
            debug_count = 0
            
        time.sleep(30)  # Check every 30 seconds

class ConfigFileEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('config.json'):
            global app_config, base_template, process_names, twitch_categories
            app_config = load_config()
            base_template = app_config.get('base', '[粵/普/EN] | %game% | %date% |  @liulian_channel')
            process_names = app_config.get('process_name', {})
            twitch_categories = app_config.get('TwitchCategoryName', {})
            print('🔄 Configuration reloaded.')
            print(f"Now monitoring {len(process_names)} games")

if __name__ == '__main__':
    t.start()
    print("OBS Started!")
    print("🎬 Twitch Stream Auto-Title Started!")
    print(f"🔍 Monitoring for games: {list(process_names.keys())}")
    
    event_handler = ConfigFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()
    
    try:
        monitor_game_and_update_title()
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
        observer.stop()
    observer.join()