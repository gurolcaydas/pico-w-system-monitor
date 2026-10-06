import serial
import time
import sys

def execute_on_pico(code_str, port="COM3", baud=115200, timeout=10):
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1, dsrdtr=True, rtscts=False)
        ser.dtr = True
        ser.rts = True
        time.sleep(0.1)
        
        # Interrupt anything running
        ser.write(b'\r\x03\x03')
        time.sleep(0.2)
        ser.read_all()
        
        # Enter Raw REPL (Ctrl-A)
        ser.write(b'\r\x01')
        time.sleep(0.2)
        raw_msg = ser.read_all()
        if b'raw REPL' not in raw_msg:
            # Try again
            ser.write(b'\r\x03\x03\r\x01')
            time.sleep(0.3)
            raw_msg = ser.read_all()
            
        # Send code followed by Ctrl-D (execute)
        ser.write(code_str.encode('utf-8'))
        ser.write(b'\x04')
        
        start_time = time.time()
        output = b""
        
        while time.time() - start_time < timeout:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                output += chunk
                if b'\x04>' in output:  # End of raw REPL output
                    break
            else:
                time.sleep(0.05)
                
        # Exit Raw REPL (Ctrl-B)
        ser.write(b'\x02')
        ser.close()
        
        # Parse output: MicroPython outputs OK then stdout then \x04 then stderr then \x04>
        clean_out = output.decode('utf-8', errors='replace')
        return clean_out
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            code = f.read()
    else:
        code = "import os; print('Pico OS info:', os.uname())"
        
    print(execute_on_pico(code))
