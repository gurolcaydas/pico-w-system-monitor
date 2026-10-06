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

if __name__ == "__main__":
    port = "COM3"
    files = ["lcd1in44.py", "ssd1306.py", "secrets.py", "picoui.py", "main.py"]
    for fn in files:
        upload_file(port, fn, fn)
        time.sleep(0.1)
        
    # Exit raw REPL with Ctrl-B, then soft-reboot with Ctrl-D to start main.py
    ser = serial.Serial(port, 115200, timeout=1, dsrdtr=True)
    ser.write(b'\x02\r\x03\x04')
    ser.close()
    print("Clean environment with libraries deployed and started on Pico W!")
