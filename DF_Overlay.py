import sys 
import os
import asyncio
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import colorchooser, ttk
import time
import statistics
import requests
import win32gui
import win32ui
import win32con
import numpy as np
import cv2
from PIL import Image, ImageTk
from bs4 import BeautifulSoup
import ctypes
import keyboard
import json
import subprocess

settings_win = None

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
GITHUB_VERSION_PUSH = "1.75"
CURRENT_VERSION = "1.73"

# Fetch patch notes
def fetch_patch_notes():
    try:
        url = "https://gaslightgod.com/verify/patchnotes.json"
        data = requests.get(url, timeout=5).json()
        title = data.get("title", "Patch Notes")
        notes = data.get("notes", [])
        version = data.get("version", "")
        return f"{title} (v{version})\n\n" + "\n".join(notes)
    except Exception as e:
        return f"Failed to load patch notes.\n\nError: {e}"

# Check if we're outdated
def check_latest_version():
    try:
        url = "https://gaslightgod.com/verify/version.json"
        data = requests.get(url, timeout=5).json()
        latest = data.get("latest_version", CURRENT_VERSION)
        download_url = data.get("download_url", "")
        msg = data.get("message", "")
        return (latest != CURRENT_VERSION), latest, download_url, msg
    except:
        return False, CURRENT_VERSION, "", ""

# Remote killswitch check - TODO: maybe merge version/killswitch into single fetch later
def check_kill_switch():
    try:
        url = "https://gaslightgod.com/verify/killswitch.json"
        data = requests.get(url, timeout=5).json()
        return data.get("enabled", True), data.get("message", ""), data.get("force_close", True)
    except:
        return True, "", False

def show_motd(data):
    messagebox.showinfo(data.get("title", "Message"), data.get("message", ""))

PID_CONFIG_FILE = "pid.cfg"

def save_pid(pid):
    try:
        with open(PID_CONFIG_FILE, "w") as f:
            f.write(pid)
    except:
        pass

def load_saved_pid():
    try:
        if os.path.exists(PID_CONFIG_FILE):
            return open(PID_CONFIG_FILE).read().strip()
    except:
        pass
    return ""

SETTINGS_FILE = "settings.json"

# Save user settings so overlay looks the same next startup
def save_settings():
    data = {
        "TEXT_COLOR": TEXT_COLOR,
        "SCALE": SCALE,
        "GOAL_LEVEL": GOAL_LEVEL,
        "FONT_FAMILY": FONT_FAMILY,
        "LOCK_POSITION": LOCK_POSITION,
        "SHOW_EXP": SHOW_EXP,
        "SHOW_AVG": SHOW_AVG,
        "SHOW_NEXT": SHOW_NEXT,
        "SHOW_GOAL": SHOW_GOAL,
        "SHOW_CLOCK": SHOW_CLOCK,
        "EXP_MODE": EXP_MODE,
        "ICON_SCALE": ICON_SCALE,
        "OVERLAY_X": overlay.winfo_x(),
        "OVERLAY_Y": overlay.winfo_y()
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

last_server_update = None
server_update_intervals = []

# Global runtime state
FONT_FAMILY = "Fira Code"
PID = ""
running = True

# Hunger state + scaling
current_hunger_state = "UNKNOWN"
ICON_SCALE = 1.0

REAL_LEVEL = 1
EXP_INSIDE = 0
REAL_EXP = 0

last_exp = None
last_change_time = None
exp_history = []
exp_window = []

# UI toggles
EXP_MODE = "RAW"
TEXT_COLOR = "#0BF0F0"
SCALE = 1.0
LOCK_POSITION = False
CLICK_THROUGH = False
SHOW_EXP = True
SHOW_AVG = True
SHOW_NEXT = True
SHOW_GOAL = True
SHOW_CLOCK = True

BASE_EXP = 22
BASE_AVG = 18
BASE_LVL = 16

GOAL_LEVEL = 415
NEXT_SECONDS = 0
GOAL_SECONDS = 0

debug_win = None
debug_text = None

# Helper for resolving resources in exe mode
def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

# Load XP table - TODO: consider caching this
def load_levels():
    d = {}
    path = resource_path("levels.txt")
    for line in open(path):
        if line.strip():
            a, b = line.split()
            d[int(a)] = int(b)
    return d

LEVELS = load_levels()
MAX_LEVEL = max(LEVELS.keys())

# Profile fetcher
def fetch_profile(pid, fetch_level=False):
    url = f"https://www.dfprofiler.com/profile/view/{pid}"
    try:
        r = session.get(url, timeout=15)
    except:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    e = soup.find("div", {"data-bind": lambda v: v and "experience" in v})
    if not e:
        return None

    try:
        inside = int(e.get_text(strip=True).split(":")[1].split("/")[0].replace(",", ""))
    except:
        return None

    if not fetch_level:
        return inside

    lvl_field = soup.find("div", {"data-bind": lambda v: v and "profession_level" in v})
    if not lvl_field:
        return None

    try:
        lvl = int(lvl_field.get_text(strip=True).split()[-1])
    except:
        lvl = None

    return lvl, inside

# Apply UI settings to labels - triggers after settings window closes
def apply_settings():
    exp_size = int(BASE_EXP * SCALE)
    avg_size = int(BASE_AVG * SCALE)
    lvl_size = int(BASE_LVL * SCALE)

    if SHOW_EXP:
        label_exp.config(fg=TEXT_COLOR, font=(FONT_FAMILY, exp_size, "bold"))
        label_exp.pack()
    else:
        label_exp.pack_forget()

    if SHOW_AVG:
        label_avg.config(fg=TEXT_COLOR, font=(FONT_FAMILY, avg_size))
        label_avg.pack()
    else:
        label_avg.pack_forget()

    if SHOW_NEXT:
        label_next.config(fg=TEXT_COLOR, font=(FONT_FAMILY, lvl_size))
        label_next.pack()
    else:
        label_next.pack_forget()

    if SHOW_GOAL:
        label_goal.config(fg=TEXT_COLOR, font=(FONT_FAMILY, lvl_size))
        label_goal.pack()
    else:
        label_goal.pack_forget()

    if SHOW_CLOCK:
        label_clock.pack()
        label_clock.config(fg=TEXT_COLOR, font=(FONT_FAMILY, int(BASE_LVL * SCALE)))
    else:
        label_clock.pack_forget()

    update_icon_scale()

# Enable click-through so overlay doesn't block gameplay
def apply_click_through():
    global overlay
    hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    if CLICK_THROUGH:
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
    else:
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style & ~0x20)

# Load saved settings
def load_settings():
    global TEXT_COLOR, SCALE, GOAL_LEVEL, FONT_FAMILY
    global LOCK_POSITION, SHOW_EXP, SHOW_AVG, SHOW_NEXT
    global SHOW_GOAL, SHOW_CLOCK, EXP_MODE, ICON_SCALE

    if not os.path.exists(SETTINGS_FILE):
        return

    data = json.load(open(SETTINGS_FILE))

    TEXT_COLOR = data.get("TEXT_COLOR", TEXT_COLOR)
    SCALE = data.get("SCALE", SCALE)
    GOAL_LEVEL = data.get("GOAL_LEVEL", GOAL_LEVEL)
    FONT_FAMILY = data.get("FONT_FAMILY", FONT_FAMILY)
    LOCK_POSITION = data.get("LOCK_POSITION", LOCK_POSITION)
    SHOW_EXP = data.get("SHOW_EXP", SHOW_EXP)
    SHOW_AVG = data.get("SHOW_AVG", SHOW_AVG)
    SHOW_NEXT = data.get("SHOW_NEXT", SHOW_NEXT)
    SHOW_GOAL = data.get("SHOW_GOAL", SHOW_GOAL)
    SHOW_CLOCK = data.get("SHOW_CLOCK", True)
    EXP_MODE = data.get("EXP_MODE", EXP_MODE)
    ICON_SCALE = data.get("ICON_SCALE", ICON_SCALE)

    # Update hunger icon scale - TODO: maybe move to its own small module someday
def update_icon_scale():
    global hunger_icon, icon_item
    base = 48
    size = int(base * SCALE * ICON_SCALE)
    if size < 8:
        size = 8

    img = hunger_img_original.resize((size, size), Image.LANCZOS)
    hunger_icon = ImageTk.PhotoImage(img)
    icon_canvas.image = hunger_icon

    icon_canvas.config(width=size, height=size)
    icon_canvas.itemconfig(icon_item, image=hunger_icon)
    icon_canvas.coords(icon_item, size // 2, size // 2)

# Small debug window for live logs
def open_debug():
    global debug_win, debug_text

    if debug_win and tk.Toplevel.winfo_exists(debug_win):
        debug_win.lift()
        return

    debug_win = tk.Toplevel(overlay)
    debug_win.title("Debug")
    debug_win.config(bg="black")
    debug_win.geometry("500x400")

    debug_text = tk.Text(debug_win, bg="black", fg="#00FF00",
                         insertbackground="#00FF00")
    debug_text.pack(fill="both", expand=True)

    

    tk.Button(debug_win, text="Clear",
              command=lambda: debug_text.delete("1.0", "end")).pack()
    

    def on_debug_close():
        global debug_win, debug_text
        try:
            debug_win.destroy()
        except:
            pass
        debug_win = None
        debug_text = None

    debug_win.protocol("WM_DELETE_WINDOW", on_debug_close)

# Send debug messages
def debug_log(msg):
    global debug_text
    if not debug_text:
        return
    try:
        debug_text.after(0, lambda: (
            debug_text.insert("end", msg + "\n"),
            debug_text.see("end")
        ))
    except:
        pass

# Settings window - pretty huge but works for now
def open_settings():
    global settings_win

    if settings_win is not None and tk.Toplevel.winfo_exists(settings_win):
        settings_win.lift()
        return

    # Pause click-through while setting things
    global CLICK_THROUGH
    CLICK_THROUGH = False
    apply_click_through()

    settings_win = tk.Toplevel(overlay)
    w = settings_win
    w.config(bg="black")
    w.attributes("-topmost", True)
    w.overrideredirect(True)

    def sd(e):
        w.x = e.x
        w.y = e.y

    def dr(e):
        w.geometry(f"+{w.winfo_x() + (e.x - w.x)}+{w.winfo_y() + (e.y - w.y)}")

    header = tk.Frame(w, bg="black")
    header.pack(fill="x")

    title_label = tk.Label(header, text="Settings", fg=TEXT_COLOR,
                           bg="black", font=("Consolas", 14, "bold"))
    title_label.pack(side="left", padx=5)

    close_btn = tk.Button(header, text="X", fg="black", bg=TEXT_COLOR,
                          bd=0, font=("Consolas", 12, "bold"),
                          padx=6, command=w.destroy)
    close_btn.pack(side="right", padx=5)

    title_label.bind("<ButtonPress-1>", sd)
    title_label.bind("<B1-Motion>", dr)
    header.bind("<ButtonPress-1>", sd)
    header.bind("<B1-Motion>", dr)

    nb = ttk.Notebook(w)
    nb.pack(padx=10, pady=5)

    st = ttk.Style()
    st.theme_use("default")
    st.configure("TNotebook", background="black", borderwidth=0)
    st.configure("TNotebook.Tab", background="black", foreground=TEXT_COLOR)
    st.map(
        "TNotebook.Tab",
        background=[("selected", "gray20")],
        foreground=[("selected", TEXT_COLOR)]
    )

    # GENERAL TAB
    g = tk.Frame(nb, bg="black")
    nb.add(g, text="General")

    lock = tk.BooleanVar(value=LOCK_POSITION)
    tk.Checkbutton(g, text="Lock Overlay Position", variable=lock,
                   fg=TEXT_COLOR, bg="black",
                   selectcolor="black").pack(pady=5)

    v1 = tk.BooleanVar(value=SHOW_EXP)
    v2 = tk.BooleanVar(value=SHOW_AVG)
    v3 = tk.BooleanVar(value=SHOW_NEXT)
    v4 = tk.BooleanVar(value=SHOW_GOAL)
    v6 = tk.BooleanVar(value=SHOW_CLOCK)

    for tx, v in [
        ("Show EXP/hr", v1),
        ("Show AVG", v2),
        ("Show Next Level ETA", v3),
        ("Show Goal Level ETA", v4),
        ("Show Clock", v6)
    ]:
        tk.Checkbutton(g, text=tx, variable=v, fg=TEXT_COLOR,
                       bg="black", selectcolor="black").pack(pady=2)

    tk.Label(g, text="EXP Rate Mode:", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack(pady=(10, 3))

    cmb = ttk.Combobox(g, values=["RAW", "AVG3", "AVG5"], state="readonly")
    cmb.set(EXP_MODE)
    cmb.pack(pady=(0, 10))

    tk.Label(g, text="Set Goal Level:", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack(pady=(10, 3))

    ge = tk.Entry(
        g, bg="black", fg=TEXT_COLOR,
        insertbackground=TEXT_COLOR, justify="center")
    ge.insert(0, str(GOAL_LEVEL))
    ge.pack(pady=(0, 20))

    # APPEARANCE TAB
    a = tk.Frame(nb, bg="black")
    nb.add(a, text="Appearance")

    tk.Label(a, text="- Text Color -", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack(pady=(10, 3))

    ce = tk.Entry(
        a, bg="black", fg=TEXT_COLOR,
        insertbackground=TEXT_COLOR, justify="center")
    ce.insert(0, TEXT_COLOR)
    ce.pack()

    def pc():
        c = colorchooser.askcolor(title="Choose Text Color")
        if c and c[1]:
            ce.delete(0, "end")
            ce.insert(0, c[1])

    tk.Button(a, text="Pick Color", fg="black",
              bg=TEXT_COLOR, command=pc).pack(pady=8)

    tk.Label(a, text="- Font -", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack()

    fb = ttk.Combobox(
        a,
        values=["Consolas", "Courier New", "Lucida Console",
                "Fira Code", "JetBrains Mono"],
        state="readonly"
    )
    fb.set(FONT_FAMILY)
    fb.pack(pady=(0, 10))

    tk.Label(a, text="- Scale -", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack()

    se = tk.Entry(a, bg="black", fg=TEXT_COLOR,
                  insertbackground=TEXT_COLOR, justify="center")
    se.insert(0, str(SCALE))
    se.pack(pady=10)

    tk.Label(a, text="- Hunger Icon Size -", fg=TEXT_COLOR,
             bg="black", font=("Consolas", 12, "bold")).pack(pady=(10, 3))

    icon_entry = tk.Entry(a, bg="black", fg=TEXT_COLOR,
                          insertbackground=TEXT_COLOR, justify="center")
    icon_entry.insert(0, str(ICON_SCALE))
    icon_entry.pack()

    # INFO TAB
    i = tk.Frame(nb, bg="black")
    nb.add(i, text="Info")

    tk.Button(i, text="Open Debug Window", fg="black",
              bg=TEXT_COLOR, command=open_debug).pack(pady=10)

    tk.Button(i, text="Update Now", fg="black",
              bg=TEXT_COLOR, command=run_updater).pack(pady=5)

    def open_patch_notes():
        txt = fetch_patch_notes()
        w = tk.Toplevel(overlay)
        w.title("Patch Notes")
        w.config(bg="black")
        w.geometry("500x400")
        t = tk.Text(w, bg="black", fg=TEXT_COLOR,
                    insertbackground=TEXT_COLOR, wrap="word")
        t.pack(fill="both", expand=True)
        t.insert("end", txt)
        t.config(state="disabled")

    tk.Button(i, text="View Patch Notes", fg="black",
              bg=TEXT_COLOR, command=open_patch_notes).pack(pady=5)

    tk.Label(
        i, text=f"Version {CURRENT_VERSION}\n", fg=TEXT_COLOR,
        bg="black", font=("Consolas", 14)
    ).pack()

    tk.Label(
        i, text="Overlay by: GaslightGod\n", fg=TEXT_COLOR,
        bg="black", font=("Consolas", 12)
    ).pack()

    tk.Label(
        i, text="https://gaslightgod.com\n", fg=TEXT_COLOR,
        bg="black", font=("Consolas", 10)
    ).pack()

    tk.Label(
        i, text="Discord: TheGaslightGod\n", fg=TEXT_COLOR,
        bg="black", font=("Consolas", 10)
    ).pack()

    tk.Label(
        i, text="Special thanks to Karmash for beta testing\n",
        fg=TEXT_COLOR, bg="black", font=("Consolas", 10)
    ).pack()

        # Save settings when user hits Apply
    def sv():
        global TEXT_COLOR, SCALE, GOAL_LEVEL, FONT_FAMILY
        global LOCK_POSITION, SHOW_EXP, SHOW_AVG, SHOW_NEXT
        global SHOW_GOAL, EXP_MODE, SHOW_CLOCK, ICON_SCALE

        TEXT_COLOR = ce.get()

        try:
            SCALE = float(se.get())
        except:
            pass

        try:
            ICON_SCALE = float(icon_entry.get())
        except:
            ICON_SCALE = 1.0

        LOCK_POSITION = lock.get()
        CLICK_THROUGH = LOCK_POSITION
        apply_click_through()

        SHOW_EXP = v1.get()
        SHOW_AVG = v2.get()
        SHOW_NEXT = v3.get()
        SHOW_GOAL = v4.get()
        SHOW_CLOCK = v6.get()
        FONT_FAMILY = fb.get()
        EXP_MODE = cmb.get()

        try:
            new_gl = int(ge.get())
            if new_gl in LEVELS:
                GOAL_LEVEL = new_gl
        except:
            pass

        if exp_history:
            global REAL_EXP, GOAL_SECONDS
            REAL_EXP = LEVELS[REAL_LEVEL] + EXP_INSIDE
            xp_goal_total = LEVELS.get(GOAL_LEVEL, REAL_EXP)
            xp_remaining = xp_goal_total - REAL_EXP

            if xp_remaining < 0:
                xp_remaining = 0
            try:
                avg_rate = statistics.mean(exp_history)
            except statistics.StatisticsError:
                avg_rate = 0

            if avg_rate > 0:
                GOAL_SECONDS = int((xp_remaining / avg_rate) * 3600)
            else:
                GOAL_SECONDS = 0


        if SHOW_NEXT:
            label_next.config(text=f"Next LV: {format_eta(NEXT_SECONDS / 3600)}")
        if SHOW_GOAL:
            label_goal.config(text=f"Goal {GOAL_LEVEL}: {format_eta(GOAL_SECONDS / 3600)}")

        apply_settings()
        save_settings()

    tk.Button(w, text="Apply", fg="black", bg=TEXT_COLOR, command=sv).pack(pady=10)

    # Restore click-through after closing settings
    def on_close():
        global settings_win, CLICK_THROUGH
        CLICK_THROUGH = LOCK_POSITION
        apply_click_through()
        try:
            settings_win.destroy()
        except:
            pass
        settings_win = None

    close_btn.config(command=on_close)
    w.protocol("WM_DELETE_WINDOW", on_close)

# Update logic - only runs if update is available
def run_updater():
    outdated, latest, url, msg = check_latest_version()
    if not outdated:
        messagebox.showinfo("No Update", "You are on the latest version.")
        return

    if not messagebox.askyesno("Update Available",
                               f"Version {latest} is available.\n\n{msg}\n\nUpdate now?"):
        return

    try:
        install_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        updater_path = os.path.join(install_dir, "updater.exe")

        if not os.path.exists(updater_path):
            messagebox.showerror("Updater Missing", "updater.exe not found!")
            return

        subprocess.Popen([updater_path, url])
        sys.exit(0)

    except Exception as e:
        messagebox.showerror("Update Failed", f"Error:\n{e}")

# Format ETA for display
def format_eta(h):
    if h <= 0:
        return "00:00:00"
    s = int(h * 3600)
    return f"{s // 3600:02}:{(s % 3600) // 60:02}:{s % 60:02}"

# Countdown loop adjusting ETA displays
def countdown_tick():
    global NEXT_SECONDS, GOAL_SECONDS
    while running:
        if NEXT_SECONDS > 0:
            NEXT_SECONDS -= 1
        if GOAL_SECONDS > 0:
            GOAL_SECONDS -= 1

        if SHOW_NEXT:
            label_next.config(text=f"Next LV: {format_eta(NEXT_SECONDS / 3600)}")
        if SHOW_GOAL:
            label_goal.config(text=f"Goal {GOAL_LEVEL}: {format_eta(GOAL_SECONDS / 3600)}")

        time.sleep(1)

# Main EXP processing loop - core logic for EXP/hr
async def exp_loop():
    global last_exp, last_change_time, REAL_LEVEL, EXP_INSIDE, REAL_EXP
    global NEXT_SECONDS, GOAL_SECONDS, exp_window, exp_history

    EXP_FETCH_INTERVAL = 8
    LEVEL_FETCH_INTERVAL = 1200

    last_exp_fetch = 0
    last_level_fetch = 0

    last_exp = EXP_INSIDE
    last_change_time = time.time()

    label_exp.config(text="EXP/hr: WAITING")
    label_avg.config(text="AVG: WAITING")

    # Starts here - main loop
    while running:
        now = time.time()
        inside = fetch_profile(PID, fetch_level=False)

        # If DF window is gone or profile unreadable we reset averages completely - this should fix the issue of stale data causing huge EXP/hr spikes
        hwnd = win32gui.FindWindow(None, "Dead Frontier")
        if hwnd == 0 or inside is None:
            exp_window.clear()
            exp_history.clear()
            last_exp = EXP_INSIDE
            last_change_time = time.time()

            label_exp.config(text="EXP/hr: WAITING")
            label_avg.config(text="AVG: WAITING")

            NEXT_SECONDS = 0
            GOAL_SECONDS = 0

            if SHOW_NEXT:
                label_next.config(text="Next LV: --:--:--")
            if SHOW_GOAL:
                label_goal.config(text=f"Goal {GOAL_LEVEL}: --:--:--")

            debug_log("[Window lost - EXP reset]")
            await asyncio.sleep(1)
            continue

        
        if inside is None:
            await asyncio.sleep(1)
            continue

        now = time.time()

        # If EXP drops, user died or leveled - recalc everything
        if inside < last_exp:
            # Player leveled up (EXP rolled back to inside XP)
            
            # Fetch updated level
            lvl_info = fetch_profile(PID, fetch_level=True)
            if lvl_info is not None:
                lvl, inside_value = lvl_info
                REAL_LEVEL = lvl
                EXP_INSIDE = inside_value
                REAL_EXP = LEVELS[REAL_LEVEL] + EXP_INSIDE
            else:
                # Fallback to inside if level fetch failed
                EXP_INSIDE = inside
                REAL_EXP = LEVELS[REAL_LEVEL] + inside

            # Reset exp_window and history to prevent incorrect averages
            exp_window.clear()
            exp_history.clear()

            last_change_time = now
            last_exp = inside

            label_exp.config(text="EXP/hr: WAITING")
            label_avg.config(text="AVG: WAITING")
            NEXT_SECONDS = 0
            GOAL_SECONDS = 0

            if SHOW_NEXT:
                label_next.config(text="Next LV: --:--:--")
            if SHOW_GOAL:
                label_goal.config(text=f"Goal {GOAL_LEVEL}: --:--:--")

            debug_log("[EXP RESET triggered]")
            await asyncio.sleep(1)
            continue

        # No EXP change for a while - consider idle
        if inside == last_exp:
            if now - last_change_time > 90:
                exp_window.clear()
                exp_history.clear()
                label_exp.config(text="EXP/hr: WAITING")
                label_avg.config(text="AVG: WAITING")
                NEXT_SECONDS = 0
                GOAL_SECONDS = 0
                if SHOW_NEXT:
                    label_next.config(text="Next LV: --:--:--")
                if SHOW_GOAL:
                    label_goal.config(text=f"Goal {GOAL_LEVEL}: --:--:--")
                debug_log("[Idle reset - no EXP gain]")
                last_change_time = now
            await asyncio.sleep(1)
            continue

        # EXP changed - recalc rate
        gain = inside - last_exp
        dt = now - last_change_time
        raw_rate = (gain / dt) * 3600

        exp_history.append(raw_rate)
        EXP_INSIDE = inside
        REAL_EXP = LEVELS[REAL_LEVEL] + inside

        if EXP_MODE == "RAW":
            final_rate = raw_rate
            exp_window = [raw_rate]
        else:
            exp_window.append(raw_rate)
            window_len = 3 if EXP_MODE == "AVG3" else 5
            exp_window = exp_window[-window_len:]
            final_rate = statistics.mean(exp_window)

        if SHOW_EXP:
            label_exp.config(text=f"EXP/hr: {int(final_rate):,}")

        if SHOW_AVG:
            try:
                label_avg.config(text=f"AVG: {int(statistics.mean(exp_history)):,}")
            except:
                label_avg.config(text="AVG: WAITING")


        # Next level ETA logic
        # Check for overflow and determine actual current level
        xp_total = LEVELS[REAL_LEVEL] + EXP_INSIDE
        while REAL_LEVEL < MAX_LEVEL and xp_total >= LEVELS[REAL_LEVEL + 1]:
            REAL_LEVEL += 1
        EXP_INSIDE = xp_total - LEVELS[REAL_LEVEL]
        REAL_EXP = xp_total

        # Using AVG exp rate for ETAs
        try:
            avg_rate = statistics.mean(exp_history) if exp_history else 0
        except statistics.StatisticsError:
            avg_rate = 0

        # Calculation for next level
        if REAL_LEVEL < MAX_LEVEL and avg_rate > 0:
            xp_next_level = LEVELS[REAL_LEVEL + 1]
            xp_needed = xp_next_level - xp_total

            if xp_needed < 0:
                xp_needed = 0
            NEXT_SECONDS = int((xp_needed / avg_rate) * 3600)
        else:
            NEXT_SECONDS = 0

        # ETA for goal level
        xp_goal_total = LEVELS.get(GOAL_LEVEL, xp_total)
        xp_remaining = xp_goal_total - xp_total
        if xp_remaining < 0:
            xp_remaining = 0

        if avg_rate > 0:
            GOAL_SECONDS = int((xp_remaining / avg_rate) * 3600)
        else:
            GOAL_SECONDS = 0

        if SHOW_NEXT:
            label_next.config(text=f"Next LV: {format_eta(NEXT_SECONDS / 3600)}")
        if SHOW_GOAL:
            label_goal.config(text=f"Goal {GOAL_LEVEL}: {format_eta(GOAL_SECONDS / 3600)}")

        last_change_time = now
        last_exp = inside

        debug_log(f"[EXP] +{gain:,} in {dt:.2f}s → {int(raw_rate):,}/hr")

        await asyncio.sleep(1)

        # Hunger icon blink cycle
def blink_hunger_icon():
    global blink_state, current_hunger_state

    # Only blink when hunger is FINE - otherwise hide it
    if current_hunger_state == "FINE":
        if blink_state:
            icon_canvas.itemconfig(icon_item, state="normal")
        else:
            icon_canvas.itemconfig(icon_item, state="hidden")
        blink_state = not blink_state
    else:
        icon_canvas.itemconfig(icon_item, state="hidden")

    overlay.after(500, blink_hunger_icon)

# Clock updater - Todo: let user pick 24h maybe?
def update_clock():
    if SHOW_CLOCK:
        label_clock.config(text=time.strftime("%I:%M:%S %p"))
    overlay.after(1000, update_clock)

# Watches version.json every ~30s
def version_watchdog():
    while running:
        try:
            outdated, latest, _, _ = check_latest_version()
            if outdated:
                label_update_notice.config(
                    text=f"New update available (v{latest}) - Press F5 to update"
                )
            else:
                label_update_notice.config(text="")
        except:
            pass
        time.sleep(30)

MOTD_URL = "https://www.gaslightgod.com/verify/motd.json"

def fetch_motd():
    try:
        return requests.get(MOTD_URL, timeout=5).json()
    except Exception as e:
        print("[MOTD ERROR]", e)
        return None

# Colors for hunger detection
NOURISHED = np.array([16, 235, 0])
FINE = np.array([137, 109, 0])

TOL_NOURISHED = 35
TOL_FINE = 40

# Capture game window
def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = right - left
    h = bottom - top

    wDC = win32gui.GetWindowDC(hwnd)
    dcObj = win32ui.CreateDCFromHandle(wDC)
    cDC = dcObj.CreateCompatibleDC()

    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dcObj, w, h)
    cDC.SelectObject(bmp)
    cDC.BitBlt((0, 0), (w, h), dcObj, (0, 0), win32con.SRCCOPY)

    img = np.frombuffer(bmp.GetBitmapBits(True), dtype=np.uint8)
    img = img.reshape((h, w, 4))[:, :, :3]

    win32gui.DeleteObject(bmp.GetHandle())
    cDC.DeleteDC()
    dcObj.DeleteDC()
    win32gui.ReleaseDC(hwnd, wDC)

    return img

def classify_color(avg_bgr):
    r, g, b = avg_bgr[2], avg_bgr[1], avg_bgr[0]
    col = np.array([r, g, b])

    if np.linalg.norm(col - NOURISHED) < TOL_NOURISHED:
        return "NOURISHED"
    if np.linalg.norm(col - FINE) < TOL_FINE:
        return "FINE"
    return "UNKNOWN"

# Hunger bar detection loop - runs constantly in background
def hunger_loop():
    global current_hunger_state, running

    while running:
        hwnd = win32gui.FindWindow(None, "Dead Frontier")
        if hwnd == 0:
            current_hunger_state = "UNKNOWN"
            time.sleep(0.25)
            continue

        frame = capture_window(hwnd)

        result = cv2.matchTemplate(frame, TEMPLATE, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < 0.65:
            current_hunger_state = "UNKNOWN"
            time.sleep(0.05)
            continue

        x, y = max_loc
        sample_x = x + int(template_w * 0.20)
        sample_y = y + int(template_h * 0.55)
        sample_w = int(template_w * 0.70)
        sample_h = int(template_h * 0.30)

        sample_crop = frame[sample_y:sample_y + sample_h,
                            sample_x:sample_x + sample_w]

        avg = sample_crop.mean(axis=(0, 1))
        current_hunger_state = classify_color(avg)

        time.sleep(0.05)

# PID input
def ask_for_pid():
    win = tk.Tk()
    win.title("DF Overlay Login")
    win.config(bg="black")
    win.geometry("300x170")
    win.resizable(False, False)

    saved_pid = load_saved_pid()

    tk.Label(win, text="Enter your DF PID:",
             fg="#0BF0F0", bg="black",
             font=("Consolas", 12)).pack(pady=(15, 5))

    pid_entry = tk.Entry(
        win, bg="black", fg="#0BF0F0",
        insertbackground="#0BF0F0", justify="center",
        font=("Consolas", 12)
    )
    pid_entry.pack()

    if saved_pid:
        pid_entry.insert(0, saved_pid)

    remember_var = tk.BooleanVar(value=bool(saved_pid))

    tk.Checkbutton(
        win, text="Remember my PID", variable=remember_var,
        fg="#0BF0F0", bg="black", selectcolor="black",
        font=("Consolas", 10)
    ).pack(pady=10)

    pid_value = {"value": None}

    def submit():
        v = pid_entry.get().strip()
        if not v:
            messagebox.showerror("Error", "PID cannot be empty.")
            return

        if remember_var.get():
            save_pid(v)
        else:
            if os.path.exists(PID_CONFIG_FILE):
                os.remove(PID_CONFIG_FILE)

        pid_value["value"] = v
        win.destroy()

    tk.Button(
        win, text="Continue", fg="black", bg="#0BF0F0",
        font=("Consolas", 12), command=submit
    ).pack()

    win.mainloop()
    return pid_value["value"]

# PROGRAM ENTRYPOINT - everything starts below
if __name__ == "__main__":

    # Kill switch check early - prevents opening GUI if disabled
    ks_enabled, ks_msg, ks_force = check_kill_switch()
    if not ks_enabled:
        if ks_force:
            messagebox.showerror("Disabled", ks_msg)
            sys.exit()
        else:
            messagebox.showwarning("Warning", ks_msg)

    # Ask player for PID (login)
    PID = ask_for_pid()
    if not PID:
        messagebox.showerror("Error", "PID required.")
        sys.exit()

    # Fetch MOTD - optional
    motd = fetch_motd()
    if motd:
        try:
            show_motd(motd)
        except:
            pass

    # Version check popup before loading overlay
    is_outdated, latest, dl_url, msg = check_latest_version()
    if is_outdated:
        upd = tk.Tk()
        upd.title("Update Available")
        upd.config(bg="black")
        upd.geometry("360x230")
        upd.resizable(False, False)

        tk.Label(upd, text="A new version is available!",
                 fg="#0BF0F0", bg="black",
                 font=("Consolas", 14, "bold")).pack(pady=(15, 5))

        tk.Label(
            upd,
            text=f"Current Version: {CURRENT_VERSION}\nLatest Version: {latest}",
            fg="#0BF0F0", bg="black", font=("Consolas", 12)
        ).pack(pady=5)

        tk.Label(
            upd, text=msg, fg="#0BF0F0", bg="black",
            font=("Consolas", 10), wraplength=320, justify="center"
        ).pack(pady=10)

        def do_update():
            try:
                install_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                updater_path = os.path.join(install_dir, "updater.exe")
                if not os.path.exists(updater_path):
                    messagebox.showerror("Updater Missing", "updater.exe not found!")
                    return
                subprocess.Popen([updater_path, dl_url])
                sys.exit(0)
            except Exception as e:
                messagebox.showerror("Error", f"Update failed:\n{e}")

        def skip_update():
            upd.destroy()

        tk.Button(
            upd, text="Update Now", fg="black", bg="#0BF0F0",
            font=("Consolas", 12, "bold"), padx=10, pady=4,
            command=do_update
        ).pack(pady=(5, 3))

        tk.Button(
            upd, text="Continue Without Updating",
            fg="black", bg="#0BF0F0",
            font=("Consolas", 11),
            padx=10, pady=3,
            command=skip_update
        ).pack(pady=(0, 10))

        upd.mainloop()

    # Load initial values so overlay has starting point
    init = fetch_profile(PID, fetch_level=True)
    if not init:
        messagebox.showerror("Error", "Failed to fetch profile.")
        sys.exit()

    REAL_LEVEL, EXP_INSIDE = init
    REAL_EXP = LEVELS[REAL_LEVEL] + EXP_INSIDE

    load_settings()

    # Now build the overlay window
    overlay = tk.Tk()
    overlay.wm_attributes("-topmost", True)
    overlay.wm_attributes("-transparentcolor", "black")
    overlay.config(bg="black")
    overlay.overrideredirect(True)

    hunger_img_original = Image.open(resource_path("hunger_icon.png"))
    TEMPLATE = cv2.imread(resource_path("fine_hunger.png"), cv2.IMREAD_COLOR)
    template_h, template_w = TEMPLATE.shape[:2]

        # Layout rows for UI labels
    row_icon = tk.Frame(overlay, bg="black")
    row_exp = tk.Frame(overlay, bg="black")
    row_avg = tk.Frame(overlay, bg="black")
    row_next = tk.Frame(overlay, bg="black")
    row_goal = tk.Frame(overlay, bg="black")
    row_clock = tk.Frame(overlay, bg="black")

    row_icon.pack()
    row_exp.pack()
    row_avg.pack()
    row_next.pack()
    row_goal.pack()
    row_clock.pack()

    # Clock label
    label_clock = tk.Label(
        row_clock,
        text="",
        bg="black",
        fg=TEXT_COLOR,
        font=(FONT_FAMILY, int(BASE_LVL * SCALE))
    )
    label_clock.pack()

    # Update notice (appears when version_watchdog sees a new version)
    global label_update_notice
    label_update_notice = tk.Label(
        overlay,
        text="",
        fg="#FFA500",
        bg="black",
        font=(FONT_FAMILY, int(BASE_LVL * SCALE)),
    )
    label_update_notice.pack(pady=(4, 2))

    # Main stat labels
    global label_exp, label_avg, label_next, label_goal

    label_exp = tk.Label(row_exp, text="EXP/hr: WAITING", bg="black")
    label_avg = tk.Label(row_avg, text="AVG: WAITING", bg="black")
    label_next = tk.Label(row_next, text="Next LV: --:--:--", bg="black")
    label_goal = tk.Label(row_goal, text=f"Goal {GOAL_LEVEL}: --:--:--", bg="black")

    label_exp.pack()
    label_avg.pack()

    # Hunger icon canvas
    global icon_canvas, icon_item, blink_state
    blink_state = True
    icon_canvas = tk.Canvas(row_icon, width=1, height=1, bg="black", highlightthickness=0)
    icon_item = icon_canvas.create_image(0, 0, image=None, anchor="center")
    icon_canvas.pack(pady=2)

    apply_settings()
    overlay.after(50, apply_click_through)

    # Drag logic so overlay can move unless locked
    def sd(e):
        if LOCK_POSITION:
            return
        overlay.x = e.x
        overlay.y = e.y

    def dr(e):
        if LOCK_POSITION:
            return
        overlay.geometry(
            f"+{overlay.winfo_x() + (e.x - overlay.x)}+"
            f"{overlay.winfo_y() + (e.y - overlay.y)}"
        )

    # Bind dragging to labels - TODO: allow dragging whole window area maybe?
    for wdg in (label_exp, label_avg, label_next, label_goal,
                row_exp, row_avg, row_next, row_goal):
        wdg.bind("<ButtonPress-1>", sd)
        wdg.bind("<B1-Motion>", dr)

    # Hotkeys
    overlay.bind("<Escape>", lambda _=None: overlay.destroy())
    keyboard.add_hotkey("f5", lambda: open_settings())

    # Background worker threads
    threading.Thread(target=lambda: asyncio.run(exp_loop()), daemon=True).start()
    threading.Thread(target=countdown_tick, daemon=True).start()
    threading.Thread(target=hunger_loop, daemon=True).start()
    threading.Thread(target=version_watchdog, daemon=True).start()

    blink_hunger_icon()
    update_clock()

    tk.mainloop()
