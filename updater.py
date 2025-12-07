import os
import sys
import time
import zipfile
import requests
import subprocess
from pathlib import Path

def wait_for_file_release(path):
    """Wait until the target file can be opened for writing."""
    while True:
        try:
            with open(path, "a"):
                return
        except PermissionError:
            time.sleep(0.1)

def main():
    if len(sys.argv) < 2:
        print("Usage: updater.exe <download_url>")
        time.sleep(3)
        return

    url = sys.argv[1]
    exe_name = "DF_Overlay.exe"

    # REAL program directory — not the temp PyInstaller folder
    program_dir = Path(os.getcwd())
    target_exe = program_dir / exe_name
    zip_path = program_dir / "update.zip"

    print("Waiting for overlay to close...")
    time.sleep(1.2)

    print(f"Ensuring {exe_name} is not locked...")
    wait_for_file_release(target_exe)

    print("Downloading update...")
    r = requests.get(url, timeout=15)
    with open(zip_path, "wb") as f:
        f.write(r.content)

    print("Extracting update...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(program_dir)

    os.remove(zip_path)

    print("Launching updated program...")
    subprocess.Popen([str(target_exe)], cwd=str(program_dir))

    print("Done.")
    time.sleep(1.0)

if __name__ == "__main__":
    main()
