# gui.py
# Originally developed by Ekey
# Converted to Python and GUI built by mwakeman1, 4/28/2025

import os
import sys
import pathlib
import threading
import queue
import time
from typing import Optional, List, Tuple

import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox

try:
    import imgui_bundle
    from imgui_bundle import imgui, immapp, ImVec2, ImVec4
    from imgui_bundle import imspinner
except ImportError as e:
    try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Dependency Error", f"imgui-bundle not found or incomplete:\n{e}\n\nPlease install using:\npip install imgui-bundle")
        root.destroy()
    except Exception: pass
    sys.exit(1)

try:
    from functions import DatHashList, DatUnpack
except ImportError:
    try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Import Error", "Could not import core logic from functions.py.\nEnsure functions.py is in the same directory.")
        root.destroy()
    except Exception: pass
    sys.exit(1)

g_archive_path: Optional[str] = None
g_output_path: Optional[str] = None
g_status_message: str = "Initializing..."
g_is_unpacking: bool = False
g_unpacking_thread: Optional[threading.Thread] = None
g_hash_list_thread: Optional[threading.Thread] = None
g_first_frame_completed = False
g_unpacked_files_queue = queue.Queue()
g_unpacked_files_list: List[str] = []
g_unpack_started = False

def load_hash_list_thread_entrypoint():
    global g_status_message
    try:
        DatHashList.set_loading_status(True)
        DatHashList.iLoadProject()
        if DatHashList._list_load_success:
            if not DatHashList.m_HashList: g_status_message = "Hash list loaded (empty). Select archive and output folder."
            else: g_status_message = f"Hash list loaded ({len(DatHashList.m_HashList)} hashes). Select archive and output folder."
        else: g_status_message = "Failed to load hash list. Unpacking may proceed without names."
    except Exception as e:
        g_status_message = f"Critical error loading hash list: {type(e).__name__}"
        DatHashList._list_load_success = False
        DatHashList.set_loading_status(False)

def run_unpacking_thread(archive_path: str, output_path: str, output_queue: queue.Queue):
    global g_status_message, g_is_unpacking, g_unpack_started
    try:
        if not DatHashList._list_loaded:
            g_status_message = "Cannot unpack: Hash list loading not finished."
            g_is_unpacking = False; return
        g_status_message = "Processing..."
        g_unpack_started = True
        DatUnpack.iDoIt(archive_path, output_path, output_queue)
        g_status_message = "Unpacking process finished."
    except Exception as e:
        g_status_message = f"Error during unpacking: {type(e).__name__}"
        output_queue.put(f"THREAD ERROR: {e}")
    finally: g_is_unpacking = False

def gui_loop():
    global g_archive_path, g_output_path, g_status_message, g_is_unpacking
    global g_unpacking_thread, g_hash_list_thread, g_first_frame_completed
    global g_unpacked_files_list, g_unpacked_files_queue, g_unpack_started

    if not g_first_frame_completed:
        g_first_frame_completed = True
        if g_hash_list_thread is None:
            g_status_message = "Loading hash list..."
            g_hash_list_thread = threading.Thread(target=load_hash_list_thread_entrypoint, daemon=True)
            g_hash_list_thread.start()

    while not g_unpacked_files_queue.empty():
        try:
            item = g_unpacked_files_queue.get_nowait()
            g_unpacked_files_list.append(str(item))
        except queue.Empty: break
        except Exception: pass

    is_loading_hashes, hash_loading_progress = DatHashList.get_loading_status()
    disable_ui = is_loading_hashes or g_is_unpacking
    content_region = imgui.get_content_region_avail()

    imgui.text("Input Archive (.dat):")
    imgui.same_line(max(150, content_region.x * 0.25))
    if disable_ui: imgui.begin_disabled()
    if imgui.button("Select Archive..."):
        archive_path_selected = None
        try:
            root_tk = tk.Tk(); root_tk.withdraw(); root_tk.attributes("-topmost", True)
            archive_path_selected = filedialog.askopenfilename(title="Select Archive File", filetypes=[("DAT files", "*.dat"), ("All files", "*.*")])
            root_tk.destroy()
        except Exception as tk_e: g_status_message = f"Dialog Error: {tk_e}"
        else:
            if archive_path_selected:
                g_archive_path = str(pathlib.Path(archive_path_selected).resolve())
                if not disable_ui: g_status_message = "Archive selected."
    if disable_ui: imgui.end_disabled()
    imgui.text("Selected:"); imgui.same_line()
    imgui.text_wrapped(g_archive_path if g_archive_path else "None")

    imgui.separator()
    imgui.text("Output Folder:")
    imgui.same_line(max(150, content_region.x * 0.25))
    if disable_ui: imgui.begin_disabled()
    if imgui.button("Select Output Folder..."):
        output_path_selected = None
        try:
            root_tk = tk.Tk(); root_tk.withdraw(); root_tk.attributes("-topmost", True)
            output_path_selected = filedialog.askdirectory(title="Select Output Folder")
            root_tk.destroy()
        except Exception as tk_e: g_status_message = f"Dialog Error: {tk_e}"
        else:
            if output_path_selected:
                g_output_path = str(pathlib.Path(output_path_selected).resolve())
                if not disable_ui: g_status_message = "Output folder selected."
    if disable_ui: imgui.end_disabled()
    imgui.text("Selected:"); imgui.same_line()
    imgui.text_wrapped(g_output_path if g_output_path else "None")

    imgui.separator()
    can_unpack = (
        g_archive_path is not None and
        g_output_path is not None and
        not g_is_unpacking and
        DatHashList._list_loaded and not is_loading_hashes
    )
    if not can_unpack: imgui.begin_disabled()
    button_pressed = imgui.button("Unpack Archive", size=ImVec2(content_region.x, 0))
    if not can_unpack: imgui.end_disabled()

    if button_pressed and can_unpack:
        g_is_unpacking = True
        g_status_message = "Starting unpacking..."
        g_unpacked_files_list.clear()
        g_unpack_started = False
        while not g_unpacked_files_queue.empty():
            try: g_unpacked_files_queue.get_nowait()
            except queue.Empty: break
        g_unpacking_thread = threading.Thread(target=run_unpacking_thread, args=(str(g_archive_path), str(g_output_path), g_unpacked_files_queue), daemon=True)
        g_unpacking_thread.start()

    imgui.separator()
    if not is_loading_hashes:
        imgui.text("Status:")
        imgui.same_line()
        imgui.text_wrapped(g_status_message)
        if g_is_unpacking:
            imgui.same_line()
            try:
                time_secs = imgui.get_time()
                spinner_radius = imgui.get_font_size() / 2.5
                spinner_thickness = spinner_radius / 4.0
                imspinner.spinner_dots("##unpacking_spinner", nextdot=(time_secs * 8.0), radius=spinner_radius, thickness=spinner_thickness)
            except AttributeError: imgui.text("...")
            except Exception as spin_e: imgui.text(f"(Spinner Error: {type(spin_e).__name__})")

    if not is_loading_hashes and g_unpack_started:
        imgui.separator()
        imgui.text("Unpack Log:")
        log_height = imgui.get_content_region_avail().y - 10
        imgui.begin_child("##unpack_log_child", size=ImVec2(-1, max(50, log_height)), child_flags=1)
        for file_path in g_unpacked_files_list:
            imgui.indent(5)
            imgui.text_unformatted(file_path)
            imgui.unindent(5)
        if imgui.get_scroll_y() >= imgui.get_scroll_max_y():
            imgui.set_scroll_here_y(1.0)
        imgui.end_child()

    if is_loading_hashes:
        io = imgui.get_io()
        window_size = io.display_size
        draw_list = imgui.get_background_draw_list()
        window_pos = imgui.get_main_viewport().pos
        overlay_min = (window_pos.x, window_pos.y)
        overlay_max = (window_pos.x + window_size.x, window_pos.y + window_size.y)
        overlay_color = imgui.color_convert_float4_to_u32(ImVec4(0.0, 0.0, 0.0, 0.65))
        draw_list.add_rect_filled(overlay_min, overlay_max, overlay_color)
        center_x = window_pos.x + window_size.x * 0.5
        center_y = window_pos.y + window_size.y * 0.5
        text_loading = "Loading Hash List... Please wait"
        text_size = imgui.calc_text_size(text_loading)
        text_y_pos = center_y - text_size.y - 10
        imgui.set_cursor_screen_pos(ImVec2(center_x - text_size.x * 0.5, text_y_pos))
        imgui.text_colored(ImVec4(1.0, 1.0, 1.0, 1.0), text_loading)
        progress_bar_width = min(300, window_size.x * 0.6)
        progress_bar_height = 20
        progress_y_pos = text_y_pos + text_size.y + 10
        imgui.set_cursor_screen_pos(ImVec2(center_x - progress_bar_width * 0.5, progress_y_pos))
        overlay_text = f"{int(hash_loading_progress * 100)}%"
        imgui.progress_bar(hash_loading_progress, ImVec2(progress_bar_width, progress_bar_height), overlay_text)
