# main.py
# Originally developed by Ekey
# Converted to Python and GUI built by mwakeman1, 4/28/2025

import os
import sys
import ctypes 
import tkinter as tk 
from tkinter import messagebox

try:
    import imgui_bundle
    from imgui_bundle import imgui, immapp
except ImportError as e:
    try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Dependency Error", f"imgui-bundle not found or incomplete:\n{e}\n\nPlease install using:\npip install imgui-bundle")
        root.destroy()
    except Exception: pass
    sys.exit(1)

try:
    from gui import gui_loop
except ImportError:
     try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Import Error", "Could not import GUI logic from gui.py.\nEnsure gui.py is in the same directory.")
        root.destroy()
     except Exception: pass
     sys.exit(1)

def main():

    try:
        immapp.run(gui_function=gui_loop, window_title="CE DAT Unpacker", window_size=[700, 500])

    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("GUI Error", f"Critical error:\n{e}\n\nApplication will exit.")
            root.destroy()
        except Exception: pass


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not getattr(sys, 'frozen', False):
         try:
              os.chdir(script_dir)
         except Exception:
              pass 

    if os.name == 'nt' and not getattr(sys, 'frozen', False):
        try:
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0) 
        except Exception:
            pass 

    main()
