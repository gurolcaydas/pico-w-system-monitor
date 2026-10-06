import socket
import json
import time
import gc

WX_FILE = "weather.txt"

def load_wx_config():
    try:
        with open(WX_FILE, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            if len(lines) >= 3:
                return lines[0], float(lines[1]), float(lines[2]), True
    except Exception:
        pass
    return "AUTO", 38.625, 34.714, False

def save_wx_config(city, lat, lon):
    try:
        with open(WX_FILE, "w") as f:
            f.write(city.strip() + "\n")
            f.write(f"{lat:.4f}\n")
            f.write(f"{lon:.4f}\n")
    except Exception:
        pass

wx_override_city, wx_override_lat, wx_override_lon, wx_is_manual = load_wx_config()

loc_data = {
    "city": wx_override_city if wx_is_manual else "DETECTING",
    "lat": wx_override_lat,
    "lon": wx_override_lon,
    "resolved": wx_is_manual,
}

weather_data = {
    "temp": None,
    "humidity": None,
    "wind": None,
    "code": 0,
    "desc": "WAIT",
    "history": [],  # Bounded to 16 samples
    "min_t": None,
    "max_t": None,
    "status": "WAIT",
    "last_sync": 0,
}
last_weather_check_time = 0

def resolve_location(wlan_connected):
    global loc_data
    if not wlan_connected or wx_is_manual:
        return loc_data["resolved"]
    s = None
    try:
        host = "ip-api.com"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(4.0)
        s.connect(ai)
        req = f"GET /json/?fields=status,city,lat,lon HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\n\r\n"
        s.send(req.encode())
        data = b""
        while True:
            c = s.recv(512)
            if not c:
                break
            data += c
            if len(data) > 2048:
                break
        parts = data.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            res = json.loads(parts[1].decode('utf-8', 'ignore'))
            if res.get("status") == "success":
                raw_city = res.get("city", "UNKNOWN")
                clean_city = raw_city.replace("İ", "I").replace("ı", "i").replace("ş", "s").replace("Ş", "S") \
                                     .replace("ğ", "g").replace("Ğ", "G").replace("ü", "u").replace("Ü", "U") \
                                     .replace("ö", "o").replace("Ö", "O").replace("ç", "c").replace("Ç", "C")
                loc_data["city"] = clean_city[:12].upper()
                loc_data["lat"] = float(res.get("lat", 38.625))
                loc_data["lon"] = float(res.get("lon", 34.714))
                loc_data["resolved"] = True
                return True
    except Exception:
        pass
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        gc.collect()
    return False

def get_wx_desc(code):
    if code == 0: return "CLEAR"
    elif code in (1, 2): return "PARTLY"
    elif code == 3: return "CLOUDY"
    elif code in (45, 48): return "FOG"
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82): return "RAIN"
    elif code in (71, 73, 75, 85, 86): return "SNOW"
    elif code in (95, 96, 99): return "STORM"
    return "FAIR"

def fetch_weather(wlan_connected):
    global weather_data
    if not wlan_connected:
        weather_data["status"] = "NO-WIFI"
        return False
    if not loc_data["resolved"]:
        resolve_location(wlan_connected)
    s = None
    try:
        lat = loc_data["lat"]
        lon = loc_data["lon"]
        host = "api.open-meteo.com"
        path = f"/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\n\r\n"
        s.send(req.encode())
        data = b""
        while True:
            c = s.recv(512)
            if not c:
                break
            data += c
            if len(data) > 3072:
                break
        parts = data.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            res = json.loads(parts[1].decode('utf-8', 'ignore'))
            cur = res.get("current", {})
            if "temperature_2m" in cur:
                t = float(cur["temperature_2m"])
                weather_data["temp"] = t
                weather_data["humidity"] = int(cur.get("relative_humidity_2m", 0))
                weather_data["wind"] = float(cur.get("wind_speed_10m", 0.0))
                code = int(cur.get("weather_code", 0))
                weather_data["code"] = code
                weather_data["desc"] = get_wx_desc(code)
                weather_data["last_sync"] = time.time()
                weather_data["status"] = "OK"

                if weather_data["min_t"] is None or t < weather_data["min_t"]:
                    weather_data["min_t"] = t
                if weather_data["max_t"] is None or t > weather_data["max_t"]:
                    weather_data["max_t"] = t

                weather_data["history"].append(int(round(t)))
                if len(weather_data["history"]) > 16:
                    weather_data["history"].pop(0)
                return True
    except Exception:
        weather_data["status"] = "ERR"
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        gc.collect()
    return False
