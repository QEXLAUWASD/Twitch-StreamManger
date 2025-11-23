import requests
import json
import time
import psutil
import configparser
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import tkinter as tk
from tkinter import messagebox, simpledialog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# check for config.ini and create a template and let user input values
if not os.path.exists(os.path.join(BASE_DIR, 'config.ini')):
    print("⚠️ config.ini not found. Creating a template...")
    # use tkinter dialogs to collect credentials (GUI input instead of console)
    root_tmp = tk.Tk()
    root_tmp.withdraw()
    client_id = simpledialog.askstring("Twitch Credentials", "Enter your Twitch client_id:", parent=root_tmp)
    access_token = simpledialog.askstring("Twitch Credentials", "Enter your Twitch access_token:", parent=root_tmp, show='*')
    streamer_id = simpledialog.askstring("Twitch Credentials", "Enter your Twitch streamer_id (user ID):", parent=root_tmp)
    root_tmp.destroy()

    if not client_id or not access_token or not streamer_id:
        tk.messagebox.showerror("Missing", "Credentials not provided. Exiting.")
        exit(0)

    with open(os.path.join(BASE_DIR, 'config.ini'), 'w', encoding='utf-8') as f:
        f.write('[Twitch]\n')
        f.write(f'client_id = {client_id}\n')
        f.write(f'access_token = {access_token}\n')
        f.write(f'streamer_id = {streamer_id}\n')
    tk.messagebox.showinfo("Template Created", "Template config.ini created. Please fill in the values and restart the application.")
    exit(0)

# check for config.json if not exists, download a default template from GitHub
if not os.path.exists(os.path.join(BASE_DIR, 'config.json')):
    print("⚠️ config.json not found. Downloading a default template...")
    default_url = 'https://raw.githubusercontent.com/QEXLAUWASD/Twitch-StreamManger/refs/heads/main/Default_config.json'  # replace with actual URL
    try:
        response = requests.get(default_url, timeout=10)
        if response.status_code == 200:
            with open(os.path.join(BASE_DIR, 'config.json'), 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("Default config.json downloaded.")
        else:
            print(f"❌ Failed to download default config.json: {response.status_code}")
    except Exception as e:
        print(f"❌ Error downloading config.json: {e}")
        exit(1)
        
# check for excluded_processes.json, create empty if not exists
if not os.path.exists(os.path.join(BASE_DIR, 'excluded_processes.json')):
    print("⚠️ excluded_processes.json not found. Creating an empty template...")
    with open(os.path.join(BASE_DIR, 'excluded_processes.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "exclude_process_names": [
                "System",
                "System Idle Process",
                "svchost.exe",
                "explorer.exe",
                "cmd.exe",
                "python.exe",
                "pythonw.exe"
            ],
            "exclude_prefixes": [
                "MicrosoftEdge",
                "Google Chrome",
                "Brave Browser"
            ]
        }, f, indent=4)
    print("Template excluded_processes.json created.")

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
        path = os.path.join(BASE_DIR, "config.json")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return {}

app_config = load_config()
base_template = app_config.get('base', ' %game% %date%')
process_names = app_config.get('process_name', {})
twitch_categories = app_config.get('TwitchCategoryName', {})

# new global for UI to display current detected game
CURRENT_GAME = 'Unknown'

# --- new: excluded processes support ---
EXCLUDED_NAMES = set()
EXCLUDED_PREFIXES = []

def load_excluded_processes():
    """Load excluded process names/prefixes from excluded_processes.json (optional)."""
    global EXCLUDED_NAMES, EXCLUDED_PREFIXES
    path = os.path.join(BASE_DIR, 'excluded_processes.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        EXCLUDED_NAMES = {n.lower() for n in data.get('exclude_process_names', []) if n}
        EXCLUDED_PREFIXES = [p.lower() for p in data.get('exclude_prefixes', []) if p]
        print(f"🔒 Loaded exclusions: {len(EXCLUDED_NAMES)} names, {len(EXCLUDED_PREFIXES)} prefixes")
    except FileNotFoundError:
        print("🔎 excluded_processes.json not found — no exclusions loaded.")
    except Exception as e:
        print(f"❌ Error loading excluded_processes.json: {e}")

def is_excluded_process(proc_name: str) -> bool:
    """Return True if proc_name is in the exclusion lists."""
    if not proc_name:
        return True
    name_l = proc_name.lower()
    if name_l in EXCLUDED_NAMES:
        return True
    for prefix in EXCLUDED_PREFIXES:
        if name_l.startswith(prefix):
            return True
    return False

# load exclusions now
load_excluded_processes()

# New: save current app_config back to config.json
def save_config_to_file():
    try:
        # Ensure expected keys exist
        if 'process_name' not in app_config:
            app_config['process_name'] = {}
        if 'TwitchCategoryName' not in app_config:
            app_config['TwitchCategoryName'] = {}
        if 'base' not in app_config:
            app_config['base'] = base_template
        with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(app_config, f, ensure_ascii=False, indent=4)
        print("🔖 config.json saved.")
    except Exception as e:
        print(f"❌ Failed to save config.json: {e}")

# New: function to add or update a custom game/process/category
def add_custom_game(game_name: str, process_name_str: str, twitch_category: str = None):
    """
    Add or update a mapping: game_name -> process_name_str and optional twitch_category.
    Saves to config.json and reloads runtime variables.
    """
    try:
        if not game_name or not process_name_str:
            raise ValueError("game_name and process_name are required")
        # update in-memory config
        if 'process_name' not in app_config:
            app_config['process_name'] = {}
        app_config['process_name'][game_name] = process_name_str
        if twitch_category:
            if 'TwitchCategoryName' not in app_config:
                app_config['TwitchCategoryName'] = {}
            app_config['TwitchCategoryName'][game_name] = twitch_category
        save_config_to_file()
        # reload runtime maps
        global process_names, twitch_categories
        process_names = app_config.get('process_name', {})
        twitch_categories = app_config.get('TwitchCategoryName', {})
        print(f"✅ Added/updated custom game: {game_name} -> {process_name_str} (Category: {twitch_category})")
        return True
    except Exception as e:
        print(f"❌ Error adding custom game: {e}")
        return False

def get_current_game():
    print("Scanning running processes...")
    detected_processes = []
    game_processes_found = []
    
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            process_name = proc.info['name']
            # skip excluded / system processes
            if is_excluded_process(process_name):
                continue
            detected_processes.append(process_name)
            
            # Check against our game processes
            for game, expected_proc in process_names.items():
                # Try exact match first, then case-insensitive substring match
                if process_name == expected_proc or (process_name and process_name.lower() == expected_proc.lower()) \
                   or (expected_proc and expected_proc.lower() in process_name.lower()):
                    print(f"🎮 FOUND GAME: {game} (Process: {process_name})")
                    game_processes_found.append((game, process_name))
                    return game
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Debug output
    if game_processes_found:
        print(f"Multiple game processes found: {game_processes_found}")
    
    print(f"Looking for: {list(process_names.values())}")
    print("Recent (non-excluded) processes detected:")
    for proc in detected_processes[-10:]:  # Last 10 processes
        print(f"  - {proc}")
    
    return 'Just Chatting'  # default game if none found

# Enhanced debug function
def debug_all_processes():
    print("\n=== DEBUG: All Running Processes (Full Scan) ===")
    all_processes = []
    excluded_count = 0
    
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            name = proc.info['name']
            if is_excluded_process(name):
                excluded_count += 1
                continue
            all_processes.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Remove duplicates and sort
    unique_processes = sorted(set(all_processes))
    
    print(f"Total unique (non-excluded) processes: {len(unique_processes)}  — excluded skipped: {excluded_count}")
    print("\nLooking for these game processes:")
    for game, proc_name in process_names.items():
        print(f"  - {game}: '{proc_name}'")
    
    print("\nAll running processes (non-excluded):")
    for i, proc in enumerate(unique_processes):
        # Highlight potential matches
        for expected_proc in process_names.values():
            if expected_proc and expected_proc.lower() in proc.lower():
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
    global CURRENT_GAME
    
    print("🎮 Starting game monitoring...")
    print(f"Monitoring for {len(process_names)} games")
    
    # Initial debug scan
    debug_all_processes()
    
    while True:
        current_game = get_current_game()
        CURRENT_GAME = current_game  # update global for UI display
        
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

# New: simple Tkinter UI to view current game and add custom mappings
class AppGUI:
    def __init__(self, root):
        self.root = root
        root.title("Twitch Auto-Title — UI")
        root.geometry("1280x720")
        root.resizable(False, False)

        # Current game display
        tk.Label(root, text="Current Detected Game:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=(10,0))
        self.current_label = tk.Label(root, text=CURRENT_GAME, font=('Segoe UI', 12))
        self.current_label.pack(anchor='w', padx=10)

        # Mappings list
        tk.Label(root, text="Configured Game -> Process mappings:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=(10,0))
        self.listbox = tk.Listbox(root, height=8, width=72)
        self.listbox.pack(padx=10, pady=(0,6))
        self.refresh_mappings()

        btn_frame = tk.Frame(root)
        btn_frame.pack(fill='x', padx=10)
        tk.Button(btn_frame, text="Reload config.json", command=self.reload_config).pack(side='left')
        tk.Button(btn_frame, text="Remove selected", command=self.remove_selected).pack(side='left', padx=6)
        tk.Button(btn_frame, text="Edit Exclusions", command=self.open_exclusions_editor).pack(side='left', padx=6)

        # Add custom mapping inputs
        frm = tk.Frame(root)
        frm.pack(fill='x', padx=10, pady=(10,0))
        tk.Label(frm, text="Game Name:").grid(row=0, column=0, sticky='e')
        tk.Label(frm, text="Process (select):").grid(row=1, column=0, sticky='ne')
        tk.Label(frm, text="Twitch Category:").grid(row=2, column=0, sticky='e')

        self.entry_game = tk.Entry(frm, width=40)
        # replaced free-text process entry with a selectable listbox
        self.proc_listbox = tk.Listbox(frm, height=6, width=40, exportselection=False)
        self.entry_cat = tk.Entry(frm, width=40)
        self.entry_game.grid(row=0, column=1, padx=6, pady=2)
        self.proc_listbox.grid(row=1, column=1, padx=6, pady=2)
        self.entry_cat.grid(row=2, column=1, padx=6, pady=2)

        # Button to refresh detected processes list
        proc_btn_frame = tk.Frame(frm)
        proc_btn_frame.grid(row=1, column=2, padx=(4,0), sticky='n')
        tk.Button(proc_btn_frame, text="Refresh", command=self.refresh_process_list).pack(pady=(0,2))
        tk.Button(proc_btn_frame, text="Auto-select match", command=self.auto_select_process).pack()

        tk.Button(root, text="Add / Update mapping", command=self.add_mapping).pack(pady=8)
        self.status_label = tk.Label(root, text="", fg='green')
        self.status_label.pack()

        # populate mappings and running processes
        self.refresh_mappings()
        self.refresh_process_list()
        # update process list periodically (60 seconds)
        self.root.after(60000, self._periodic_process_refresh)

        # Periodically update current game label
        self._update_loop()

        # Handle close
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def refresh_mappings(self):
        self.listbox.delete(0, tk.END)
        for game, proc in sorted(process_names.items()):
            cat = twitch_categories.get(game, '')
            self.listbox.insert(tk.END, f"{game} -> {proc}   [Category: {cat}]")

    def refresh_process_list(self):
        # populate proc_listbox with unique running process names (exclude system/non-game)
        try:
            procs = []
            for p in psutil.process_iter(['name']):
                try:
                    name = p.info['name']
                    if not name or is_excluded_process(name):
                        continue
                    procs.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs = sorted(set(procs), key=str.lower)
            self.proc_listbox.delete(0, tk.END)
            for proc in procs:
                self.proc_listbox.insert(tk.END, proc)
        except Exception as e:
            print(f"❌ Failed to refresh process list: {e}")

    def _periodic_process_refresh(self):
        self.refresh_process_list()
        # schedule next refresh in 60 seconds
        self.root.after(60000, self._periodic_process_refresh)

    def auto_select_process(self):
        # try to auto-select the most likely match from configured process names
        best_match_index = None
        configured = [v.lower() for v in process_names.values()]
        for i in range(self.proc_listbox.size()):
            item = self.proc_listbox.get(i)
            for cfg in configured:
                if cfg in item.lower() or item.lower() in cfg:
                    best_match_index = i
                    break
            if best_match_index is not None:
                break
        if best_match_index is not None:
            self.proc_listbox.selection_clear(0, tk.END)
            self.proc_listbox.selection_set(best_match_index)
            self.proc_listbox.see(best_match_index)
            messagebox.showinfo("Auto-select", f"Selected: {self.proc_listbox.get(best_match_index)}")
        else:
            messagebox.showinfo("Auto-select", "No likely match found.")

    def reload_config(self):
        global app_config, process_names, twitch_categories, base_template
        app_config = load_config()
        base_template = app_config.get('base', base_template)
        process_names = app_config.get('process_name', {})
        twitch_categories = app_config.get('TwitchCategoryName', {})
        self.refresh_mappings()
        messagebox.showinfo("Reloaded", "config.json reloaded.")

    def add_mapping(self):
        game = self.entry_game.get().strip()
        # get selected process from listbox instead of typing
        sel = self.proc_listbox.curselection()
        if not game:
            messagebox.showwarning("Missing", "Please provide a Game Name.")
            return
        if not sel:
            messagebox.showwarning("Missing", "Please select a Process from the list.")
            return
        proc = self.proc_listbox.get(sel[0]).strip()
        cat = self.entry_cat.get().strip()
        ok = add_custom_game(game, proc, cat if cat else None)
        if ok:
            self.entry_game.delete(0, tk.END)
            self.entry_cat.delete(0, tk.END)
            self.refresh_mappings()
            self.status_label.config(text=f"Added/Updated: {game} -> {proc}", fg='green')
        else:
            self.status_label.config(text="Failed to add mapping", fg='red')

    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose a mapping to remove.")
            return
        idx = sel[0]
        item = self.listbox.get(idx)
        # parse game name from listbox line
        game = item.split("->")[0].strip()
        if messagebox.askyesno("Confirm", f"Remove mapping for '{game}'?"):
            try:
                if 'process_name' in app_config and game in app_config['process_name']:
                    del app_config['process_name'][game]
                if 'TwitchCategoryName' in app_config and game in app_config['TwitchCategoryName']:
                    del app_config['TwitchCategoryName'][game]
                save_config_to_file()
                # reload runtime maps
                global process_names, twitch_categories
                process_names = app_config.get('process_name', {})
                twitch_categories = app_config.get('TwitchCategoryName', {})
                self.refresh_mappings()
                messagebox.showinfo("Removed", f"Removed mapping for '{game}'.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to remove: {e}")

    def _update_loop(self):
        # update the current detected game every second
        self.current_label.config(text=CURRENT_GAME)
        self.root.after(1000, self._update_loop)

    def on_close(self):
        # stop observer and exit
        try:
            observer.stop()
        except Exception:
            pass
        try:
            observer.join(timeout=1)
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)  # ensure background threads exit

    # new: open exclusions editor window
    def open_exclusions_editor(self):
        win = tk.Toplevel(self.root)
        win.title("Edit Excluded Processes")
        win.geometry("960x420")
        win.transient(self.root)

        frame = tk.Frame(win)
        frame.pack(fill='both', expand=True, padx=8, pady=8)

        # Excluded names column
        left = tk.Frame(frame)
        left.pack(side='left', fill='both', expand=True, padx=(0,6))
        tk.Label(left, text="Excluded Process Names (one per line)").pack(anchor='w')
        # allow multi-select for names
        self.exc_names_lb = tk.Listbox(left, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_names_lb.pack(fill='both', expand=True, padx=2, pady=4)
        en_frame = tk.Frame(left)
        en_frame.pack(fill='x')
        self.exc_name_entry = tk.Entry(en_frame)
        self.exc_name_entry.pack(side='left', fill='x', expand=True)
        tk.Button(en_frame, text="Add", command=self.add_excluded_name).pack(side='left', padx=6)
        tk.Button(left, text="Remove Selected", command=self.remove_selected_excluded_name).pack(pady=(6,0))

        # Running processes column (for selection to exclude)
        middle = tk.Frame(frame)
        middle.pack(side='left', fill='both', expand=True, padx=(6,6))
        tk.Label(middle, text="Running Processes (select to add to exclusions)").pack(anchor='w')
        # allow multi-select for running processes
        self.running_procs_lb = tk.Listbox(middle, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.running_procs_lb.pack(fill='both', expand=True, padx=2, pady=4)
        rp_btns = tk.Frame(middle)
        rp_btns.pack(fill='x')
        tk.Button(rp_btns, text="Refresh", command=self.refresh_running_processes_list).pack(side='left')
        tk.Button(rp_btns, text="Add Selected → Excluded Names", command=self.add_selected_running_to_excluded_name).pack(side='left', padx=6)
        tk.Button(rp_btns, text="Add Selected → Excluded Prefixes", command=self.add_selected_running_to_excluded_prefix).pack(side='left', padx=6)

        # Excluded prefixes column
        right = tk.Frame(frame)
        right.pack(side='left', fill='both', expand=True, padx=(6,0))
        tk.Label(right, text="Excluded Prefixes (starts-with)").pack(anchor='w')
        # allow multi-select for prefixes
        self.exc_prefix_lb = tk.Listbox(right, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_prefix_lb.pack(fill='both', expand=True, padx=2, pady=4)
        pre_frame = tk.Frame(right)
        pre_frame.pack(fill='x')
        self.exc_prefix_entry = tk.Entry(pre_frame)
        self.exc_prefix_entry.pack(side='left', fill='x', expand=True)
        tk.Button(pre_frame, text="Add", command=self.add_excluded_prefix).pack(side='left', padx=6)
        tk.Button(right, text="Remove Selected", command=self.remove_selected_excluded_prefix).pack(pady=(6,0))

        # Save / Close
        btns = tk.Frame(win)
        btns.pack(fill='x', pady=(6,8), padx=8)
        tk.Button(btns, text="Save", command=self.save_exclusions_and_close).pack(side='right', padx=6)
        tk.Button(btns, text="Close", command=win.destroy).pack(side='right')

        # populate lists
        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()

    def refresh_running_processes_list(self):
        """Populate the running processes listbox (exclude already excluded/system processes)."""
        try:
            procs = []
            for p in psutil.process_iter(['name']):
                try:
                    name = p.info['name']
                    if not name:
                        continue
                    # skip if already excluded by exact name or prefix
                    if is_excluded_process(name):
                        continue
                    procs.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs = sorted(set(procs), key=str.lower)
            self.running_procs_lb.delete(0, tk.END)
            for proc in procs:
                self.running_procs_lb.insert(tk.END, proc)
        except Exception as e:
            print(f"❌ Failed to refresh running processes list: {e}")

    # ---- 新增缺少的方法，修正 AttributeError ----
    def refresh_exclusions_lists(self):
        """Populate exclusion listboxes from global EXCLUDED_NAMES / EXCLUDED_PREFIXES."""
        try:
            self.exc_names_lb.delete(0, tk.END)
            for name in sorted(EXCLUDED_NAMES):
                self.exc_names_lb.insert(tk.END, name)
            self.exc_prefix_lb.delete(0, tk.END)
            for p in EXCLUDED_PREFIXES:
                self.exc_prefix_lb.insert(tk.END, p)
        except Exception as e:
            print(f"❌ Failed to refresh exclusions lists: {e}")

    def add_excluded_name(self):
        val = (self.exc_name_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a process name to exclude.")
            return
        EXCLUDED_NAMES.add(val.lower())
        self.exc_name_entry.delete(0, tk.END)
        self.refresh_exclusions_lists()

    def remove_selected_excluded_name(self):
        sel = self.exc_names_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more names to remove.")
            return
        # remove all selected (iterate reversed to avoid index shift)
        for i in reversed(sel):
            name = self.exc_names_lb.get(i)
            EXCLUDED_NAMES.discard(name.lower())
        self.refresh_exclusions_lists()

    def add_excluded_prefix(self):
        val = (self.exc_prefix_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a prefix to exclude.")
            return
        p = val.lower()
        if p not in EXCLUDED_PREFIXES:
            EXCLUDED_PREFIXES.append(p)
        self.exc_prefix_entry.delete(0, tk.END)
        self.refresh_exclusions_lists()

    def remove_selected_excluded_prefix(self):
        sel = self.exc_prefix_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more prefixes to remove.")
            return
        for i in reversed(sel):
            p = self.exc_prefix_lb.get(i)
            try:
                EXCLUDED_PREFIXES.remove(p)
            except ValueError:
                pass
        self.refresh_exclusions_lists()

    def save_exclusions_and_close(self):
        try:
            path = os.path.join(os.path.dirname(__file__), 'excluded_processes.json')
            data = {
                'exclude_process_names': sorted(list(EXCLUDED_NAMES)),
                'exclude_prefixes': EXCLUDED_PREFIXES
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            # reload to ensure consistency
            load_excluded_processes()
            ok = True
            print(f"🔖 Saved exclusions: {len(EXCLUDED_NAMES)} names, {len(EXCLUDED_PREFIXES)} prefixes")
        except Exception as e:
            ok = False
            print(f"❌ Failed to save excluded_processes.json: {e}")
        if ok:
            messagebox.showinfo("Saved", "excluded_processes.json updated.")
        else:
            messagebox.showerror("Error", "Failed to save excluded_processes.json.")
        # refresh process list and UI mappings after save
        try:
            self.refresh_process_list()
        except Exception:
            pass
        # close any open editor windows by destroying their top-level (caller will close)
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.title() == "Edit Excluded Processes":
                w.destroy()

    def add_selected_running_to_excluded_name(self):
        sel = self.running_procs_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more running processes to add to excluded names.")
            return
        added = []
        for i in sel:
            name = self.running_procs_lb.get(i).strip()
            if not name:
                continue
            EXCLUDED_NAMES.add(name.lower())
            added.append(name)
        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()
        if added:
            messagebox.showinfo("Added", f"Added to excluded names:\n{', '.join(added)}")
        else:
            messagebox.showinfo("Added", "No valid names were added.")

    def add_selected_running_to_excluded_prefix(self):
        sel = self.running_procs_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more running processes to add as prefix exclusions.")
            return
        added = []
        for i in sel:
            name = self.running_procs_lb.get(i).strip()
            if not name:
                continue
            prefix = name.split('.', 1)[0].lower()
            if prefix not in EXCLUDED_PREFIXES:
                EXCLUDED_PREFIXES.append(prefix)
                added.append(prefix)
        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()
        if added:
            messagebox.showinfo("Added", f"Added prefixes:\n{', '.join(added)}")
        else:
            messagebox.showinfo("Added", "No new prefixes were added.")

if __name__ == '__main__':
    print("🎬 Twitch Stream Auto-Title Started!")
    print(f"🔍 Monitoring for games: {list(process_names.keys())}")
    
    # start file observer (existing behavior)
    event_handler = ConfigFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()

    # run monitor in background thread so we can run a GUI in main thread
    monitor_thread = threading.Thread(target=monitor_game_and_update_title, daemon=True)
    monitor_thread.start()

    # Start UI
    root = tk.Tk()
    app = AppGUI(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
        observer.stop()
    observer.join()