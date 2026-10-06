import socket
import ssl
import json
import time
import math
import gc
import network
import machine

TZ_OFFSET = 3 * 3600

loc_info = {
    "lat": 38.625,
    "lon": 34.714,
    "city": "KAPADOKYA"
}

DAYS = ["PAZARTESI", "SALI", "CARSAMBA", "PERSEMBE", "CUMA", "CUMARTESI", "PAZAR"]
DAYS_SHORT = ["PZT", "SAL", "CRS", "PER", "CUM", "CTS", "PAZ"]
MONTHS = ["OCA", "SUB", "MAR", "NIS", "MAY", "HAZ", "TEM", "AGU", "EYL", "EKI", "KAS", "ARA"]

def get_now_tuple():
    return time.localtime(time.time() + TZ_OFFSET)

def get_time_str():
    t = get_now_tuple()
    return f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

def get_short_time_str():
    t = get_now_tuple()
    return f"{t[3]:02d}:{t[4]:02d}"

def get_date_str():
    t = get_now_tuple()
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"

def get_comfort_rating(tc, h):
    if h < 32: return "Kuru Hava"
    elif h > 68: return "Yuksek Nem"
    elif tc < 18: return "Serin"
    elif tc > 27: return "Sicak"
    elif 19 <= tc <= 25 and 40 <= h <= 60: return "Mukemmel Konfor"
    return "Normal"

def get_dew_point(tc, h):
    return round(tc - ((100 - h) / 5), 1)

def get_moon_info():
    t = get_now_tuple()
    y, m, d, h = t[0], t[1], t[2], t[3]
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + (a // 4)
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5
    jd += h / 24.0
    
    synodic = 29.53058867
    ref_new_moon = 2451550.26
    age = (jd - ref_new_moon) % synodic
    
    if age < 1.85: p_name = "YENI AY"
    elif age < 5.54: p_name = "HILAL"
    elif age < 9.23: p_name = "ILK DORDUN"
    elif age < 12.92: p_name = "SISKIN AY"
    elif age < 16.61: p_name = "DOLUNAY"
    elif age < 20.30: p_name = "SISKIN AY"
    elif age < 23.99: p_name = "SON DORDUN"
    elif age < 27.68: p_name = "HILAL"
    else: p_name = "YENI AY"
        
    full_target = 14.76529
    if age <= full_target:
        days_to_full = full_target - age
    else:
        days_to_full = synodic + full_target - age
        
    illum = (1 - math.cos(2 * math.pi * age / synodic)) / 2 * 100
    return {
        "age_days": round(age, 1),
        "phase_name": p_name,
        "illumination_pct": round(illum),
        "days_to_full": round(days_to_full, 1),
        "days_to_full_int": round(days_to_full)
    }

tcmb_rates = {
    "buying": "48.97",
    "selling": "49.06",
    "last_update": 0
}

def update_tcmb_rates():
    now = time.ticks_ms()
    if tcmb_rates["last_update"] != 0 and time.ticks_diff(now, tcmb_rates["last_update"]) < 1800000:
        return
    try:
        host = "www.tcmb.gov.tr"
        ai = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        s = ssl.wrap_socket(s)
        req = "GET /kurlar/today.xml HTTP/1.1\r\nHost: " + host + "\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
        s.write(req.encode())
        buf = b""
        while True:
            chunk = s.read(512)
            if not chunk: break
            buf += chunk
            if b"<ForexSelling>" in buf and b"</ForexSelling>" in buf: break
            if len(buf) > 4096: break
        s.close()
        text = str(buf, 'utf-8')
        if "<ForexBuying>" in text:
            b_start = text.find("<ForexBuying>") + len("<ForexBuying>")
            b_end = text.find("</ForexBuying>", b_start)
            tcmb_rates["buying"] = text[b_start:b_end].strip()
        if "<ForexSelling>" in text:
            s_start = text.find("<ForexSelling>") + len("<ForexSelling>")
            s_end = text.find("</ForexSelling>", s_start)
            tcmb_rates["selling"] = text[s_start:s_end].strip()
        tcmb_rates["last_update"] = now
        print(f"-> TCMB Kurlari guncellendi: Alis {tcmb_rates['buying']}, Satis {tcmb_rates['selling']}")
    except Exception as e:
        print("TCMB uyari:", e)

usd_rates = {
    "history_30d": [48.25, 48.26, 48.27, 48.29, 48.32, 48.44, 48.43, 48.46, 48.48, 48.50, 48.60, 48.62, 48.64, 48.66, 48.68, 48.78, 48.80, 48.81, 48.84, 48.86, 48.93, 48.98, 49.00, 49.02, 49.03, 49.15],
    "last_chart_update": 0
}

def update_usd_history():
    now = time.ticks_ms()
    if usd_rates["last_chart_update"] != 0 and time.ticks_diff(now, usd_rates["last_chart_update"]) < 7200000:
        return
    try:
        t_now = get_now_tuple()
        t_past = time.localtime(time.time() + TZ_OFFSET - 35 * 86400)
        start_d = f"{t_past[0]:04d}-{t_past[1]:02d}-{t_past[2]:02d}"
        end_d = f"{t_now[0]:04d}-{t_now[1]:02d}-{t_now[2]:02d}"
        host = "api.frankfurter.dev"
        path = f"/v1/{start_d}..{end_d}?from=USD&to=TRY"
        ai = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket()
        s.settimeout(8.0)
        s.connect(ai)
        s = ssl.wrap_socket(s, server_hostname=host)
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
        s.write(req.encode())
        buf = b""
        while True:
            c = s.read(512)
            if not c: break
            buf += c
            if len(buf) > 8192: break
        s.close()
        parts = buf.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            data = json.loads(parts[1].decode())
            r_dict = data.get("rates", {})
            rates = [v["TRY"] for k, v in sorted(r_dict.items())]
            if len(rates) >= 5:
                usd_rates["history_30d"] = rates
                usd_rates["last_chart_update"] = now
                print(f"-> USD 30G Gecmis guncellendi: {len(rates)} gun")
    except Exception as e:
        print("USD uyari:", e)

eur_rates = {
    "history_30d": [55.96, 56.10, 56.17, 56.24],
    "last_chart_update": 0
}

def update_eur_history():
    now = time.ticks_ms()
    if eur_rates["last_chart_update"] != 0 and time.ticks_diff(now, eur_rates["last_chart_update"]) < 7200000:
        return
    try:
        t_now = get_now_tuple()
        t_past = time.localtime(time.time() + TZ_OFFSET - 35 * 86400)
        start_d = f"{t_past[0]:04d}-{t_past[1]:02d}-{t_past[2]:02d}"
        end_d = f"{t_now[0]:04d}-{t_now[1]:02d}-{t_now[2]:02d}"
        host = "api.frankfurter.dev"
        path = f"/v1/{start_d}..{end_d}?from=EUR&to=TRY"
        ai = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket()
        s.settimeout(8.0)
        s.connect(ai)
        s = ssl.wrap_socket(s, server_hostname=host)
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
        s.write(req.encode())
        buf = b""
        while True:
            c = s.read(512)
            if not c: break
            buf += c
            if len(buf) > 8192: break
        s.close()
        parts = buf.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            data = json.loads(parts[1].decode())
            r_dict = data.get("rates", {})
            rates = [v["TRY"] for k, v in sorted(r_dict.items())]
            if len(rates) >= 5:
                eur_rates["history_30d"] = rates
                eur_rates["last_chart_update"] = now
                print(f"-> EUR 30G Gecmis guncellendi: {len(rates)} gun")
    except Exception as e:
        print("EUR uyari:", e)

gold_rates = {
    "history_30d": [6350.0, 6420.0, 6480.0, 6541.8],
    "last_chart_update": 0
}

def update_gold_history():
    now = time.ticks_ms()
    if gold_rates["last_chart_update"] != 0 and time.ticks_diff(now, gold_rates["last_chart_update"]) < 7200000:
        return
    try:
        host = "api.nbp.pl"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        path = "/api/cenyzlota/last/30?format=json"
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\n\r\n"
        s.send(req.encode())
        buf = b""
        while True:
            c = s.recv(512)
            if not c: break
            buf += c
            if len(buf) > 4096: break
        s.close()
        parts = buf.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            data = json.loads(parts[1].decode())
            rates = [round(pt["cena"] * 12.64, 1) for pt in data]
            if len(rates) >= 5:
                gold_rates["history_30d"] = rates
                gold_rates["last_chart_update"] = now
                print(f"-> Gram Altin guncellendi: {len(rates)} gun, son {rates[-1]:.1f} TL")
    except Exception as e:
        print("Altin uyari:", e)

ping_data = {
    "current_ms": 35,
    "history": [35] * 20,
    "last_update": 0
}

def update_ping():
    now = time.ticks_ms()
    if ping_data["last_update"] != 0 and time.ticks_diff(now, ping_data["last_update"]) < 15000:
        return
    try:
        t0 = time.ticks_ms()
        ai = socket.getaddrinfo("1.1.1.1", 53)[0][-1]
        s = socket.socket()
        s.settimeout(2.0)
        s.connect(ai)
        t1 = time.ticks_ms()
        s.close()
        lat = time.ticks_diff(t1, t0)
        ping_data["current_ms"] = lat
        ping_data["history"].append(lat)
        if len(ping_data["history"]) > 20:
            ping_data["history"].pop(0)
        ping_data["last_update"] = now
    except Exception as e:
        ping_data["current_ms"] = 99

earthquake_data = {
    "mag": 2.4,
    "loc": "IC ANADOLU",
    "depth": 7.0,
    "time": "20:45",
    "last_update": 0
}

def update_earthquake():
    now = time.ticks_ms()
    if earthquake_data["last_update"] != 0 and time.ticks_diff(now, earthquake_data["last_update"]) < 300000:
        return
    try:
        host = "www.koeri.boun.edu.tr"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        req = "GET /scripts/lst0.asp HTTP/1.0\r\nHost: " + host + "\r\nUser-Agent: Mozilla/5.0\r\n\r\n"
        s.send(req.encode())
        buf = b""
        while True:
            c = s.recv(512)
            if not c: break
            buf += c
            if b"---------- --------" in buf:
                c2 = s.recv(512)
                if c2: buf += c2
                break
            if len(buf) > 8192: break
        s.close()
        idx = buf.find(b"---------- --------")
        if idx != -1:
            line_start = buf.find(b"\n", idx) + 1
            line_end = buf.find(b"\n", line_start)
            line_bytes = buf[line_start:line_end]
            raw = "".join([chr(b) if 32 <= b < 127 else " " for b in line_bytes]).strip()
            parts = raw.split()
            if len(parts) >= 8:
                earthquake_data["time"] = parts[1][:5]
                earthquake_data["depth"] = parts[4]
                earthquake_data["mag"] = parts[6] if parts[6] != "-.-" else parts[5]
                loc = " ".join(parts[8:10]).replace("Ilksel", "").strip()
                earthquake_data["loc"] = loc[:16]
                earthquake_data["last_update"] = now
                print(f"-> Kandilli Deprem: {earthquake_data['mag']} ML - {earthquake_data['loc']}")
    except Exception as e:
        print("Deprem uyari:", e)

air_quality_data = {
    "aqi": 18,
    "aqi_txt": "MUKEMMEL",
    "pm25": 4.5,
    "pm10": 5.5,
    "uv": 0.0,
    "last_update": 0
}

def update_air_quality():
    now = time.ticks_ms()
    if air_quality_data["last_update"] != 0 and time.ticks_diff(now, air_quality_data["last_update"]) < 1800000:
        return
    try:
        host = "air-quality-api.open-meteo.com"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        path = "/v1/air-quality?latitude=38.625&longitude=34.714&current=european_aqi,pm2_5,pm10,uv_index"
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\n\r\n"
        s.send(req.encode())
        buf = b""
        while True:
            c = s.recv(512)
            if not c: break
            buf += c
            if len(buf) > 2048: break
        s.close()
        parts = buf.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            data = json.loads(parts[1].decode())
            cur = data.get("current", {})
            aqi = cur.get("european_aqi", 20)
            if aqi <= 20: aqi_txt = "MUKEMMEL"
            elif aqi <= 40: aqi_txt = "IYI"
            elif aqi <= 60: aqi_txt = "ORTA"
            else: aqi_txt = "KOTU"
            air_quality_data["aqi"] = int(aqi)
            air_quality_data["aqi_txt"] = aqi_txt
            air_quality_data["pm25"] = round(cur.get("pm2_5", 8.0), 1)
            air_quality_data["pm10"] = round(cur.get("pm10", 14.0), 1)
            air_quality_data["uv"] = round(cur.get("uv_index", 0.0), 1)
            air_quality_data["last_update"] = now
            print(f"-> Hava Kalitesi: AQI {aqi} ({aqi_txt})")
    except Exception as e:
        print("Hava kalitesi uyari:", e)

def calc_prayer_times():
    lat, lon = loc_info["lat"], loc_info["lon"]
    tz = 3.0
    t_now = get_now_tuple()
    year, month, day = t_now[0], t_now[1], t_now[2]
    cur_m = t_now[3] * 60 + t_now[4]
    
    N1 = math.floor(275 * month / 9)
    N2 = math.floor((month + 9) / 12)
    N3 = (1 + math.floor((year - 4 * math.floor(year / 4) + 2) / 3))
    N = N1 - (N2 * N3) + day - 30
    lngHour = lon / 15.0

    def calc_solar(t_event, zenith, is_morning):
        M = (0.9856 * t_event) - 3.289
        L = (M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634) % 360.0
        RA = (math.degrees(math.atan(0.91764 * math.tan(math.radians(L))))) % 360.0
        Lquadrant  = (math.floor(L / 90.0)) * 90.0
        RAquadrant = (math.floor(RA / 90.0)) * 90.0
        RA = (RA + (Lquadrant - RAquadrant)) / 15.0
        sinDec = 0.39782 * math.sin(math.radians(L))
        cosDec = math.cos(math.asin(sinDec))
        cosH = (math.cos(math.radians(zenith)) - (sinDec * math.sin(math.radians(lat)))) / (cosDec * math.cos(math.radians(lat)))
        if cosH > 1: return 6, 0
        if cosH < -1: return 18, 0
        H = (360.0 - math.degrees(math.acos(cosH))) if is_morning else math.degrees(math.acos(cosH))
        H = H / 15.0
        T = H + RA - (0.06571 * t_event) - 6.622
        UT = (T - lngHour) % 24.0
        local_time = (UT + tz) % 24.0
        hh = int(local_time)
        mm = int((local_time - hh) * 60.0 + 0.5)
        if mm >= 60:
            hh = (hh + 1) % 24
            mm = 0
        return hh, mm

    t_base = N + ((12.0 - lngHour) / 24.0)
    fajr_h, fajr_m = calc_solar(N + ((5.0 - lngHour)/24.0), 108.0, True)
    rise_h, rise_m = calc_solar(N + ((6.0 - lngHour)/24.0), 90.833, True)
    set_h, set_m   = calc_solar(N + ((18.0 - lngHour)/24.0), 90.833, False)
    isha_h, isha_m = calc_solar(N + ((19.5 - lngHour)/24.0), 107.0, False)

    M = (0.9856 * t_base) - 3.289
    L = (M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634) % 360.0
    dec = math.degrees(math.asin(0.39782 * math.sin(math.radians(L))))
    alt_asr = math.degrees(math.atan(1.0 / (1.0 + math.tan(math.radians(abs(lat - dec))))))
    asr_h, asr_m = calc_solar(N + ((15.5 - lngHour)/24.0), 90.0 - alt_asr, False)

    dhuhr_m = (rise_m + (set_h*60 + set_m - rise_h*60 - rise_m)//2)
    dh_h = (rise_h * 60 + dhuhr_m) // 60
    dh_m = (rise_h * 60 + dhuhr_m) % 60

    slots = [
        ("IMSAK", fajr_h * 60 + fajr_m, f"{fajr_h:02d}:{fajr_m:02d}"),
        ("GUNES", rise_h * 60 + rise_m, f"{rise_h:02d}:{rise_m:02d}"),
        ("OGLE", dh_h * 60 + dh_m, f"{dh_h:02d}:{dh_m:02d}"),
        ("IKINDI", asr_h * 60 + asr_m, f"{asr_h:02d}:{asr_m:02d}"),
        ("AKSAM", set_h * 60 + set_m, f"{set_h:02d}:{set_m:02d}"),
        ("YATSI", isha_h * 60 + isha_m, f"{isha_h:02d}:{isha_m:02d}")
    ]
    
    next_name, next_diff = "IMSAK", 0
    for name, s_mins, s_str in slots:
        if s_mins > cur_m:
            next_name = name
            next_diff = s_mins - cur_m
            break
    else:
        next_name = "IMSAK"
        next_diff = (24 * 60 - cur_m) + slots[0][1]
        
    diff_h = next_diff // 60
    diff_m = next_diff % 60
    countdown = f"{diff_h}s {diff_m:02d}d" if diff_h > 0 else f"{diff_m}d"
    return {"slots": slots, "next_name": next_name, "countdown": countdown}

iss_data = {
    "dist_km": 3450,
    "lat": 12.5,
    "lon": 45.0,
    "alt": 425,
    "vis": "GUNDUZ",
    "last_update": 0
}

def update_iss():
    now = time.ticks_ms()
    if iss_data["last_update"] != 0 and time.ticks_diff(now, iss_data["last_update"]) < 120000:
        return
    try:
        host = "api.wheretheiss.at"
        ai = socket.getaddrinfo(host, 443)[0][-1]
        s = socket.socket()
        s.settimeout(6.0)
        s.connect(ai)
        s = ssl.wrap_socket(s, server_hostname=host)
        path = "/v1/satellites/25544"
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\nConnection: close\r\n\r\n"
        s.write(req.encode())
        buf = b""
        while True:
            c = s.read(512)
            if not c: break
            buf += c
            if len(buf) > 2048: break
        s.close()
        parts = buf.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            data = json.loads(parts[1].decode())
            iss_lat = data.get("latitude", 0.0)
            iss_lon = data.get("longitude", 0.0)
            alt = round(data.get("altitude", 420.0))
            c_lat, c_lon = loc_info["lat"], loc_info["lon"]
            dlat = math.radians(iss_lat - c_lat)
            dlon = math.radians(iss_lon - c_lon)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(c_lat)) * math.cos(math.radians(iss_lat)) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_km = int(6371 * c)
            iss_data["dist_km"] = dist_km
            iss_data["lat"] = round(iss_lat, 1)
            iss_data["lon"] = round(iss_lon, 1)
            iss_data["alt"] = alt
            raw_vis = data.get("visibility", "daylight").lower()
            iss_data["vis"] = "GUNDUZ" if "day" in raw_vis else "GOLGE"
            iss_data["last_update"] = now
            print(f"-> ISS guncellendi: Mesafe {dist_km} km")
    except Exception as e:
        print("ISS uyari:", e)

def get_weather_desc(code):
    if code == 0: return "ACIK HAVA"
    elif code in (1, 2): return "AZ BULUTLU"
    elif code == 3: return "KAPALI HAVA"
    elif code in (45, 48): return "SISLI"
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82): return "YAGMURLU"
    elif code in (71, 73, 75, 85, 86): return "KARLI"
    elif code in (95, 96, 99): return "FIRTINALI"
    return "ACIK HAVA"

sky_weather = {
    "temp": 9.8,
    "humidity": 72,
    "wind": 6.4,
    "weather_code": 0,
    "cloud_cover": 20,
    "condition": "ACIK HAVA",
    "balloon_day": "YARIN",
    "balloon_date": "03 EKI",
    "balloon_status": "UCUS VAR",
    "balloon_wind": 6.4,
    "balloon_slot_temp": 8.6,
    "daily_3day": {
        "weather_code": [0, 1, 61],
        "temperature_2m_max": [16.0, 14.5, 12.0],
        "temperature_2m_min": [6.0, 5.0, 4.0]
    },
    "last_update": 0
}

def update_cappadocia_weather():
    now = time.ticks_ms()
    if sky_weather["last_update"] != 0 and time.ticks_diff(now, sky_weather["last_update"]) < 1200000:
        return
    try:
        host = "api.open-meteo.com"
        path = "/v1/forecast?latitude=38.625&longitude=34.714&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,cloud_cover&hourly=wind_speed_10m,temperature_2m&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=3&timezone=Europe%2FIstanbul"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(8.0)
        s.connect(ai)
        req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: PicoW\r\n\r\n"
        s.send(req.encode())
        data = b""
        while True:
            chunk = s.recv(512)
            if not chunk: break
            data += chunk
            if len(data) > 6144: break
        s.close()
        parts = data.split(b"\r\n\r\n", 1)
        if len(parts) > 1:
            parsed = json.loads(parts[1].decode())
            current = parsed.get("current", {})
            out_t = current.get("temperature_2m", sky_weather["temp"])
            out_h = current.get("relative_humidity_2m", sky_weather["humidity"])
            wind = current.get("wind_speed_10m", sky_weather["wind"])
            code = current.get("weather_code", 0)
            
            sky_weather["temp"] = float(out_t)
            sky_weather["humidity"] = int(out_h)
            sky_weather["wind"] = float(wind)
            sky_weather["weather_code"] = int(code)
            sky_weather["condition"] = get_weather_desc(int(code))
            sky_weather["cloud_cover"] = int(current.get("cloud_cover", 20))
            daily = parsed.get("daily", {})
            if daily:
                sky_weather["daily_3day"] = daily

            t_local = get_now_tuple()
            current_hour = t_local[3]
            hourly = parsed.get("hourly", {})
            h_winds = hourly.get("wind_speed_10m", [])
            h_temps = hourly.get("temperature_2m", [])
            
            if current_hour < 8:
                idx = 6
                sky_weather["balloon_day"] = "BUGUN"
                sky_weather["balloon_date"] = f"{t_local[2]:02d} {MONTHS[(t_local[1]-1)%12]}"
            else:
                idx = 30
                t_tom = time.localtime(time.time() + TZ_OFFSET + 86400)
                sky_weather["balloon_day"] = "YARIN"
                sky_weather["balloon_date"] = f"{t_tom[2]:02d} {MONTHS[(t_tom[1]-1)%12]}"
                
            if len(h_winds) > idx + 1 and len(h_temps) > idx + 1:
                b_wind = round((h_winds[idx] + h_winds[idx+1]) / 2, 1)
                b_temp = round((h_temps[idx] + h_temps[idx+1]) / 2, 1)
            else:
                b_wind = float(wind)
                b_temp = float(out_t)
                
            sky_weather["balloon_wind"] = b_wind
            sky_weather["balloon_slot_temp"] = b_temp
            
            if b_wind < 12.0: sky_weather["balloon_status"] = "UCUS VAR"
            elif b_wind <= 17.0: sky_weather["balloon_status"] = "DIKKAT"
            else: sky_weather["balloon_status"] = "IPTAL"
                
            sky_weather["last_update"] = now
            print(f"-> Hava ve Balon: Disari {out_t}C, Balon: {sky_weather['balloon_status']}")
    except Exception as e:
        print("Hava durumu uyari:", e)

def calculate_sun_times():
    t = get_now_tuple()
    year, month, day = t[0], t[1], t[2]
    lat, lon, tz = loc_info["lat"], loc_info["lon"], 3.0
    N1 = math.floor(275 * month / 9)
    N2 = math.floor((month + 9) / 12)
    N3 = (1 + math.floor((year - 4 * math.floor(year / 4) + 2) / 3))
    N = N1 - (N2 * N3) + day - 30
    lngHour = lon / 15.0
    t_rise = N + ((6.0 - lngHour) / 24.0)
    t_set = N + ((18.0 - lngHour) / 24.0)
    
    def calc_event(t_event, is_rise):
        M = (0.9856 * t_event) - 3.289
        L = (M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634) % 360.0
        RA = (math.degrees(math.atan(0.91764 * math.tan(math.radians(L))))) % 360.0
        Lquadrant  = (math.floor(L / 90.0)) * 90.0
        RAquadrant = (math.floor(RA / 90.0)) * 90.0
        RA = (RA + (Lquadrant - RAquadrant)) / 15.0
        sinDec = 0.39782 * math.sin(math.radians(L))
        cosDec = math.cos(math.asin(sinDec))
        zenith = 90.8333
        cosH = (math.cos(math.radians(zenith)) - (sinDec * math.sin(math.radians(lat)))) / (cosDec * math.cos(math.radians(lat)))
        if cosH > 1 or cosH < -1: return 6, 0
        H = (360.0 - math.degrees(math.acos(cosH))) if is_rise else math.degrees(math.acos(cosH))
        H = H / 15.0
        T = H + RA - (0.06571 * t_event) - 6.622
        UT = (T - lngHour) % 24.0
        local_time = (UT + tz) % 24.0
        hh = int(local_time)
        mm = int((local_time - hh) * 60.0 + 0.5)
        if mm >= 60:
            hh = (hh + 1) % 24
            mm = 0
        return hh, mm
        
    rh, rm = calc_event(t_rise, True)
    sh, sm = calc_event(t_set, False)
    diff_mins = (sh * 60 + sm) - (rh * 60 + rm)
    if diff_mins < 0: diff_mins += 24 * 60
    return {
        "sunrise": f"{rh:02d}:{rm:02d}",
        "sunset": f"{sh:02d}:{sm:02d}",
        "daylight": f"{diff_mins // 60}s {diff_mins % 60:02d}d",
        "city": loc_info["city"]
    }

def calc_stargazing():
    cloud_pct = sky_weather.get("cloud_cover", 20)
    moon_pct = get_moon_info().get("illumination_pct", 50)
    score = max(0, min(100, int(100 - (cloud_pct * 0.7) - (moon_pct * 0.3))))
    if score >= 80: desc = "MUKEMMEL"
    elif score >= 60: desc = "IYI"
    elif score >= 40: desc = "ORTA"
    else: desc = "UYGUN DEGIL"
    return {
        "score": score,
        "desc": desc,
        "cloud_cover": cloud_pct,
        "moon_illum": moon_pct
    }

def jdn(y, m, d):
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + (a // 4)
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524

def calc_next_holiday():
    t_now = get_now_tuple()
    y, m, d, hh = t_now[0], t_now[1], t_now[2], t_now[3]
    cur_jdn = jdn(y, m, d)
    holidays = [
        ("23 NISAN", 4, 23, "COCUK BAYRAMI"),
        ("1 MAYIS", 5, 1, "EMEK BAYRAMI"),
        ("19 MAYIS", 5, 19, "GENCLIK SPOR"),
        ("15 TEMMUZ", 7, 15, "DEMOKRASI"),
        ("30 AGUSTOS", 8, 30, "ZAFER BAYRAMI"),
        ("29 EKIM", 10, 29, "CUMHURIYET"),
        ("10 KASIM", 11, 10, "ATATURK"),
        ("1 OCAK", 1, 1, "YILBASI 2027")
    ]
    best_event = None
    min_days = 99999
    for name, hm, hd, sub in holidays:
        target_y = y if (hm > m or (hm == m and hd >= d)) else y + 1
        target_jdn = jdn(target_y, hm, hd)
        diff_days = target_jdn - cur_jdn
        if diff_days >= 0 and diff_days < min_days:
            min_days = diff_days
            total_hours = diff_days * 24 - hh
            if total_hours < 0: total_hours = 0
            d_remain = total_hours // 24
            h_remain = total_hours % 24
            best_event = {
                "name": name,
                "sub": sub,
                "target_date": f"{hd:02d}.{hm:02d}.{target_y}",
                "days": diff_days,
                "d_remain": d_remain,
                "h_remain": h_remain
            }
    return best_event

def read_device_telemetry(adc_cpu, start_time):
    try:
        raw = adc_cpu.read_u16() * (3.3 / 65535)
        cpu_t = 27 - (raw - 0.706) / 0.001721
    except Exception:
        cpu_t = 0.0
    try:
        wlan = network.WLAN(network.STA_IF)
        rssi = wlan.status('rssi')
    except Exception:
        rssi = -60
    gc.collect()
    free_ram = gc.mem_free() // 1024
    up_sec = time.ticks_diff(time.ticks_ms(), start_time) // 1000
    if up_sec < 60: up_str = f"{up_sec} sn"
    elif up_sec < 3600: up_str = f"{up_sec // 60} dk {up_sec % 60} sn"
    else: up_str = f"{up_sec // 3600} sa {(up_sec % 3600) // 60} dk"
    return {
        "cpu_temp": round(cpu_t, 1),
        "rssi": rssi,
        "free_ram_kb": free_ram,
        "uptime_str": up_str,
        "uptime_sec": up_sec
    }
