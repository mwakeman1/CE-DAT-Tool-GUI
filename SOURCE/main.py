# Combined DAT Unpacker Core Logic and GUI with File Type Detection
# Version 2.4.5: Added unpack log display within the GUI.
#                GUI opens instantly, hash processing starts after first frame.
#                Integrated loading overlay/blur, removed ALL terminal output.
#                UI elements disabled during hash list loading.
# Fix: Corrected begin_child call to use flags for border instead of keyword.
# Fix: Corrected ChildFlags import and usage.
# Fix: Corrected ChildFlags attribute access (removed trailing underscore).
# Fix: Corrected access to border flag constant (imgui.CHILD_FLAGS_BORDER).
# Fix: Attempting access via imgui.ChildFlags_.border based on previous error.
# Fix: Using integer flag 1 for border in begin_child.

import os
import struct
import sys
import pathlib
import io
import encodings
import threading
import traceback
import time
import queue # Added for thread-safe communication
from typing import Optional, Dict, List, Tuple

# --- Tkinter Imports for File Dialog ---
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox # Explicit import for potential error popups

# --- ImGui Bundle Imports (Core + Spinner) ---
try:
    # Attempt to import necessary imgui components
    import imgui_bundle
    # Import specific enums/classes needed
    # ChildFlags is accessed via imgui submodule
    from imgui_bundle import imgui, immapp, ImVec2, ImVec4
    from imgui_bundle import imspinner # Import the spinner module
except ImportError as e:
    # Handle missing imgui-bundle with a messagebox
    try:
        # Initialize Tkinter temporarily for the messagebox
        root = tk.Tk()
        root.withdraw() # Hide the main Tkinter window
        messagebox.showerror("Dependency Error", f"imgui-bundle not found or incomplete:\n{e}\n\nPlease install using:\npip install imgui-bundle")
        root.destroy() # Clean up Tkinter
    except Exception:
        pass # Ignore errors during error reporting itself
    sys.exit(1) # Exit the application

# --- Filenames Import ---
# Attempt to import the filename list from filenames.py silently
try:
    from filenames import filename_list as imported_filename_list
    # Validate that the imported object is actually a list
    if not isinstance(imported_filename_list, list):
        imported_filename_list = None # Mark as failed if not a list
    elif not imported_filename_list:
        pass # Allow an empty list, it's not an error state
except ImportError:
    imported_filename_list = None # Mark as failed if file not found
except NameError:
     imported_filename_list = None # Mark as failed if list variable not found
except Exception as e:
    # Handle unexpected errors during import with a messagebox
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("File Import Error", f"Failed during import from 'filenames.py':\n{e}")
        root.destroy()
    except Exception:
        pass
    imported_filename_list = None # Mark as failed

# ==============================================
# --- CORE UNPACKER LOGIC --- (Unchanged)
# ==============================================

# --- DatEntry Class ---
class DatEntry:
    def __init__(self, dwHash: int = 0, dwOffset: int = 0, dwSize: int = 0):
        self.dwHash: int = dwHash
        self.dwOffset: int = dwOffset
        self.dwSize: int = dwSize

# --- Utils Class (MODIFIED TO SUPPRESS OUTPUT) ---
class Utils:
    @staticmethod
    def iGetApplicationPath() -> str: return str(pathlib.Path(__file__).parent.resolve())
    @staticmethod
    def iGetApplicationVersion() -> str: return "1.0.0.0 (Python Placeholder)"
    @staticmethod
    def iSetInfo(m_String: str): pass
    @staticmethod
    def iSetError(m_String: str): pass
    @staticmethod
    def iSetWarning(m_String: str): pass
    @staticmethod
    def iCheckArgumentsPath(m_Arg: str) -> str:
        if m_Arg and not m_Arg.endswith(os.path.sep): return m_Arg + os.path.sep
        return m_Arg
    @staticmethod
    def iCreateDirectory(m_Directory: str):
        dir_name = os.path.dirname(m_Directory)
        try:
             if dir_name: os.makedirs(dir_name, exist_ok=True)
        except Exception: pass

# --- Helpers Class (Stream Extensions) ---
class Helpers:
    @staticmethod
    def read_bytes(stream: io.BufferedIOBase, count: int) -> bytes:
        if count < 0: raise IOError("Count cannot be negative.");
        if count == 0: return b''
        chunks = []
        bytes_read = 0
        while bytes_read < count:
            chunk = stream.read(count - bytes_read)
            if not chunk: raise EOFError(f"Stream ended unexpectedly. Expected {count} bytes, got {bytes_read}.")
            chunks.append(chunk)
            bytes_read += len(chunk)
        return b"".join(chunks)
    @staticmethod
    def read_int16(stream: io.BufferedIOBase) -> int: return struct.unpack('<h', Helpers.read_bytes(stream, 2))[0]
    @staticmethod
    def read_int32(stream: io.BufferedIOBase) -> int: return struct.unpack('<i', Helpers.read_bytes(stream, 4))[0]
    @staticmethod
    def read_int64(stream: io.BufferedIOBase) -> int: return struct.unpack('<q', Helpers.read_bytes(stream, 8))[0]
    @staticmethod
    def read_uint16(stream: io.BufferedIOBase) -> int: return struct.unpack('<H', Helpers.read_bytes(stream, 2))[0]
    @staticmethod
    def read_uint32(stream: io.BufferedIOBase) -> int: return struct.unpack('<I', Helpers.read_bytes(stream, 4))[0]
    @staticmethod
    def read_uint64(stream: io.BufferedIOBase) -> int: return struct.unpack('<Q', Helpers.read_bytes(stream, 8))[0]
    @staticmethod
    def read_single(stream: io.BufferedIOBase) -> float: return struct.unpack('<f', Helpers.read_bytes(stream, 4))[0]
    @staticmethod
    def read_string_unicode_length(stream: io.BufferedIOBase, length: int) -> str: return Helpers.read_bytes(stream, length * 2).decode('utf-16le')
    @staticmethod
    def read_string_length(stream: io.BufferedIOBase) -> str: length = Helpers.read_int32(stream); return Helpers.read_bytes(stream, length).decode('ascii')
    @staticmethod
    def read_string(stream: io.BufferedIOBase, length: int = -1, encoding: str = 'ascii', trim: bool = True) -> str:
        if length != -1: result = Helpers.read_bytes(stream, length).decode(encoding)
        else:
            data = bytearray()
            while True:
                b = stream.read(1)
                if not b: raise EOFError("EOF reading null-terminated string.")
                if b == b'\x00': break
                data.extend(b)
            result = data.decode(encoding)
        return result.strip() if trim else result
    @staticmethod
    def read_string_by_offset(stream: io.BufferedIOBase, offset: int, encoding: str = 'ascii', trim: bool = True) -> str:
        original_pos = stream.tell(); stream.seek(offset)
        try: result = Helpers.read_string(stream, length=-1, encoding=encoding, trim=trim)
        finally: stream.seek(original_pos)
        return result
    @staticmethod
    def read_string_list(stream: io.BufferedIOBase, encoding: str = 'ascii', trim: bool = True) -> list[str]:
        result = []; start_pos = stream.tell(); stream.seek(0, io.SEEK_END); stream_size = stream.tell(); stream.seek(start_pos)
        while stream.tell() < stream_size:
            try: result.append(Helpers.read_string(stream, length=-1, encoding=encoding, trim=trim))
            except EOFError: break
        return result
    @staticmethod
    def copy_to(source: io.BufferedIOBase, target: io.BufferedIOBase):
        buffer_size = 32768
        while True:
            buffer = source.read(buffer_size)
            if not buffer: break
            target.write(buffer)

# --- ByteArrayExtensions Class ---
class ByteArrayExtensions:
    @staticmethod
    def read_bytes(data: bytes, count: int, start_index: int = 0) -> bytes:
        if start_index + count > len(data): raise IndexError("Read beyond bounds")
        return data[start_index : start_index + count]
    @staticmethod
    def read_int16(data: bytes, start_index: int = 0) -> int: return struct.unpack('<h', data[start_index : start_index + 2])[0]
    @staticmethod
    def read_int32(data: bytes, start_index: int = 0) -> int: return struct.unpack('<i', data[start_index : start_index + 4])[0]
    @staticmethod
    def read_uint16(data: bytes, start_index: int = 0) -> int: return struct.unpack('<H', data[start_index : start_index + 2])[0]
    @staticmethod
    def read_uint32(data: bytes, start_index: int = 0) -> int: return struct.unpack('<I', data[start_index : start_index + 4])[0]
    @staticmethod
    def read_uint64(data: bytes, start_index: int = 0) -> int: return struct.unpack('<Q', data[start_index : start_index + 8])[0]
    @staticmethod
    def read_single(data: bytes, start_index: int = 0) -> float: return struct.unpack('<f', data[start_index : start_index + 4])[0]
    @staticmethod
    def read_single_be(data: bytes, start_index: int = 0) -> float: return struct.unpack('>f', data[start_index : start_index + 4])[0]
    @staticmethod
    def _read_string_internal(data: bytes, start_index: int, encoding: str, trim: bool) -> tuple[str, int]:
        try: null_pos = data.index(b'\x00', start_index); result = data[start_index:null_pos].decode(encoding); next_index = null_pos + 1
        except ValueError: result = data[start_index:].decode(encoding); next_index = len(data)
        return result.strip() if trim else result, next_index
    @staticmethod
    def read_string(data: bytes, start_index: int = 0, encoding: str = 'ascii', trim: bool = True) -> str:
        result, _ = ByteArrayExtensions._read_string_internal(data, start_index, encoding, trim); return result
    @staticmethod
    def read_string_list(data: bytes, start_index: int = 0, encoding: str = 'ascii', trim: bool = True) -> list[str]:
        result = []; current_index = start_index
        while current_index < len(data):
            s, next_index = ByteArrayExtensions._read_string_internal(data, current_index, encoding, trim); result.append(s); current_index = next_index
        return result
    @staticmethod
    def is_text(data: bytes) -> bool:
        limit = min(len(data), 100);
        if limit == 0: return True
        has_binary = any(not (b == 0 or b == 9 or b == 10 or b == 13 or 32 <= b <= 126) for b in data[:limit])
        if has_binary: return False
        try:
            sample_text = data[:limit].decode('ascii', errors='ignore').strip()
            if sample_text.startswith('#') or any(kw in sample_text for kw in ['v ', 'vt ', 'vn ', 'f ', 'mtllib', 'usemtl']): return True
            return True
        except Exception: return False

# --- DatHash Class (Suppressed internal Utils calls) ---
class DatHash:
    @staticmethod
    def iGetHash(m_String: str) -> int:
        UINT32_MAX = 0xFFFFFFFF; dw_hash = 1; j = 0; b_counter = 1; dw_blocks = 8 * len(m_String)
        if dw_blocks > 0:
            try: string_bytes = m_String.encode('latin-1')
            except UnicodeEncodeError: return 0
            for _ in range(dw_blocks):
                d = (dw_hash & 0x80000000) != 0; a = (dw_hash & 0x200000) != 0; b = (dw_hash & 2) != 0; c = (dw_hash & 1) != 0
                dw_hash = (dw_hash << 1) & UINT32_MAX
                try: x = (string_bytes[j] & b_counter) != 0
                except IndexError: x = False
                if d ^ (a ^ b ^ c ^ x): dw_hash = (dw_hash | 1) & UINT32_MAX
                b_counter *= 2
                if b_counter > 255: j += 1; b_counter = 1
                if j >= len(string_bytes) and _ < dw_blocks - 1: break
        return dw_hash

# --- DatHashList Class (Handles loading and lookup of filename hashes) ---
class DatHashList:
    m_HashList: Dict[int, str] = {}
    _list_loaded = False
    _list_load_success = False
    g_is_loading_hashes = False
    g_hash_list_loading_progress = 0.0
    g_hash_list_lock = threading.Lock()
    @staticmethod
    def update_load_progress(processed: int, total: int):
        with DatHashList.g_hash_list_lock:
            if total > 0: DatHashList.g_hash_list_loading_progress = float(processed) / total
            else: DatHashList.g_hash_list_loading_progress = 0.0
    @staticmethod
    def set_loading_status(loading: bool):
        with DatHashList.g_hash_list_lock: DatHashList.g_is_loading_hashes = loading
    @staticmethod
    def get_loading_status() -> Tuple[bool, float]:
         with DatHashList.g_hash_list_lock: return DatHashList.g_is_loading_hashes, DatHashList.g_hash_list_loading_progress
    @staticmethod
    def iLoadProject():
        if DatHashList._list_loaded: return
        DatHashList.update_load_progress(0, 1)
        DatHashList.m_HashList.clear()
        i = 0; processed_count = 0; total_count = 0; load_error = False
        if imported_filename_list is None: load_error = True
        elif not imported_filename_list: load_error = False; total_count = 0
        else:
            total_count = len(imported_filename_list)
            update_interval = max(1, total_count // 200)
            for line_num, m_Line_Stripped in enumerate(imported_filename_list):
                if not isinstance(m_Line_Stripped, str) or not m_Line_Stripped: continue
                dwHashLower = DatHash.iGetHash(m_Line_Stripped.lower())
                dwHashUpper = DatHash.iGetHash(m_Line_Stripped.upper())
                DatHashList.m_HashList[dwHashLower] = m_Line_Stripped
                if dwHashUpper != dwHashLower: DatHashList.m_HashList[dwHashUpper] = m_Line_Stripped
                i += 1
                processed_count = line_num + 1
                if processed_count % update_interval == 0 or processed_count == total_count:
                    DatHashList.update_load_progress(processed_count, total_count)
        if not load_error and i > 0: DatHashList._list_load_success = True
        elif not load_error and i == 0: DatHashList._list_load_success = True
        else: DatHashList._list_load_success = False
        DatHashList._list_loaded = True
        DatHashList.update_load_progress(total_count, total_count)
        DatHashList.set_loading_status(False)
    @staticmethod
    def iGetNameFromHashList(dwHash: int) -> Optional[str]:
        if not DatHashList._list_loaded or not DatHashList._list_load_success: return None
        return DatHashList.m_HashList.get(dwHash)

# --- DatHelpers Class (File I/O operations, Suppressed Utils calls) ---
class DatHelpers:
    @staticmethod
    def ReadWriteFile(m_ArchiveFile: str, m_FullPath: str, dwOffset: int, dwSize: int):
        MAX_BUFFER = 524288; dwBytesLeft = dwSize
        if not os.path.exists(m_ArchiveFile): return
        try:
            Utils.iCreateDirectory(m_FullPath)
            with open(m_FullPath, 'wb') as TDstStream, open(m_ArchiveFile, 'rb') as TArchiveStream:
                TArchiveStream.seek(dwOffset)
                if dwSize <= 0: return
                while dwBytesLeft > 0:
                    read_size = min(dwBytesLeft, MAX_BUFFER); lpBuffer = Helpers.read_bytes(TArchiveStream, read_size); TDstStream.write(lpBuffer); dwBytesLeft -= read_size
        except Exception as e: pass

# --- DatUnpack Class (Core unpacking logic, MODIFIED to use Queue) ---
class DatUnpack:
    m_EntryTable: List[DatEntry] = []

    @staticmethod
    def detect_file_type_and_name(archive_path: str, entry: DatEntry) -> Tuple[str, str]:
        base_name_known = DatHashList.iGetNameFromHashList(entry.dwHash)
        detected_ext = ".bin"; magic_int = None
        if entry.dwSize >= 4:
            try:
                with open(archive_path, 'rb') as f: f.seek(entry.dwOffset); header_bytes = Helpers.read_bytes(f, 4)
                magic_int = struct.unpack('<I', header_bytes)[0]
            except (IOError, EOFError, struct.error, OSError): pass
            except Exception: pass
        if magic_int is not None:
            if magic_int == 0x474E5089: detected_ext = ".png"
            elif magic_int == 0x20534444: detected_ext = ".dds"
            elif magic_int == 0x4A4D4F45: detected_ext = ".obj"
            elif magic_int == 0x00000002: detected_ext = ".fmt_02"
        if base_name_known: name_part = os.path.splitext(base_name_known)[0]; relative_path = name_part + detected_ext
        else: relative_path = os.path.join("__Unknown", f"{entry.dwHash:08X}{detected_ext}")
        relative_path = relative_path.replace('/', os.path.sep).replace('\\', os.path.sep)
        return relative_path, detected_ext

    @staticmethod
    def iDoIt(m_Archive: str, m_DstFolder: str, output_queue: queue.Queue):
        """Performs the main unpacking process, putting extracted paths onto the queue."""
        try:
            if not DatHashList._list_loaded:
                output_queue.put("ERROR: Hash list not loaded.")
                return
            m_DstFolder = Utils.iCheckArgumentsPath(m_DstFolder)
            DatUnpack.m_EntryTable.clear();
            try:
                with open(m_Archive, 'rb') as TDatStream:
                    while True:
                        entry_data = TDatStream.read(12)
                        if len(entry_data) < 12: break
                        dwHash, dwOffset, dwSize = struct.unpack('<IIi', entry_data)
                        if dwHash == 0 and dwOffset == 0 and dwSize == 0: break
                        if dwSize < 0: continue
                        DatUnpack.m_EntryTable.append(DatEntry(dwHash, dwOffset, dwSize))
            except FileNotFoundError: output_queue.put(f"ERROR: Archive not found: {m_Archive}"); return
            except Exception as read_err: output_queue.put(f"ERROR: Failed reading index: {read_err}"); return
            total_entries = len(DatUnpack.m_EntryTable)
            if total_entries == 0: output_queue.put("WARNING: No file entries found in the archive."); return
            processed_count = 0
            try:
                os.makedirs(m_DstFolder, exist_ok=True)
                if not DatHashList._list_load_success or not DatHashList.m_HashList:
                     os.makedirs(os.path.join(m_DstFolder, "__Unknown"), exist_ok=True)
            except Exception: pass
            for index, m_Entry in enumerate(DatUnpack.m_EntryTable):
                try:
                     relative_path, _ = DatUnpack.detect_file_type_and_name(m_Archive, m_Entry)
                     relative_path_os = relative_path.replace('/', os.path.sep).replace('\\', os.path.sep)
                     m_FullPath = os.path.join(m_DstFolder, relative_path_os)
                     m_FullPath = os.path.normpath(m_FullPath)
                     output_queue.put(relative_path_os) # Put path on queue
                     DatHelpers.ReadWriteFile(m_Archive, m_FullPath, m_Entry.dwOffset, m_Entry.dwSize)
                     processed_count += 1
                except Exception as extract_err:
                     output_queue.put(f"ERROR extracting {relative_path_os}: {extract_err}")
                     pass
        except Exception as e: output_queue.put(f"FATAL ERROR during unpack: {e}")

# ==============================================
# --- GUI CODE ---
# ==============================================

# --- Global UI State Variables ---
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

# --- Hash List Loading Thread Entry Point ---
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

# --- Unpacking Thread Entry Point ---
def run_unpacking_thread(archive_path: str, output_path: str, output_queue: queue.Queue):
    """Function executed by the unpacking thread."""
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

# --- Main GUI Loop Function ---
def gui_loop():
    """Runs every frame to draw the ImGui interface."""
    global g_archive_path, g_output_path, g_status_message, g_is_unpacking
    global g_unpacking_thread, g_hash_list_thread, g_first_frame_completed
    global g_unpacked_files_list, g_unpacked_files_queue, g_unpack_started

    # --- Start Hash Loading Thread After First Frame ---
    if not g_first_frame_completed:
        g_first_frame_completed = True
        if g_hash_list_thread is None:
             g_status_message = "Loading hash list..."
             g_hash_list_thread = threading.Thread(target=load_hash_list_thread_entrypoint, daemon=True)
             g_hash_list_thread.start()
    # --- End Thread Start Logic ---

    # --- Process Unpacking Queue ---
    while not g_unpacked_files_queue.empty():
        try:
            item = g_unpacked_files_queue.get_nowait()
            g_unpacked_files_list.append(str(item))
        except queue.Empty: break
        except Exception: pass

    # --- Get Current State ---
    is_loading_hashes, hash_loading_progress = DatHashList.get_loading_status()
    disable_ui = is_loading_hashes or g_is_unpacking
    content_region = imgui.get_content_region_avail()

    # ==================================
    # == Main UI Controls ==
    # ==================================

    # --- Input Archive Selection ---
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

    # --- Output Folder Selection ---
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

    # --- Unpack Button ---
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

    # ==================================
    # == Status Display Area ==
    # ==================================
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

    # ==================================
    # == Unpack Log Area ==
    # ==================================
    if not is_loading_hashes and g_unpack_started:
        imgui.separator()
        imgui.text("Unpack Log:")
        log_height = imgui.get_content_region_avail().y - 5
        # *** FIXED LINE BELOW *** Use integer flag 1 for border
        imgui.begin_child("##unpack_log_child", size=ImVec2(-1, max(50, log_height)), child_flags=1) # Use 1 for border
        for file_path in g_unpacked_files_list:
            imgui.text_unformatted(file_path)
        if imgui.get_scroll_y() >= imgui.get_scroll_max_y():
             imgui.set_scroll_here_y(1.0)
        imgui.end_child()


    # ==================================
    # == Loading Overlay ==
    # ==================================
    if is_loading_hashes:
        # --- Draw Background Overlay FIRST ---
        io = imgui.get_io()
        window_size = io.display_size
        draw_list = imgui.get_background_draw_list()
        window_pos = imgui.get_main_viewport().pos
        overlay_min = (window_pos.x, window_pos.y)
        overlay_max = (window_pos.x + window_size.x, window_pos.y + window_size.y)
        overlay_color = imgui.color_convert_float4_to_u32(ImVec4(0.0, 0.0, 0.0, 0.60))
        draw_list.add_rect_filled(overlay_min, overlay_max, overlay_color)

        # --- Draw Foreground Elements (Text and Progress Bar) ---
        center_x = window_pos.x + window_size.x * 0.5
        center_y = window_pos.y + window_size.y * 0.5

        # Draw Loading Text
        text_loading = "Loading Hash List... Please wait"
        text_size = imgui.calc_text_size(text_loading)
        text_y_pos = center_y - text_size.y - 10
        imgui.set_cursor_screen_pos(ImVec2(center_x - text_size.x * 0.5, text_y_pos))
        imgui.text_colored(ImVec4(1.0, 1.0, 1.0, 1.0), text_loading)

        # Draw Progress Bar
        progress_bar_width = min(300, window_size.x * 0.6)
        progress_bar_height = 20
        progress_y_pos = text_y_pos + text_size.y + 10
        imgui.set_cursor_screen_pos(ImVec2(center_x - progress_bar_width * 0.5, progress_y_pos))
        overlay_text = f"{int(hash_loading_progress * 100)}%"
        imgui.progress_bar(hash_loading_progress, ImVec2(progress_bar_width, progress_bar_height), overlay_text)


# --- Application Entry Point --- (Unchanged)
def main():
    """Sets up and runs the ImGui application."""
    try:
        immapp.run(gui_function=gui_loop, window_title="DAT Unpacker (v2.4.5 - GUI Log)", window_size=[700, 500])
    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("GUI Error", f"Critical error:\n{e}\n\nApplication will exit.")
            root.destroy()
        except Exception: pass
    finally: pass


if __name__ == "__main__":
    # --- Setup --- (Unchanged)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not getattr(sys, 'frozen', False):
         try: os.chdir(script_dir)
         except Exception: pass

    # --- Optional: Hide Console Window (Windows Only) --- (Unchanged)
    if os.name == 'nt' and not getattr(sys, 'frozen', False):
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception: pass

    # --- Run Main Application --- (Unchanged)
    main()
