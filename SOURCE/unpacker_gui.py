import os
import sys
import threading
import traceback
from typing import Optional
import pathlib # Added for path normalization

# --- Tkinter Imports for File Dialog ---
import tkinter as tk
from tkinter import filedialog

# --- ImGui Bundle Imports (excluding ImFileDialog) ---
# Use imgui_bundle instead of raw imgui for convenience
try:
    import imgui_bundle
    from imgui_bundle import imgui, immapp, ImVec2
    # Removed: from imgui_bundle.im_file_dialog import ImFileDialog
except ImportError as e:
    # Keep the check, in case the rest of imgui-bundle is missing
    print(f"DEBUG: Caught ImportError: {e}", file=sys.stderr) # Keep debug print
    print("Error: imgui-bundle core components might be missing or not installed.", file=sys.stderr)
    print("Please ensure it's installed using: pip install imgui-bundle", file=sys.stderr)
    sys.exit(1)

# --- Import the Core Unpacker Logic ---
# Assume the previous code is saved as unpacker_core.py
try:
    # Find the directory where this GUI script lives
    gui_script_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to unpacker_core.py in the same directory
    core_script_path = os.path.join(gui_script_dir, "unpacker_core.py")

    # Check if core script exists before trying to import
    if not os.path.exists(core_script_path):
         raise ImportError(f"Cannot find 'unpacker_core.py' in the script directory: {gui_script_dir}")

    from unpacker_core import (
        Utils,
        DatHashList,
        DatUnpack
        # Import other classes if needed directly, but usually only these are needed
    )
except ImportError as e:
    print(f"Import Error: {e}", file=sys.stderr)
    print("Please ensure 'unpacker_core.py' contains the core logic and is", file=sys.stderr)
    print("in the same directory as this GUI script.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error importing core logic: {e}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)

# --- Global state for the UI ---
g_archive_path: Optional[str] = None
g_output_path: Optional[str] = None
g_status_message: str = "Idle. Select archive and output folder."
g_is_unpacking: bool = False
g_unpacking_thread: Optional[threading.Thread] = None

# --- Unpacking Function (to run in a thread) ---
def run_unpacking_thread(archive_path: str, output_path: str):
    global g_status_message, g_is_unpacking
    try:
        # Update status for UI
        g_status_message = "Loading hash list..."
        # Ensure the core logic knows where to find FileNames.list
        # Make 'Projects' folder relative to the core script location
        # Note: unpacker_core.__file__ might not be reliable if it's imported
        # Instead, use the directory of the GUI script as reference point
        gui_script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.join(gui_script_dir, "Projects") # Assume Projects is sibling to scripts
        DatHashList.m_Path = project_dir + os.path.sep
        DatHashList.m_ProjectFilePath = os.path.join(DatHashList.m_Path, DatHashList.m_ProjectFile)
        Utils.iSetInfo(f"Using Project Path: {DatHashList.m_ProjectFilePath}") # Log path being used

        # Redirect core logic print statements? Maybe later.
        # For now, let them print to console and update high-level status here.

        # Perform the unpacking using the core logic
        Utils.iSetInfo(f"Starting unpack: {archive_path} -> {output_path}") # Log start
        DatUnpack.iDoIt(archive_path, output_path)

        # If iDoIt completes without raising an uncaught error in core logic
        g_status_message = "Unpacking completed successfully!"
        Utils.iSetInfo(g_status_message)

    except Exception as e:
        # Capture specific errors if needed (e.g., FileNotFoundError for hash list)
        if isinstance(e, FileNotFoundError) and "FileNames.list" in str(e):
             g_status_message = f"Error: Hash list 'FileNames.list' not found in {project_dir}"
        else:
             g_status_message = f"Error during unpacking: {type(e).__name__}\nSee console for details."

        # Print detailed traceback to console
        print(f"--- ERROR IN UNPACKING THREAD ---", file=sys.stderr)
        traceback.print_exc()
        print(f"--- END ERROR ---", file=sys.stderr)
        Utils.iSetError(f"Unpacking failed: {e}") # Log error via Utils

    finally:
        # Signal that unpacking is finished
        g_is_unpacking = False

# --- Main GUI Loop Function ---
def gui_loop():
    global g_archive_path, g_output_path, g_status_message, g_is_unpacking, g_unpacking_thread

    content_region = imgui.get_content_region_avail() # Removed '_able'

    # == File Selection ==
    imgui.text("Input Archive (.dat):")
    imgui.same_line(max(150, content_region.x * 0.25)) # Adjust alignment
    archive_button_text = "Select Archive..."
    if imgui.button(archive_button_text):
        # Use tkinter filedialog
        try:
            root_tk = tk.Tk()
            root_tk.withdraw() # Hide the main Tk window
            root_tk.attributes("-topmost", True) # Keep dialog on top
            archive_path_selected = filedialog.askopenfilename(
                title="Select Archive File",
                filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
            )
            root_tk.destroy() # Destroy the hidden window
        except Exception as tk_e:
             g_status_message = f"Error opening file dialog: {tk_e}"
             archive_path_selected = None

        if archive_path_selected: # Check if user selected a file (didn't cancel)
             # Use pathlib for robust normalization
             g_archive_path = str(pathlib.Path(archive_path_selected).resolve())
             g_status_message = "Archive selected. Select output folder."

    # Display selected path more clearly
    imgui.text("Selected:")
    imgui.same_line()
    display_archive_path = g_archive_path if g_archive_path else "No file selected"
    imgui.text_wrapped(display_archive_path) # Wrap if path is long


    # == Folder Selection ==
    imgui.separator()
    imgui.text("Output Folder:")
    imgui.same_line(max(150, content_region.x * 0.25)) # Adjust alignment
    output_button_text = "Select Output Folder..."
    if imgui.button(output_button_text):
        # Use tkinter filedialog
        try:
            root_tk = tk.Tk()
            root_tk.withdraw() # Create and hide root Tk window
            root_tk.attributes("-topmost", True) # Keep dialog on top
            output_path_selected = filedialog.askdirectory(
                title="Select Output Folder"
                # Optionally set initialdir='.'
            )
            root_tk.destroy() # Destroy the hidden window
        except Exception as tk_e:
             g_status_message = f"Error opening folder dialog: {tk_e}"
             output_path_selected = None

        if output_path_selected: # Check if user selected a folder
             # Use pathlib for robust normalization
             g_output_path = str(pathlib.Path(output_path_selected).resolve())
             g_status_message = "Output folder selected. Ready to unpack."

    # Display selected path more clearly
    imgui.text("Selected:")
    imgui.same_line()
    display_output_path = g_output_path if g_output_path else "No folder selected"
    imgui.text_wrapped(display_output_path) # Wrap if path is long


    # == Unpack Button ==
    imgui.separator()
    # Disable button if paths not set or already unpacking
    can_unpack = g_archive_path is not None and g_output_path is not None and not g_is_unpacking
    if not can_unpack:
        # Use Push/PopDisabled for modern ImGui feel
        imgui.begin_disabled()
        # imgui.internal.push_item_flag(imgui.internal.ItemFlags_.disabled, True)
        # imgui.push_style_var(imgui.StyleVar_.alpha, imgui.get_style().alpha * 0.5)

    button_pressed = imgui.button("Unpack Archive", size=ImVec2(content_region.x, 0)) # Make button full width

    if not can_unpack:
        imgui.end_disabled()
        # imgui.pop_style_var()
        # imgui.internal.pop_item_flag()

    if button_pressed and can_unpack: # Check if button was actually pressed while enabled
        g_is_unpacking = True
        g_status_message = "Starting unpacking..."
        # Start the unpacking in a separate thread to avoid freezing the GUI
        # Ensure paths passed are strings
        g_unpacking_thread = threading.Thread(
            target=run_unpacking_thread,
            args=(str(g_archive_path), str(g_output_path)), # Pass current paths as strings
            daemon=True # Allow program to exit even if thread is running
        )
        g_unpacking_thread.start()


    # == Status Display ==
    imgui.separator()
    imgui.text("Status:")
    # Potentially add a loading indicator when unpacking
    if g_is_unpacking:
         imgui.same_line()
         imgui.spinner("##unpacking_spinner", radius=8.0, thickness=2.0) # Basic spinner

    imgui.text_wrapped(g_status_message)


    # == Handle File Dialog Results ==
    # NO LONGER NEEDED - ImFileDialog display/check logic is removed.

# --- Application Entry Point ---
def main():
    # We no longer need to configure runner_params separately

    # Define the main loop function
    # Add exception handling around run() for robustness
    try:
        # Use Signature 3: Pass parameters directly as keywords to immapp.run
        immapp.run(
            gui_function=gui_loop,
            window_title="DAT Unpacker",
            window_size=[700, 300]  # Set window size directly here
            # Add other options from signature 3 if needed, like:
            # window_size_auto=False, # Prevent automatic resizing
        )
    except Exception as e:
        print(f"\n--- GUI CRASH ---", file=sys.stderr)
        print(f"An error occurred in the GUI application: {e}", file=sys.stderr)
        traceback.print_exc()
        print(f"--- END GUI CRASH ---", file=sys.stderr)
        # Basic fallback error message if GUI fails to start
        try:
            # Ensure tkinter is imported if using messagebox
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("GUI Error", f"A critical error occurred:\n{e}\n\nPlease see console output for details.")
            root.destroy()
        except Exception:
            pass # Ignore errors during fallback message

# --- ENSURE THIS LINE IS CORRECTLY INDENTED (NO INDENTATION) ---
if __name__ == "__main__":
    main()