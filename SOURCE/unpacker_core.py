# Combined DAT Unpacker Core Logic and GUI with File Type Detection
# Based on original C# snippets, QuickBMS script, and troubleshooting.
# Version 1.7: Modified file type detection to EXACTLY match QuickBMS script logic.

import os
import struct
import sys
import pathlib
import io
import encodings # To get access to ASCII, Unicode etc.
import threading
import traceback
from typing import Optional, Dict, List, Tuple

# --- Tkinter Imports for File Dialog ---
import tkinter as tk
from tkinter import filedialog

# --- ImGui Bundle Imports (Core + Spinner) ---
try:
    import imgui_bundle
    from imgui_bundle import imgui, immapp, ImVec2
    from imgui_bundle import imspinner # Import the spinner module
except ImportError as e:
    print(f"DEBUG: Caught ImportError: {e}", file=sys.stderr)
    print("Error: imgui-bundle core components might be missing or not installed.", file=sys.stderr)
    print("Please ensure it's installed using: pip install imgui-bundle", file=sys.stderr)
    try:
        root = tk.Tk(); root.withdraw()
        from tkinter import messagebox
        messagebox.showerror("Dependency Error", f"imgui-bundle not found or incomplete:\n{e}\n\nPlease install using:\npip install imgui-bundle")
        root.destroy()
    except Exception: pass
    sys.exit(1)

# ==============================================
# --- CORE UNPACKER LOGIC ---
# ==============================================

# --- DatEntry.cs ---
class DatEntry:
    def __init__(self, dwHash: int = 0, dwOffset: int = 0, dwSize: int = 0):
        self.dwHash: int = dwHash
        self.dwOffset: int = dwOffset
        self.dwSize: int = dwSize

# --- Utils.cs ---
class Utils:
    @staticmethod
    def iGetApplicationPath() -> str:
        return str(pathlib.Path(__file__).parent.resolve())

    @staticmethod
    def iGetApplicationVersion() -> str:
        return "1.0.0.0 (Python Placeholder)"

    @staticmethod
    def iSetInfo(m_String: str):
        print(m_String)

    @staticmethod
    def iSetError(m_String: str):
        print(f"ERROR: {m_String}!", file=sys.stderr)

    @staticmethod
    def iSetWarning(m_String: str):
        print(f"WARNING: {m_String}!", file=sys.stderr)

    @staticmethod
    def iCheckArgumentsPath(m_Arg: str) -> str:
        if m_Arg and not m_Arg.endswith(os.path.sep):
            return m_Arg + os.path.sep
        return m_Arg

    @staticmethod
    def iCreateDirectory(m_Directory: str):
        dir_name = os.path.dirname(m_Directory)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

# --- Helpers.cs (Stream Extensions) ---
class Helpers:
    @staticmethod
    def read_bytes(stream: io.BufferedIOBase, count: int) -> bytes:
        if count < 0: raise IOError("Count cannot be negative.")
        if count == 0: return b''
        data = stream.read(count)
        if len(data) != count: raise EOFError(f"Stream ended. Expected {count}, got {len(data)}.")
        return data
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

    # Corrected read_string method
    @staticmethod
    def read_string(stream: io.BufferedIOBase, length: int = -1, encoding: str = 'ascii', trim: bool = True) -> str:
        if length != -1:
            result_bytes = Helpers.read_bytes(stream, length)
            result = result_bytes.decode(encoding)
        else:
            data = bytearray()
            while True: # Start of loop
                b = stream.read(1) # Read one byte INSIDE the loop
                if not b: raise EOFError("EOF reading null-terminated string.") # Check for EOF INSIDE the loop
                if b == b'\x00': break # Check for null terminator INSIDE the loop
                data.extend(b) # If it's a valid byte, append it INSIDE the loop
            result = data.decode(encoding) # After the loop, decode the result
        return result.strip() if trim else result # Trim the final result if needed

    @staticmethod
    def read_string_by_offset(stream: io.BufferedIOBase, offset: int, encoding: str = 'ascii', trim: bool = True) -> str:
        original_pos = stream.tell(); stream.seek(offset)
        try: result = Helpers.read_string(stream, length=-1, encoding=encoding, trim=trim)
        finally: stream.seek(original_pos)
        return result
    @staticmethod
    def read_string_list(stream: io.BufferedIOBase, encoding: str = 'ascii', trim: bool = True) -> list[str]:
        result = []; start_pos = stream.tell(); stream_size = stream.seek(0, io.SEEK_END); stream.seek(start_pos)
        while stream.tell() < stream_size:
             try: result.append(Helpers.read_string(stream, length=-1, encoding=encoding, trim=trim))
             except EOFError: break
        return result

    # Corrected copy_to method
    @staticmethod
    def copy_to(source: io.BufferedIOBase, target: io.BufferedIOBase):
        buffer_size = 32768
        while True: # Start of loop
            buffer = source.read(buffer_size)
            if not buffer: break # Exit the loop if EOF is reached
            target.write(buffer) # If the buffer is NOT empty, write it
        # Loop finishes when break is hit

# --- ByteArrayExtensions.cs ---
class ByteArrayExtensions:
    # Note: is_text is no longer used by detect_file_type_and_name but kept for potential future use
    @staticmethod
    def read_bytes(data: bytes, count: int, start_index: int = 0) -> bytes:
        if start_index + count > len(data): raise IndexError("Read beyond bounds"); return data[start_index : start_index + count]
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
            sample_text = data[:limit].decode('ascii', errors='replace').strip()
            if sample_text.startswith('#') or any(kw in sample_text for kw in ['v ', 'vt ', 'vn ', 'f ', 'mtllib', 'usemtl']): return True
            return True
        except Exception: return False

# --- DatHash.cs ---
class DatHash:
    @staticmethod
    def iGetHash(m_String: str) -> int:
        UINT32_MAX = 0xFFFFFFFF; dw_hash = 1; j = 0; b_counter = 1; dw_blocks = 8 * len(m_String)
        if dw_blocks > 0:
            try: string_bytes = m_String.encode('latin-1')
            except UnicodeEncodeError: Utils.iSetError(f"Hash encode error: {m_String}"); return 0
            for _ in range(dw_blocks):
                a=(dw_hash & 0x200000)!=0; b=(dw_hash & 2)!=0; c=(dw_hash & 1)!=0; d=(dw_hash & 0x80000000)!=0
                dw_hash = (dw_hash << 1) & UINT32_MAX
                try: x = (string_bytes[j] & b_counter)!=0
                except IndexError: Utils.iSetError(f"Hash index error: {j} for '{m_String}'"); x = False
                if d ^ (a ^ b ^ c ^ x): dw_hash = (dw_hash | 1) & UINT32_MAX
                b_counter *= 2
                if b_counter > 255: j += 1; b_counter = 1
                if j >= len(string_bytes) and _ < dw_blocks - 1: Utils.iSetWarning(f"Hash truncated: '{m_String}'"); break
        return dw_hash

# --- DatHashList.cs ---
class DatHashList:
    m_ScriptPath = Utils.iGetApplicationPath()
    m_ProjectFile = "FileNames.list"
    m_ProjectFilePath = os.path.join(m_ScriptPath, m_ProjectFile)
    _project_file_found = os.path.exists(m_ProjectFilePath)
    m_HashList: Dict[int, str] = {}

    @staticmethod
    def iLoadProject():
        if not DatHashList._project_file_found:
             Utils.iSetWarning(f"Hash list not found: {DatHashList.m_ProjectFilePath}. Proceeding without known names.")
             return
        Utils.iSetInfo(f"Attempting to load hash list: {DatHashList.m_ProjectFilePath}")
        i = 0; DatHashList.m_HashList.clear()
        try:
            encoding_to_use = None; Utils.iSetInfo("Detecting hash list encoding...")
            for enc in ['utf-8', 'latin-1']:
                try:
                    Utils.iSetInfo(f"  Trying encoding: {enc}")
                    with open(DatHashList.m_ProjectFilePath, 'r', encoding=enc) as test_file: test_file.read()
                    encoding_to_use = enc; Utils.iSetInfo(f"  Successfully detected encoding: {enc}"); break
                except UnicodeDecodeError: Utils.iSetInfo(f"  Encoding {enc} failed."); continue
                except Exception as e_inner: Utils.iSetWarning(f"Error checking encoding {enc}: {e_inner}"); continue
            if not encoding_to_use: Utils.iSetWarning(f"Could not detect encoding for {DatHashList.m_ProjectFile}, using system default."); encoding_to_use = None
            Utils.iSetInfo(f"Reading hash list content using encoding: {encoding_to_use or 'system default'}")
            with open(DatHashList.m_ProjectFilePath, 'r', encoding=encoding_to_use) as TProjectFile:
                for line_num, m_Line in enumerate(TProjectFile):
                    m_Line_Stripped = m_Line.strip();
                    if not m_Line_Stripped: continue
                    dwHashLower = DatHash.iGetHash(m_Line_Stripped.lower()); dwHashUpper = DatHash.iGetHash(m_Line_Stripped.upper())
                    if dwHashLower in DatHashList.m_HashList and DatHashList.m_HashList[dwHashLower] != m_Line_Stripped: print(f"[COLLISION]: L{line_num+1} {DatHashList.m_HashList[dwHashLower]} <-> {m_Line_Stripped} ({dwHashLower:08X})")
                    DatHashList.m_HashList[dwHashLower] = m_Line_Stripped
                    if dwHashUpper != dwHashLower:
                         if dwHashUpper in DatHashList.m_HashList and DatHashList.m_HashList[dwHashUpper] != m_Line_Stripped: print(f"[COLLISION]: L{line_num+1} {DatHashList.m_HashList[dwHashUpper]} <-> {m_Line_Stripped} ({dwHashUpper:08X})")
                         DatHashList.m_HashList[dwHashUpper] = m_Line_Stripped
                    i += 1
            Utils.iSetInfo(f"[INFO]: Hash List Loaded: {i} entries."); print()
        except FileNotFoundError: Utils.iSetWarning(f"Hash list disappeared during load: {DatHashList.m_ProjectFilePath}")
        except Exception as e: Utils.iSetError(f"Failed processing {DatHashList.m_ProjectFile}: {e}"); traceback.print_exc()

    @staticmethod
    def iGetNameFromHashList(dwHash: int) -> Optional[str]:
        return DatHashList.m_HashList.get(dwHash)

# --- DatHelpers.cs ---
class DatHelpers:
    @staticmethod
    def ReadWriteFile(m_ArchiveFile: str, m_FullPath: str, dwOffset: int, dwSize: int):
        MAX_BUFFER = 524288; dwBytesLeft = dwSize
        if not os.path.exists(m_ArchiveFile): Utils.iSetError(f"Archive not found: {m_ArchiveFile}"); return
        try:
            Utils.iCreateDirectory(m_FullPath)
            with open(m_FullPath, 'wb') as TDstStream, open(m_ArchiveFile, 'rb') as TArchiveStream:
                TArchiveStream.seek(dwOffset)
                if dwSize <= 0: return
                while dwBytesLeft > 0:
                    read_size = min(dwBytesLeft, MAX_BUFFER); lpBuffer = Helpers.read_bytes(TArchiveStream, read_size); TDstStream.write(lpBuffer); dwBytesLeft -= read_size
        except Exception as e: Utils.iSetError(f"Error writing {m_FullPath}: {e}")

# --- DatUnpack.cs (MODIFIED to match QuickBMS extension logic) ---
class DatUnpack:
    m_EntryTable: List[DatEntry] = []

    @staticmethod
    def detect_file_type_and_name(archive_path: str, entry: DatEntry) -> Tuple[str, str]:
        """
        Detects file type based *only* on magic number, matching QuickBMS.
        Returns tuple: (relative_path_with_extension, detected_extension)
        """
        base_name_known = DatHashList.iGetNameFromHashList(entry.dwHash)
        # ** FIX: Default extension changed to .txt **
        detected_ext = ".txt"
        magic_int = None

        # Try reading magic number (first 4 bytes)
        if entry.dwSize >= 4:
            try:
                with open(archive_path, 'rb') as f: f.seek(entry.dwOffset); header_bytes = Helpers.read_bytes(f, 4)
                magic_int = struct.unpack('<I', header_bytes)[0]
            except Exception: pass # Ignore errors reading magic number

        # Check known magic numbers from QuickBMS script
        if magic_int is not None:
            if magic_int == 1196314761: detected_ext = ".png"    # 0x474E5089 PNG
            elif magic_int == 542327876: detected_ext = ".dds"    # 0x20534444 DDS
            elif magic_int == 1245859653: detected_ext = ".obj"    # 0x4A4F4205 QuickBMS calls this obj
            elif magic_int == 2: detected_ext = ".fmt_02" # 0x00000002 Use slightly more descriptive name

        # ** FIX: Removed the text heuristic check to match QuickBMS **
        # (No check for text obj if magic number doesn't match)

        # Construct final relative path
        if base_name_known:
            # Use known name, remove any existing extension, add detected one
            name_part = os.path.splitext(base_name_known)[0]
            relative_path = name_part + detected_ext
        else:
            # Unknown hash, use __Unknown\HASHVALUE.ext format
            relative_path = os.path.join("__Unknown", f"{entry.dwHash:08X}{detected_ext}")

        return relative_path, detected_ext


    @staticmethod
    def iDoIt(m_Archive: str, m_DstFolder: str):
        try:
            m_DstFolder = Utils.iCheckArgumentsPath(m_DstFolder); DatHashList.iLoadProject()
            DatUnpack.m_EntryTable.clear()
            try: # Read index
                with open(m_Archive, 'rb') as TDatStream:
                    while True:
                        entry_data = TDatStream.read(12);
                        if len(entry_data) < 12: break
                        dwHash, dwOffset, dwSize = struct.unpack('<IIi', entry_data)
                        if dwHash == 0: break
                        if dwSize < 0: Utils.iSetWarning(f"Skipping entry hash {dwHash:08X}, negative size ({dwSize})"); continue
                        DatUnpack.m_EntryTable.append(DatEntry(dwHash, dwOffset, dwSize))
            except Exception as read_err: Utils.iSetError(f"Failed reading index: {read_err}"); return

            total_entries = len(DatUnpack.m_EntryTable); Utils.iSetInfo(f"Read {total_entries} entries.")
            if total_entries == 0: Utils.iSetWarning("No file entries found."); return

            # Process entries
            processed_count = 0
            for index, m_Entry in enumerate(DatUnpack.m_EntryTable):
                # ** Use the modified detection logic **
                relative_path, _ = DatUnpack.detect_file_type_and_name(m_Archive, m_Entry)
                m_FullPath = os.path.join(m_DstFolder, relative_path); m_FullPath = os.path.normpath(m_FullPath)
                Utils.iSetInfo(f"[UNPACKING {index + 1}/{total_entries}]: {relative_path}") # Log name with new extension
                DatHelpers.ReadWriteFile(m_Archive, m_FullPath, m_Entry.dwOffset, m_Entry.dwSize)
                processed_count += 1
            Utils.iSetInfo(f"[INFO]: Unpacking completed. Processed {processed_count} files.")
        except FileNotFoundError: Utils.iSetError(f"Archive file not found: {m_Archive}")
        except Exception as e: Utils.iSetError(f"Unexpected error during unpacking: {e}"); traceback.print_exc()

# ==============================================
# --- GUI CODE ---
# ==============================================

# --- Global state for the UI ---
g_archive_path: Optional[str] = None; g_output_path: Optional[str] = None
g_status_message: str = "Idle. Select archive and output folder."; g_is_unpacking: bool = False
g_unpacking_thread: Optional[threading.Thread] = None

# --- Unpacking Function (to run in a thread) ---
def run_unpacking_thread(archive_path: str, output_path: str):
    """Wrapper to run DatUnpack.iDoIt and update GUI status"""
    global g_status_message, g_is_unpacking
    try:
        g_status_message = "Processing... (See console for details)"
        Utils.iSetInfo(f"Starting unpack: {archive_path} -> {output_path}")
        DatUnpack.iDoIt(archive_path, output_path) # Calls the modified version
        g_status_message = "Unpacking completed! Check output folder and console log."
        Utils.iSetInfo(g_status_message)
    except Exception as e:
        g_status_message = f"Error during unpacking: {type(e).__name__}\nSee console for details."
        print(f"--- ERROR IN UNPACKING THREAD ---", file=sys.stderr); traceback.print_exc()
        print(f"--- END ERROR ---", file=sys.stderr)
    finally: g_is_unpacking = False

# --- Main GUI Loop Function ---
def gui_loop():
    """Runs every frame to draw the GUI"""
    global g_archive_path, g_output_path, g_status_message, g_is_unpacking, g_unpacking_thread
    content_region = imgui.get_content_region_avail()

    # == File Selection ==
    imgui.text("Input Archive (.dat):"); imgui.same_line(max(150, content_region.x * 0.25))
    if imgui.button("Select Archive...") and not g_is_unpacking:
        archive_path_selected = None
        try:
            root_tk = tk.Tk(); root_tk.withdraw(); root_tk.attributes("-topmost", True)
            archive_path_selected = filedialog.askopenfilename(title="Select Archive File", filetypes=[("DAT files", "*.dat"), ("All files", "*.*")])
            root_tk.destroy()
        except Exception as tk_e: g_status_message = f"Dialog Error: {tk_e}"
        else:
            if archive_path_selected: g_archive_path = str(pathlib.Path(archive_path_selected).resolve()); g_status_message = "Archive selected."
    imgui.text("Selected:"); imgui.same_line(); display_archive_path = g_archive_path if g_archive_path else "None"
    imgui.text_wrapped(display_archive_path)

    # == Folder Selection ==
    imgui.separator(); imgui.text("Output Folder:"); imgui.same_line(max(150, content_region.x * 0.25))
    if imgui.button("Select Output Folder...") and not g_is_unpacking:
        output_path_selected = None
        try:
            root_tk = tk.Tk(); root_tk.withdraw(); root_tk.attributes("-topmost", True)
            output_path_selected = filedialog.askdirectory(title="Select Output Folder")
            root_tk.destroy()
        except Exception as tk_e: g_status_message = f"Dialog Error: {tk_e}"
        else:
            if output_path_selected: g_output_path = str(pathlib.Path(output_path_selected).resolve()); g_status_message = "Output folder selected."
    imgui.text("Selected:"); imgui.same_line(); display_output_path = g_output_path if g_output_path else "None"
    imgui.text_wrapped(display_output_path)

    # == Unpack Button ==
    imgui.separator(); can_unpack = g_archive_path is not None and g_output_path is not None and not g_is_unpacking
    if not can_unpack: imgui.begin_disabled()
    button_pressed = imgui.button("Unpack Archive", size=ImVec2(content_region.x, 0))
    if not can_unpack: imgui.end_disabled()
    if button_pressed and can_unpack:
        g_is_unpacking = True; g_status_message = "Starting unpacking..."
        g_unpacking_thread = threading.Thread(target=run_unpacking_thread, args=(str(g_archive_path), str(g_output_path)), daemon=True); g_unpacking_thread.start()

    # == Status Display ==
    imgui.separator(); imgui.text("Status:")
    if g_is_unpacking:
         imgui.same_line()
         try: # Use spinner_dots
             imspinner.spinner_dots("##unpacking_spinner", radius=6.0, thickness=1.5)
         except AttributeError: imgui.text("...") # Fallback
         except Exception as spin_e: imgui.text(f"(Spinner Error: {spin_e})")
    imgui.text_wrapped(g_status_message)

# --- Application Entry Point ---
def main():
    """Sets up and runs the ImGui application"""
    try: immapp.run(gui_function=gui_loop, window_title="DAT Unpacker (v1.7 - BMS Logic)", window_size=[700, 300]) # Updated title
    except Exception as e:
        print(f"\n--- GUI CRASH ---", file=sys.stderr); print(f"Error: {e}", file=sys.stderr); traceback.print_exc(); print(f"--- END GUI CRASH ---", file=sys.stderr)
        try: root = tk.Tk(); root.withdraw(); from tkinter import messagebox; messagebox.showerror("GUI Error", f"Critical error:\n{e}\n\nSee console output."); root.destroy()
        except Exception: pass

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__)); os.chdir(script_dir)
    print(f"Running from directory: {script_dir}")
    main()