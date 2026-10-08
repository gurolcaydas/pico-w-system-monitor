import serial
import time
import sys
import os

def upload_file(port, local_path, remote_path):
    with open(local_path, 'rb') as f:
        content = f.read()

    ser = serial.Serial(port, 115200, timeout=1, dsrdtr=True)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.1)

    # Interrupt and enter raw REPL
    ser.write(b'\r\x03\x03\r\x01')
    time.sleep(0.3)
    ser.read_all()

    # Create file writing command in chunks
    chunk_size = 512
    cmd = f"f = open('{remote_path}', 'wb')\r".encode('utf-8')
    ser.write(cmd)
    ser.write(b'\x04')
    time.sleep(0.1)
    ser.read_all()

    for i in range(0, len(content), chunk_size):
        chunk = content[i:i+chunk_size]
        write_chunk_cmd = f"f.write({repr(chunk)})\r".encode('utf-8')
        ser.write(write_chunk_cmd)
        ser.write(b'\x04')
        time.sleep(0.05)
        ser.read_all()

    ser.write(b"f.close()\r\x04")
    time.sleep(0.1)
    ser.read_all()
    ser.close()
    print(f"Uploaded {local_path} -> {remote_path} ({len(content)} bytes)")

import subprocess

def precompile_modules(mod_list):
    print("Pre-compiling modules with mpy-cross for zero heap fragmentation...")
    for fn in mod_list:
        if os.path.exists(fn):
            res = subprocess.run([sys.executable, "-m", "mpy_cross", fn], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Warning compiling {fn}: {res.stderr}")

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    
    if not os.path.exists("secrets.py"):
        print("ERROR: secrets.py not found!")
        print("Please copy secrets.example.py to secrets.py and configure your Wi-Fi credentials:")
        print("   cp secrets.example.py secrets.py")
        sys.exit(1)

    # Copy main.py to main_app.py for bytecode pre-compilation
    import shutil
    shutil.copyfile("main.py", "main_app.py")

    mpy_sources = [
        "main_app.py", "picoui.py", "lan_scanner.py", "weather.py",
        "youtube_service.py", "moon.py", "screensaver.py",
        "blackjack.py", "galaxy.py", "copter.py", "viper.py", "brick.py", "lander.py", "pong.py"
    ]
    precompile_modules(mpy_sources)

    # Minimal launcher for main.py to load pre-compiled main_app.mpy
    with open("main_loader.py", "w") as f:
        f.write("import gc\ngc.collect()\nimport main_app\n")

    # Files to upload: boot.py, launcher main.py, .mpy files, config & assets
    upload_files = [
        ("boot.py", "boot.py"),
        ("lcd1in44.py", "lcd1in44.py"),
        ("ssd1306.py", "ssd1306.py"),
        ("secrets.py", "secrets.py"),
        ("main_loader.py", "main.py"),
    ]
    for s in mpy_sources:
        mpy_name = s.replace(".py", ".mpy")
        if os.path.exists(mpy_name):
            upload_files.append((mpy_name, mpy_name))

    if os.path.exists("yt_views.txt"):
        upload_files.append(("yt_views.txt", "yt_views.txt"))
    if os.path.exists("lan_devices.txt"):
        upload_files.append(("lan_devices.txt", "lan_devices.txt"))

    # Connect to Pico and clean up old .py files that now have .mpy equivalents
    ser = serial.Serial(port, 115200, timeout=1, dsrdtr=True)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.1)
    ser.write(b'\r\x03\x03\r\x01')
    time.sleep(0.3)
    cleanup_cmd = b"import os\rfor f in ['main_app.py','picoui.py','lan_scanner.py','weather.py','youtube_service.py','moon.py','screensaver.py']:\r try: os.remove(f)\r except: pass\r\x04"
    ser.write(cleanup_cmd)
    time.sleep(0.3)
    ser.read_all()
    ser.write(b'\x02')
    ser.close()

    print(f"Uploading files to Pico on {port}...")
    for local_fn, remote_fn in upload_files:
        upload_file(port, local_fn, remote_fn)
        time.sleep(0.05)
        
    print("Restarting Pico W...")
    ser = serial.Serial(port, 115200, timeout=1, dsrdtr=True)
    ser.write(b'\r\x03\x03\r\x01import machine\rmachine.reset()\r\x04')
    ser.close()
    print("Pre-compiled bytecode environment deployed and started on Pico W!")
