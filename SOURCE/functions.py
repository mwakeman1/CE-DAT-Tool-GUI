#functions.py
# Originally developed by Ekey
# Converted to Python and GUI built by mwakeman1, 4/28/2025

import os
import struct
import sys
import pathlib
import io
import encodings
import threading
import traceback
import time
import queue
from typing import Optional, Dict, List, Tuple

try:
    from filenames import filename_list as imported_filename_list
    if not isinstance(imported_filename_list, list):
        imported_filename_list = None
    elif not imported_filename_list:
        pass
except ImportError:
    imported_filename_list = None
except NameError:
    imported_filename_list = None
except Exception as e:
    imported_filename_list = None

class DatEntry:
    def __init__(self, dwHash: int = 0, dwOffset: int = 0, dwSize: int = 0):
        self.dwHash: int = dwHash
        self.dwOffset: int = dwOffset
        self.dwSize: int = dwSize

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
                     output_queue.put(relative_path_os)
                     DatHelpers.ReadWriteFile(m_Archive, m_FullPath, m_Entry.dwOffset, m_Entry.dwSize)
                     processed_count += 1
                except Exception as extract_err:
                     output_queue.put(f"ERROR extracting {relative_path_os}: {extract_err}")
                     pass
        except Exception as e: output_queue.put(f"FATAL ERROR during unpack: {e}")
