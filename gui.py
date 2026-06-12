"""
gui.py  —  FG Downloader  |  Minimal · Crisp
"""

import os
import json
import time
import ctypes
import threading
import requests
import tkinter
from tkinter import filedialog

import dearpygui.dearpygui as dpg
import downloader

# ══════════════════════════════════════════════════════════════════════════════
#  Constants & Palette
# ══════════════════════════════════════════════════════════════════════════════
W, H       = 600, 600
HISTORY_FILE = "history.json"
THUMB_FILE = ".thumb.jpg"

BG       = (10,  13,  20,  255)
CARD     = (16,  21,  32,  255)
FRAME    = (24,  30,  45,  255)
FRAME_HV = (32,  40,  58,  255)
ACCENT   = (88, 138, 255,  255)
ACCENT_H = (115, 165, 255,  255)
ACCENT_A = (62, 108, 230,  255)
TEXT     = (225, 232, 245,  255)
MUTED    = (120, 135, 165,  255)
BORDER   = (34,  42,  60,  255)
GREEN    = (68,  195, 110,  255)
GOLD     = (220, 178,  68,  255)
RED_B    = (195,  58,  58,  255)
RED_H    = (225,  80,  80,  255)

# ══════════════════════════════════════════════════════════════════════════════
#  App state
# ══════════════════════════════════════════════════════════════════════════════
state = {
    "url":              "",
    "gt":               "",
    "providers":        {},
    "selected_prov":    "",
    "base_files":       [],
    "optional_files":   [],
    "selective_files":  [],
    "safe_title":       "",
    "dest":             "",
    "cancel_requested": False,
    "pause_event":      threading.Event(),
    "start_time":       None,
    "total_files":      0,
    "avg_file_size":    500 * 1024 * 1024,
    "bytes_downloaded": 0,
    "last_pct":         0.0,
}
state["pause_event"].set()

# ══════════════════════════════════════════════════════════════════════════════
#  Utility & History
# ══════════════════════════════════════════════════════════════════════════════
def _sz(b):
    if b >= 1 << 30: return f"{b/(1<<30):.2f} GB"
    if b >= 1 << 20: return f"{b/(1<<20):.1f} MB"
    if b >= 1 << 10: return f"{b/(1<<10):.1f} KB"
    return f"{b:.0f} B"

def _spd(bps):
    if bps >= 1 << 20: return f"{bps/(1<<20):.1f} MB/s"
    if bps >= 1 << 10: return f"{bps/(1<<10):.1f} KB/s"
    return f"{bps:.0f} B/s"

def _t(s):
    if s <= 0: return "--"
    if s < 60:   return f"{int(s)}s"
    if s < 3600: return f"{int(s//60)}m {int(s%60):02d}s"
    return f"{int(s//3600)}h {int((s%3600)//60):02d}m"

def trunc(txt, n=56):
    return txt if len(txt) <= n else txt[:n-1] + "..."

SCREENS = ("s_setup", "s_search", "s_select", "s_progress")
def show(name):
    for s in SCREENS:
        dpg.configure_item(s, show=(s == name))

def sv(tag, val):   dpg.set_value(tag, val)
def sc(tag, **kw):  dpg.configure_item(tag, **kw)

def load_history():
    if not os.path.exists(HISTORY_FILE): return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            h = json.load(f)
        for url, data in h.items():
            if data["status"] not in ("Deleted", "Completed") and not os.path.exists(data["dest"]):
                data["status"] = "Deleted"
        return h
    except: return {}

def save_history(h):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(h, f)
    except: pass

def update_history(status, pct):
    if not state["url"]: return
    h = load_history()
    h[state["url"]] = {
        "title": state["gt"],
        "safe_title": state["safe_title"],
        "dest": state["dest"],
        "status": status,
        "pct": pct
    }
    save_history(h)

def _load_hist(url, dest):
    sv("url_in", url)
    if dest: sv("dir_in", dest)
    cb_fetch(None, None)

def refresh_history():
    dpg.delete_item("hist_list", children_only=True)
    h = load_history()
    if not h:
        dpg.add_text("No history yet.", parent="hist_list", color=list(MUTED))
        return
    
    for url, data in reversed(list(h.items())):
        with dpg.group(horizontal=True, parent="hist_list"):
            dpg.add_button(label="Load", callback=lambda s,a,ud: _load_hist(ud[0], ud[1]), user_data=(url, data.get("dest", "")))
            st = data['status']
            c = GREEN if st == "Completed" else (RED_B if st in ("Deleted", "Error") else GOLD)
            dpg.add_text(f"[{st}] {data.get('pct', 0):.1f}%", color=list(c))
            dpg.add_text(trunc(data['title'], 40))

# ══════════════════════════════════════════════════════════════════════════════
#  Callbacks
# ══════════════════════════════════════════════════════════════════════════════
def cb_minimize():
    hw = ctypes.windll.user32.FindWindowW(None, "FG Downloader")
    if hw: ctypes.windll.user32.ShowWindow(hw, 6)

def cb_close():
    state["cancel_requested"] = True
    dpg.stop_dearpygui()

def cb_fetch(s, a):
    inp = dpg.get_value("url_in").strip()
    if not inp:
        sv("st_status", "Enter a URL or Game Name")
        sc("st_status", color=list(GOLD))
        return

    sc("btn_fetch", label=" Fetching...", enabled=False)
    sc("st_status", color=list(MUTED))

    if inp.startswith("http"):
        sv("st_status", "Connecting...")
        threading.Thread(target=_fetch, args=(inp,), daemon=True).start()
    else:
        sv("st_status", "Searching FitGirl...")
        threading.Thread(target=_search, args=(inp,), daemon=True).start()

def _search(query):
    try:
        results = downloader.search_game(query)
        if not results:
            sv("st_status", "No games found.")
            sc("st_status", color=list(RED_B))
            sc("btn_fetch", label="  Fetch  ", enabled=True)
            return

        if len(results) == 1:
            _fetch(results[0]["url"])
            return

        # Multiple results
        dpg.delete_item("search_list", children_only=True)
        for r in results:
            dpg.add_button(label=trunc(r["title"], 75), callback=lambda s,a,u: _fetch_wrap(u), user_data=r["url"], parent="search_list")
        
        show("s_search")
        sc("btn_fetch", label="  Fetch  ", enabled=True)
        sv("st_status", "")
    except Exception as e:
        sv("st_status", str(e)[:62])
        sc("st_status", color=list(RED_B))
        sc("btn_fetch", label="  Fetch  ", enabled=True)

def _fetch_wrap(url):
    show("s_setup")
    sv("url_in", url)
    cb_fetch(None, None)

def _fetch(url):
    try:
        state["url"] = url
        gt, safe, providers = downloader.fetch_links(url)
        state.update({"safe_title": safe, "gt": gt, "providers": providers})

        # Setup providers dropdown
        avail = [p for p, links in providers.items() if links]
        if not avail:
            raise ValueError("No supported links found on page.")
        
        sc("prov_combo", items=avail)
        sv("prov_combo", avail[0])
        _on_prov_change(None, avail[0])

        sv("sel_title",  trunc(gt, 60))
        show("s_select")
    except Exception as e:
        sv("st_status", str(e)[:62])
        sc("st_status", color=list(RED_B))
        sc("btn_fetch", label="  Fetch  ", enabled=True)

def _on_prov_change(s, a):
    prov = dpg.get_value("prov_combo")
    state["selected_prov"] = prov
    links = state["providers"][prov]
    
    base, opts, sels = downloader.group_files(links)
    state.update({"base_files": base, "optional_files": opts, "selective_files": sels})

    size_str = _sz(len(base) * state["avg_file_size"])
    sv("base_count", f"{len(base)} Base files ~{size_str} (Must be downloaded)")

    dpg.delete_item("sel_list", children_only=True)
    if sels:
        sc("sel_block", show=True)
        for i, o in enumerate(sels):
            dpg.add_checkbox(label=f"{o['filename']}", tag=f"sc_{i}", default_value=True, parent="sel_list")
    else: sc("sel_block", show=False)

    dpg.delete_item("opt_list", children_only=True)
    if opts:
        sc("opt_block", show=True)
        for i, o in enumerate(opts):
            dpg.add_checkbox(label=f"{o['filename']}", tag=f"oc_{i}", default_value=False, parent="opt_list")
    else: sc("opt_block", show=False)


def cb_browse(s, a):
    r = tkinter.Tk(); r.withdraw(); r.attributes('-topmost', True)
    p = filedialog.askdirectory(title="Select Download Directory")
    r.destroy()
    if p: sv("dir_in", os.path.normpath(p))

def cb_back_setup(s, a):
    sc("btn_fetch", label="  Fetch  ", enabled=True)
    sv("st_status", "")
    refresh_history()
    show("s_setup")

def cb_start(s, a):
    opts = [state["optional_files"][i] for i in range(len(state["optional_files"])) if dpg.does_item_exist(f"oc_{i}") and dpg.get_value(f"oc_{i}")]
    sels = [state["selective_files"][i] for i in range(len(state["selective_files"])) if dpg.does_item_exist(f"sc_{i}") and dpg.get_value(f"sc_{i}")]
    
    if len(state["selective_files"]) > 0 and len(sels) == 0: return

    queue = state["base_files"] + sels + opts
    if not queue: return

    parent = dpg.get_value("dir_in").strip() or os.getcwd()
    if os.path.basename(parent) == state["safe_title"]: dest = parent
    else: dest = os.path.join(parent, state["safe_title"])
    os.makedirs(dest, exist_ok=True)
    state["dest"] = dest

    state.update(cancel_requested=False, start_time=time.perf_counter(),
                 total_files=len(queue), bytes_downloaded=0, last_pct=0.0)
    state["pause_event"].set()

    sv("pr_fname",   "Preparing...")
    sv("pr_part",    f"0 / {len(queue)}")
    sv("pr_pct",     "0%")
    sv("pr_sz",      "-- / --")
    sv("pr_spd",     "--")
    sv("pr_eta",     "Calculating...")
    sv("pr_el",      "0s")
    sv("pr_file_b",  0.0)
    sv("pr_all_b",   0.0)
    sv("lbl_all_prog", "OVERALL PROGRESS - 0.0%")
    
    sc("btn_cancel", label="Cancel", enabled=True)
    sc("btn_pause", label="Pause", enabled=True)
    dpg.delete_item("log_list", children_only=True)

    update_history("Downloading", 0.0)
    show("s_progress")
    threading.Thread(target=_download, args=(queue, dest, state["selected_prov"]), daemon=True).start()

def cb_cancel(s, a):
    state["cancel_requested"] = True
    state["pause_event"].set()
    sv("pr_fname", "Cancelling...")
    sc("btn_cancel", enabled=False, label="Cancelling...")
    sc("btn_pause", enabled=False)
    update_history("Cancelled", state["last_pct"] * 100.0)

def cb_pause(s, a):
    if state["pause_event"].is_set():
        state["pause_event"].clear()
        sc("btn_pause", label="Resume")
        sv("pr_spd", "paused")
        update_history("Paused", state["last_pct"] * 100.0)
    else:
        state["pause_event"].set()
        sc("btn_pause", label="Pause")
        update_history("Downloading", state["last_pct"] * 100.0)

def cb_back_sel(s, a):
    state["cancel_requested"] = True
    state["pause_event"].set()
    update_history("Cancelled", state["last_pct"] * 100.0)
    show("s_select")

# ══════════════════════════════════════════════════════════════════════════════
#  Download thread
# ══════════════════════════════════════════════════════════════════════════════
def _download(queue, dest, provider):
    total = state["total_files"]
    for i, item in enumerate(queue):
        if state["cancel_requested"]: break

        fname = item["filename"]
        out   = os.path.join(dest, fname)

        sv("pr_fname",  trunc(fname, 65))
        sv("pr_part",   f"{i+1} / {total}")
        sv("pr_file_b", 0.0)
        sv("pr_pct",    "0%")
        sv("pr_sz",     "0 B / --")
        sv("pr_spd",    f"resolving {provider}...")

        def cb(done, tsz, spd, ela, _i=i):
            pct  = done/tsz if tsz else 0.0
            all_ = (_i+pct)/state["total_files"]
            state["last_pct"] = all_
            tnow = time.perf_counter()-state["start_time"]
            
            files_left = total - _i - pct
            avg_sz = tsz if tsz > 0 else state["avg_file_size"]
            bytes_left = files_left * avg_sz
            overall_eta = bytes_left / spd if spd > 0 else 0.0

            sv("pr_file_b", pct);    sv("pr_all_b",  all_)
            sv("pr_pct",  f"{pct*100:.1f}%")
            sv("lbl_all_prog", f"OVERALL PROGRESS - {all_*100:.1f}%")
            sv("pr_sz",   f"{_sz(done)} / {_sz(tsz)}")
            sv("pr_spd",  _spd(spd));  sv("pr_eta",  _t(overall_eta))
            sv("pr_el",   _t(tnow));   sv("pr_part", f"{_i+1} / {total}")

        ok, msg = downloader.download_file(
            item["url"], provider, out, progress_cb=cb,
            cancel_check=lambda: state["cancel_requested"],
            pause_event=state["pause_event"])

        if ok:
            sv("pr_file_b", 1.0); sv("pr_pct", "100%")
            ico   = "[skip]" if msg == "already_exists" else "[ok]"
            color = list(MUTED) if msg == "already_exists" else list(GREEN)
            dpg.add_text(f"  {ico}  {trunc(fname, 60)}", parent="log_list", color=color)
        else:
            dpg.add_text(f"  [fail] {trunc(fname,50)}  -  {msg[:22]}",
                         parent="log_list", color=list(RED_B))
            if not state["cancel_requested"]:
                update_history("Error", state["last_pct"] * 100.0)
        dpg.set_y_scroll("log_win", dpg.get_y_scroll_max("log_win"))

    tt = time.perf_counter()-state["start_time"]
    sv("pr_el", _t(tt));  sv("pr_spd", "--");  sv("pr_eta", "done")
    sc("btn_cancel", enabled=False)
    sc("btn_pause", enabled=False)
    if not state["cancel_requested"]:
        sv("pr_all_b",  1.0)
        sv("lbl_all_prog", "OVERALL PROGRESS - 100.0%")
        sv("pr_fname",  f"[*] All {total} files complete!")
        sv("pr_part",   f"{total} / {total}")
        update_history("Completed", 100.0)
    else:
        sv("pr_fname", "[-] Cancelled")

# ══════════════════════════════════════════════════════════════════════════════
#  Theme
# ══════════════════════════════════════════════════════════════════════════════
def build_theme():
    T = {}

    with dpg.theme() as base:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,            BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,             CARD)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,             FRAME)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,      FRAME_HV)
            dpg.add_theme_color(dpg.mvThemeCol_Button,              ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,       ACCENT_H)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,        ACCENT_A)
            dpg.add_theme_color(dpg.mvThemeCol_Text,                TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,        MUTED)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,         BG)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,       BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered,FRAME_HV)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,           ACCENT_H)
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,       ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,             CARD)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,       CARD)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,      0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,       4)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,       4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,       12, 12)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,        6, 4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,         6, 6)
    dpg.bind_theme(base)

    with dpg.theme() as danger:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        RED_B)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, RED_H)
    T["danger"] = danger

    with dpg.theme() as muted_btn:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        FRAME)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, FRAME_HV)
            dpg.add_theme_color(dpg.mvThemeCol_Text,          TEXT)
    T["muted"] = muted_btn

    with dpg.theme() as circle_btn:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (0,0,0,0))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, FRAME_HV)
            dpg.add_theme_color(dpg.mvThemeCol_Text,          TEXT)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
    T["circle"] = circle_btn

    return T

# ══════════════════════════════════════════════════════════════════════════════
#  UI Layout
# ══════════════════════════════════════════════════════════════════════════════
def build_ui():
    with dpg.window(tag="root", width=W, height=H, no_collapse=True, no_close=False, on_close=cb_close, label="FG Downloader", menubar=True):
        
        with dpg.menu_bar():
            dpg.add_spacer(width=4)
            dpg.add_text("FG Downloader", color=list(ACCENT))
            dpg.add_spacer(width=W - 200)
            dpg.add_button(label="-", width=24, height=24, callback=cb_minimize, tag="btn_tb_min")
            dpg.add_button(label="X", width=24, height=24, callback=cb_close, tag="btn_tb_close")

        # ╭─────────────────────────────────────────────────────╮
        # │  SCREEN 1 - Setup                                   │
        # ╰─────────────────────────────────────────────────────╯
        with dpg.group(tag="s_setup", show=True):
            dpg.add_spacer(height=10)
            dpg.add_text("FitGirl URL or Game Name", color=list(MUTED), tag="lbl_url")
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="url_in", width=-100, hint="Type your game name or paste URL")
                dpg.add_button(label="Fetch", tag="btn_fetch", width=90, callback=cb_fetch)
            dpg.add_text("", tag="st_status", color=list(MUTED))

            dpg.add_spacer(height=30)
            dpg.add_text("RECENT DOWNLOADS", color=list(MUTED))
            with dpg.child_window(tag="hist_win", height=200, border=True, width=-1):
                with dpg.group(tag="hist_list"): pass

        # ╭─────────────────────────────────────────────────────╮
        # │  SCREEN 1B - Search Results                         │
        # ╰─────────────────────────────────────────────────────╯
        with dpg.group(tag="s_search", show=False):
            dpg.add_spacer(height=10)
            dpg.add_text("Multiple matches found. Select one:", color=list(ACCENT))
            with dpg.child_window(tag="search_win", height=300, border=True, width=-1):
                with dpg.group(tag="search_list"): pass
            dpg.add_spacer(height=8)
            dpg.add_button(label="Back", tag="btn_bk_search", width=60, callback=cb_back_setup)

        # ╭─────────────────────────────────────────────────────╮
        # │  SCREEN 2 - File Selection                          │
        # ╰─────────────────────────────────────────────────────╯
        with dpg.group(tag="s_select", show=False):
            dpg.add_text("", tag="sel_title", color=list(ACCENT))
            
            with dpg.group(horizontal=True):
                dpg.add_text("Provider:", color=list(MUTED))
                dpg.add_combo(tag="prov_combo", width=150, callback=_on_prov_change)

            dpg.add_text("", tag="base_count", color=list(TEXT))

            # Selective
            with dpg.group(tag="sel_block", show=False):
                dpg.add_spacer(height=6)
                dpg.add_text("Selective Files (Choose at least one voice/language)", color=list(MUTED))
                with dpg.child_window(tag="sel_win", height=80, border=True, width=-1):
                    with dpg.group(tag="sel_list"): pass

            # Optional
            with dpg.group(tag="opt_block", show=False):
                dpg.add_spacer(height=6)
                dpg.add_text("Optional Files", color=list(MUTED))
                with dpg.child_window(tag="opt_win", height=80, border=True, width=-1):
                    with dpg.group(tag="opt_list"): pass

            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="dir_in", width=-80, hint="Download directory (blank = current)")
                dpg.add_button(label="Browse", tag="btn_browse", width=70, callback=cb_browse)

            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Back", tag="btn_bk_s", width=60, callback=cb_back_setup)
                dpg.add_button(label="Start Download", tag="btn_start", width=-1, callback=cb_start)

        # ╭─────────────────────────────────────────────────────╮
        # │  SCREEN 3 - Download Progress                       │
        # ╰─────────────────────────────────────────────────────╯
        with dpg.group(tag="s_progress", show=False):
            
            with dpg.group(horizontal=True):
                dpg.add_text("FILE:", color=list(MUTED))
                dpg.add_text("", tag="pr_fname", color=list(TEXT))
            
            with dpg.group(horizontal=True):
                dpg.add_text("PART:", color=list(MUTED))
                dpg.add_text("", tag="pr_part", color=list(ACCENT))

            with dpg.group(horizontal=True):
                dpg.add_progress_bar(tag="pr_file_b", default_value=0.0, width=-50, height=14)
                dpg.add_text("0%", tag="pr_pct", color=list(ACCENT))

            dpg.add_text("", tag="pr_sz", color=list(MUTED))
            
            with dpg.group(horizontal=True):
                dpg.add_text("SPEED:", color=list(MUTED))
                dpg.add_text("", tag="pr_spd", color=list(ACCENT))
                dpg.add_spacer(width=10)
                dpg.add_text("OVERALL ETA:", color=list(MUTED))
                dpg.add_text("", tag="pr_eta", color=list(GOLD))
                dpg.add_spacer(width=10)
                dpg.add_text("ELAPSED:", color=list(MUTED))
                dpg.add_text("", tag="pr_el", color=list(MUTED))

            dpg.add_spacer(height=4)
            dpg.add_text("OVERALL PROGRESS - 0.0%", tag="lbl_all_prog", color=list(MUTED))
            dpg.add_progress_bar(tag="pr_all_b", default_value=0.0, width=-1, height=8)

            dpg.add_spacer(height=6)
            with dpg.child_window(tag="log_win", height=100, border=False, width=-1):
                with dpg.group(tag="log_list"): pass

            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Back", tag="btn_bk_p", width=60, callback=cb_back_sel)
                dpg.add_button(label="Pause", tag="btn_pause", width=60, callback=cb_pause)
                dpg.add_button(label="Cancel", tag="btn_cancel", width=-1, callback=cb_cancel)

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def resource_path(relative_path):
    import sys
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def main():
    dpg.create_context()

    with dpg.texture_registry():
        dpg.add_static_texture(width=1, height=1, default_value=[0,0,0,0], tag="tex_thumb_id")
        dpg.add_alias("tex_thumb", "tex_thumb_id")
        try:
            w, h, c, d = dpg.load_image(resource_path("favicon.jpg"))
            dpg.add_static_texture(width=w, height=h, default_value=d, tag="tex_favicon")
        except: pass

    themes = build_theme()
    build_ui()
    refresh_history()

    # Apply minimal theme buttons
    dpg.bind_item_theme("btn_bk_s",   themes["muted"])
    dpg.bind_item_theme("btn_bk_p",   themes["muted"])
    dpg.bind_item_theme("btn_bk_search", themes["muted"])
    dpg.bind_item_theme("btn_browse", themes["muted"])
    dpg.bind_item_theme("btn_cancel", themes["danger"])
    dpg.bind_item_theme("btn_tb_min", themes["circle"])
    dpg.bind_item_theme("btn_tb_close", themes["circle"])

    with dpg.handler_registry():
        dpg.add_mouse_drag_handler(button=0, callback=lambda s,a: dpg.set_viewport_pos([
            dpg.get_viewport_pos()[0] + a[1], dpg.get_viewport_pos()[1] + a[2]
        ]) if dpg.get_mouse_pos()[1] < 20 else None)

    dpg.create_viewport(
        title="FG Downloader",
        width=W, height=H,
        decorated=False,
        clear_color=BG,
        small_icon=resource_path("favicon.ico"),
        large_icon=resource_path("favicon.ico")
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("root", True)
    dpg.start_dearpygui()
    dpg.destroy_context()

if __name__ == "__main__":
    main()
