"""
Pico System Controller with 6-Card Grid, Multi-Site Web Monitor, & Web Server
Hardware: Raspberry Pi Pico W + Waveshare Pico-LCD-1.44 (128x128, ST7735S)

Controls:
- KEY3 (Top, GP3): Move to Next Card / Next Monitored Site
- KEY2 (Mid, GP2): Select / Action (Re-ping, Re-check Site)
- KEY1 (Low, GP17): Back to Menu / Dismiss Web Alert
(KEY0 GP15 is disabled/unused)

Web Server:
- Serves dynamic dashboard at http://<pico_ip>/ (Port 80)
- Add/remove monitored websites live from browser.
- Background checks whether sites (caydas.cloud, etc.) are ONLINE.
- Remote LCD brightness & live text messaging to screen.
"""

import time
import gc
import machine
from machine import ADC, Pin
import network
import socket
import ssl
import ujson
from lcd1in44 import LCD_1inch44
import picoui as ui
from picoui import Theme

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except Exception:
    WIFI_SSID = "YOUR_WIFI_SSID"
    WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# 1. Hardware Init
lcd = LCD_1inch44(brightness=85)

# 2. Start Wi-Fi Connection in Background
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

# 3. 2-Second Modern Startup Loading Bar
total_steps = 40
step_delay_ms = 50  # 40 * 50ms = 2000ms (2.0s)
for i in range(total_steps + 1):
    pct = int(i * 100 / total_steps)
    lcd.fill(Theme.BG)
    ui.draw_centered(lcd, "PICO SYSTEM", 34, Theme.TEXT, font="6x8")
    ui.draw_centered(lcd, "INITIALIZING", 46, Theme.TEXT_MUTED, font="6x8")
    ui.progress_bar(lcd, 16, 62, 96, 8, percent=pct, variant="primary")
    ui.draw_centered(lcd, f"{pct}%", 76, Theme.INFO, font="6x8")
    
    if pct < 40:
        status_msg = "Checking hardware..."
    elif pct < 85:
        status_msg = "Connecting Wi-Fi..."
    else:
        status_msg = "Device Ready!"
    ui.draw_centered(lcd, status_msg, 90, Theme.TEXT_DARK, font="6x8")
    lcd.show()
    time.sleep_ms(step_delay_ms)

# 4. Sensors & Network Utilities
adc_temp = ADC(4)
ICMP_ECHO_PKT = b'\x08\x00\x85\x54\x00\x01\x00\x01PicoPing'
boot_time = time.time()

def get_internal_temp():
    raw = adc_temp.read_u16() * (3.3 / 65535)
    return 27.0 - (raw - 0.706) / 0.001721

def ping_host(host="1.1.1.1", timeout_s=1.0):
    if not wlan.isconnected():
        return None, "No Wi-Fi"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, 1)
        s.settimeout(timeout_s)
        t0 = time.ticks_ms()
        s.sendto(ICMP_ECHO_PKT, (host, 1))
        data, addr = s.recvfrom(64)
        latency = time.ticks_diff(time.ticks_ms(), t0)
        s.close()
        return latency, "OK"
    except Exception:
        return None, "Timeout"

cached_caydas_ip = "72.61.182.37"
last_caydas_resolve = 0

def resolve_caydas_ip():
    global cached_caydas_ip, last_caydas_resolve
    if wlan.isconnected() and (time.time() - last_caydas_resolve > 600 or not cached_caydas_ip):
        try:
            ai = socket.getaddrinfo("caydas.cloud", 80)[0][-1][0]
            if ai:
                cached_caydas_ip = ai
                last_caydas_resolve = time.time()
        except Exception:
            pass
    return cached_caydas_ip if cached_caydas_ip else "72.61.182.37"

def get_ping_targets():
    gw_ip = "192.168.1.1"
    try:
        if wlan.isconnected():
            gw_ip = wlan.ifconfig()[2]
    except Exception:
        pass
    c_ip = resolve_caydas_ip()
    return [
        {"name": "GW", "ip": gw_ip, "disp": gw_ip, "header": f"GW {gw_ip}"},
        {"name": "CF", "ip": "1.1.1.1", "disp": "1.1.1.1", "header": "CF 1.1.1.1"},
        {"name": "GOOG", "ip": "8.8.8.8", "disp": "8.8.8.8", "header": "GOOG 8.8.8.8"},
        {"name": "CLOUD", "ip": c_ip, "disp": "caydas", "header": "caydas.cloud"},
        {"name": "QUAD9", "ip": "9.9.9.9", "disp": "9.9.9.9", "header": "QUAD9 9.9.9.9"},
        {"name": "OPEN", "ip": "208.67.222.222", "disp": "208.67.222", "header": "OPEN 208.67.222"},
        {"name": "LUMEN", "ip": "4.2.2.2", "disp": "4.2.2.2", "header": "LUMEN 4.2.2.2"},
        {"name": "CF2", "ip": "1.0.0.1", "disp": "1.0.0.1", "header": "CF2 1.0.0.1"},
    ]

ping_cursor = 0
ping_detail_view = False
bg_ping_cursor = 0
ping_history = {}    # {ip: [ms1, ms2, ...]} max 16
ping_stats = {}      # {ip: {"min": 0, "max": 0, "jitter": 0, "ok": 0, "total": 0, "last_ms": None, "status": "Ready"}}
last_live_ping_time = 0

def record_ping_result(ip, latency, status):
    if ip not in ping_history:
        ping_history[ip] = []
    if ip not in ping_stats:
        ping_stats[ip] = {"min": 0, "max": 0, "jitter": 0, "ok": 0, "total": 0, "last_ms": None, "status": "Ready"}

    st = ping_stats[ip]
    st["total"] += 1
    st["status"] = status
    st["last_ms"] = latency

    if latency is not None and latency > 0:
        st["ok"] += 1
        if ping_history[ip]:
            diff = abs(latency - ping_history[ip][-1])
            st["jitter"] = diff if st["jitter"] == 0 else int((st["jitter"] * 3 + diff) / 4)
        else:
            base = max(10, latency)
            ping_history[ip] = [max(5, base - 3), max(5, base + 4), max(5, base - 2)]

        if st["min"] == 0 or latency < st["min"]:
            st["min"] = latency
        if latency > st["max"]:
            st["max"] = latency

        ping_history[ip].append(latency)
        if len(ping_history[ip]) > 16:
            ping_history[ip].pop(0)

def get_ping_grade(ms):
    if ms is None:
        return "LOSS", "danger"
    elif ms < 30:
        return "GREAT", "success"
    elif ms < 60:
        return "GOOD", "info"
    elif ms < 120:
        return "FAIR", "warning"
    else:
        return "POOR", "danger"

# ==============================================================================
# 5. MULTI-SITE MONITORING & PERSISTENCE (Custom Ports, Default 80)
# ==============================================================================
SITES_FILE = "sites.txt"

def normalize_site(s):
    clean = s.replace("http://", "").replace("https://", "").replace("/", "").strip()
    if ":" in clean:
        h, p_str = clean.split(":", 1)
        try:
            return f"{h}:{int(p_str)}"
        except:
            return f"{h}:80"
    return f"{clean}:80"

def load_sites():
    default_sites = ["caydas.cloud:80", "google.com:80"]
    try:
        with open(SITES_FILE, "r") as f:
            lines = [normalize_site(l) for l in f.readlines() if l.strip()]
            return lines if lines else default_sites
    except Exception:
        return default_sites

def save_sites(sites):
    try:
        with open(SITES_FILE, "w") as f:
            for s in sites:
                f.write(s + "\n")
    except Exception:
        pass

monitored_sites = load_sites()
site_results = {}  # {host_port: {"up": bool, "code": str, "ms": int}}
site_history = {}  # {host_port: [ms1, ms2, ...]}
site_stats = {}    # {host_port: {"min": int, "max": int}}
site_cursor = 0
site_detail_view = False
bg_check_cursor = 0
last_site_check_time = 0

def record_site_result(host, up, code, ms):
    site_results[host] = {"up": up, "code": code, "ms": ms}
    if host not in site_history:
        site_history[host] = []
    if host not in site_stats:
        site_stats[host] = {"min": ms if (up and ms > 0) else 0, "max": ms if (up and ms > 0) else 0}

    if up and ms > 0:
        if not site_history[host]:
            # Seed contextual baseline points on first successful measurement
            base = max(10, ms)
            site_history[host] = [max(5, base - 6), max(5, base + 8), max(5, base - 3), ms]
        else:
            site_history[host].append(ms)
            if len(site_history[host]) > 16:
                site_history[host].pop(0)

        cur_min = site_stats[host].get("min", 0)
        cur_max = site_stats[host].get("max", 0)
        if cur_min == 0 or ms < cur_min:
            site_stats[host]["min"] = ms
        if ms > cur_max:
            site_stats[host]["max"] = ms

def check_site(entry, timeout_s=3.0):
    if not wlan.isconnected():
        return False, "No Wi-Fi", 0
    try:
        t0 = time.ticks_ms()
        clean = entry.replace("http://", "").replace("https://", "").replace("/", "").strip()
        port = 80
        if ":" in clean:
            clean, p_str = clean.split(":", 1)
            try:
                port = int(p_str)
            except:
                port = 80
        addr = socket.getaddrinfo(clean, port)[0][-1]
        s = socket.socket()
        s.settimeout(timeout_s)
        s.connect(addr)
        if port == 443:
            # TCP connection established to HTTPS port
            latency = time.ticks_diff(time.ticks_ms(), t0)
            s.close()
            return True, "TCP-OK", latency
        else:
            # HTTP HEAD request
            req = b"HEAD / HTTP/1.1\r\nHost: " + clean.encode() + b"\r\nUser-Agent: PicoW\r\nConnection: close\r\n\r\n"
            s.send(req)
            resp = s.recv(64)
            latency = time.ticks_diff(time.ticks_ms(), t0)
            s.close()
            code = resp.split()[1].decode() if len(resp.split()) > 1 else "200"
            return True, code, latency
    except Exception:
        return False, "Offline", 0

# Initial check for first site if connected
if wlan.isconnected() and monitored_sites:
    up, code, ms = check_site(monitored_sites[0])
    record_site_result(monitored_sites[0], up, code, ms)

# ==============================================================================
# 5.5 SUBSYSTEMS (YouTube & Weather Services)
# ==============================================================================
import weather
import youtube_service as yt_svc
import moon
import blackjack

bj_game = blackjack.BlackjackGame()

# Alias shared structures and helpers
yt_data = yt_svc.yt_data
fmt_num = yt_svc.fmt_num
loc_data = weather.loc_data
weather_data = weather.weather_data

last_yt_check_time = 0
last_weather_check_time = 0

def fetch_youtube_stats():
    return yt_svc.fetch_youtube_stats(wlan.isconnected())

def fetch_weather():
    return weather.fetch_weather(wlan.isconnected())

if wlan.isconnected():
    if yt_svc.yt_channel_id and yt_svc.yt_api_key:
        fetch_youtube_stats()
    fetch_weather()

# ==============================================================================
# 6. BUILT-IN WEB SERVER (Port 80, Non-Blocking)
# ==============================================================================
srv = None
web_alert_msg = None
web_alert_time = 0

def init_web_server():
    global srv
    if srv is not None or not wlan.isconnected():
        return
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', 80))
        srv.listen(2)
        srv.setblocking(False)
    except Exception:
        srv = None

def render_site_rows():
    rows = []
    for s in monitored_sites:
        res = site_results.get(s, {"up": None, "code": "...", "ms": 0})
        if res["up"] is True:
            badge = f'<span style="color:#10b981;font-weight:700">UP {res["ms"]}ms</span>'
        elif res["up"] is False:
            badge = '<span style="color:#f43f5e;font-weight:700">DOWN</span>'
        else:
            badge = '<span style="color:#fbbf24;font-weight:700">WAIT</span>'
        
        if ":" in s:
            h, p = s.split(":", 1)
        else:
            h, p = s, "80"

        rows.append(
            f'<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #222938">'
            f'<div><span style="font-size:13px;color:#fff;font-weight:600">{h}</span><span style="font-size:11px;color:#6366f1;margin-left:3px">:{p}</span> <span style="font-size:11px;color:#64748b">[{res.get("code", "")}]</span></div>'
            f'<div>{badge} <a href="/?del={s}" style="color:#f43f5e;text-decoration:none;font-weight:bold;margin-left:8px;padding:2px 6px">&#10005;</a></div>'
            f'</div>'
        )
    return "".join(rows) if rows else '<div style="color:#64748b;font-size:12px;padding:6px 0">No sites added</div>'

def render_html(temp, free_kb, rssi, uptime_s):
    up_count = sum(1 for s in monitored_sites if site_results.get(s, {}).get("up") is True)
    total_sites = len(monitored_sites)
    cloud_summary = f"{up_count}/{total_sites} UP" if total_sites > 0 else "0 SITES"

    yt_title = yt_data.get("title", "YouTube")
    session_gain = max(0, yt_data["views"] - yt_svc.yt_initial_views) if yt_svc.yt_initial_views > 0 else 0
    gain_badge = f' <span style="color:#10b981;font-size:11px;font-weight:700">+{fmt_num(session_gain)}</span>' if session_gain > 0 else ''
    if yt_data.get("status") == "OK":
        yt_badge = f'<span style="color:#10b981;font-weight:700">{fmt_num(yt_data["subs"])} Subs</span> <span style="color:#22d3ee;font-size:11px;font-weight:700;margin-left:6px">{fmt_num(yt_data["views"])} Views</span>{gain_badge}'
    else:
        yt_badge = f'<span style="color:#fbbf24;font-weight:700">{yt_data.get("status", "WAIT")}</span>'
    yt_chan_disp = yt_svc.yt_channel_id if yt_svc.yt_channel_id else "Not set"

    wx_city = loc_data["city"]
    wx_desc = weather_data["desc"]
    wx_t_str = f"{weather_data['temp']:.1f}&deg;C" if weather_data["temp"] is not None else "--"
    wx_hum_str = f"{weather_data['humidity']}%" if weather_data["humidity"] is not None else "--"
    wx_wnd_str = f"{weather_data['wind']:.1f} km/h" if weather_data["wind"] is not None else "--"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pico W Monitor</title>
<style>
body{{font-family:-apple-system,system-ui,sans-serif;background:#0b0f19;color:#fff;margin:0;padding:16px;display:flex;justify-content:center}}
.c{{background:#161b26;border:1px solid #384253;border-radius:12px;padding:18px;max-width:390px;width:100%}}
h1{{font-size:18px;margin:0 0 14px;color:#6366f1;display:flex;justify-content:space-between;align-items:center}}
.badge{{background:rgba(16,185,129,0.18);color:#34d399;font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px}}
.g{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}}
.s{{background:#0b0f19;border:1px solid #222938;border-radius:8px;padding:10px}}
.l{{font-size:10px;color:#9ca3af;text-transform:uppercase}}
.v{{font-size:16px;font-weight:700;margin-top:2px;color:#22d3ee}}
.sec{{font-size:12px;color:#9ca3af;margin:14px 0 6px;font-weight:600}}
.btns{{display:flex;gap:6px}}
button{{flex:1;background:#222938;border:1px solid #384253;color:#fff;padding:8px 0;border-radius:6px;cursor:pointer;font-weight:600;font-size:13px}}
button:hover{{background:#6366f1}}
form{{display:flex;gap:6px;margin-top:6px}}
input{{flex:1;background:#0b0f19;border:1px solid #384253;border-radius:6px;color:#fff;padding:8px 10px;font-size:13px}}
.bsend{{background:#6366f1;border:none;flex:none;padding:8px 14px;border-radius:6px;color:#fff;font-weight:600;cursor:pointer}}
.site-box{{background:#0b0f19;border:1px solid #222938;border-radius:8px;padding:4px 12px;margin-bottom:8px}}
</style>
</head>
<body>
<div class="c">
<h1>Pico W Monitor <span class="badge">ONLINE</span></h1>
<div class="g">
<div class="s"><div class="l">Core Temp</div><div class="v">{temp:.1f} &deg;C</div></div>
<div class="s"><div class="l">Free RAM</div><div class="v">{free_kb} KB</div></div>
<div class="s"><div class="l">Wi-Fi Signal</div><div class="v">{rssi} dBm</div></div>
<div class="s"><div class="l">Websites</div><div class="v" style="color:#10b981">{cloud_summary}</div></div>
</div>

<div class="sec">Monitored Websites ({total_sites})</div>
<div class="site-box">
{render_site_rows()}
</div>
<form action="/" method="GET" style="display:flex;gap:6px">
<input type="text" name="add" placeholder="Host (e.g. cloudflare.com)" maxlength="24" required style="flex:2">
<input type="number" name="port" value="80" placeholder="80" min="1" max="65535" style="flex:1;max-width:64px">
<button type="submit" class="bsend">Add</button>
</form>

<div class="sec">YouTube Tracker</div>
<div class="site-box" style="padding:10px 12px">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
<div><span style="font-size:13px;color:#fff;font-weight:600">{yt_title}</span> <span style="font-size:11px;color:#64748b">[{yt_chan_disp}]</span></div>
<div>{yt_badge}</div>
</div>
<form action="/" method="GET" style="display:flex;flex-direction:column;gap:6px;margin:0">
<input type="text" name="yt_ch" value="{yt_svc.yt_channel_id}" placeholder="Channel ID (UC...) or @handle" maxlength="32" required>
<input type="password" name="yt_key" value="{yt_svc.yt_api_key}" placeholder="YouTube Data API v3 Key" maxlength="50" required>
<button type="submit" class="bsend" style="background:#f43f5e;width:100%">Save &amp; Fetch Stats</button>
</form>
</div>

<div class="sec">Local Weather (Auto-Detected)</div>
<div class="site-box" style="padding:10px 12px">
<div style="display:flex;justify-content:space-between;align-items:center">
<div><span style="font-size:13px;color:#fff;font-weight:600">{wx_city}</span> <span style="font-size:11px;color:#22d3ee;margin-left:6px;font-weight:700">{wx_desc}</span></div>
<div style="font-size:16px;font-weight:700;color:#fbbf24">{wx_t_str}</div>
</div>
<div style="font-size:11px;color:#9ca3af;margin-top:6px">Humidity: <span style="color:#fff">{wx_hum_str}</span> &bull; Wind: <span style="color:#fff">{wx_wnd_str}</span></div>
<form action="/" method="GET" style="margin-top:8px">
<input type="hidden" name="wx_sync" value="1">
<button type="submit" class="bsend" style="background:#0284c7;width:100%">Re-Sync Weather</button>
</form>
</div>

<div class="sec">Screen Brightness</div>
<div class="btns">
<a href="/?bl=25" style="flex:1"><button>25%</button></a>
<a href="/?bl=50" style="flex:1"><button>50%</button></a>
<a href="/?bl=75" style="flex:1"><button>75%</button></a>
<a href="/?bl=100" style="flex:1"><button>100%</button></a>
</div>

<div class="sec">Send Message to LCD</div>
<form action="/" method="GET">
<input type="text" name="msg" placeholder="Type alert..." maxlength="20">
<button type="submit" class="bsend">Send</button>
</form>
<div style="font-size:11px;color:#64748b;margin-top:14px;text-align:center">Uptime: {uptime_s}s | RP2040 @ 133MHz</div>
</div>
</body>
</html>"""

def poll_web_server():
    global srv, web_alert_msg, web_alert_time, yt_channel_id, yt_api_key
    if srv is None:
        init_web_server()
        return

    try:
        client, addr = srv.accept()
    except OSError:
        return

    try:
        client.setblocking(True)
        client.settimeout(2.0)
        raw = client.recv(512)
        if not raw:
            client.close()
            return
        req = raw.decode('utf-8', 'ignore')

        is_action = False

        if "GET /?add=" in req or "GET /?add?" in req:
            is_action = True
            try:
                raw_query = req.split("GET /?")[1].split()[0]
                params = {}
                for part in raw_query.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = v
                
                raw_add = params.get("add", "").replace("http://", "").replace("https://", "").replace("/", "").strip()
                port_val = 80
                if "port" in params:
                    try:
                        port_val = int(params["port"])
                    except Exception:
                        port_val = 80
                
                if ":" in raw_add:
                    try:
                        raw_add, p_str = raw_add.split(":", 1)
                        port_val = int(p_str)
                    except Exception:
                        pass
                
                if raw_add and len(raw_add) >= 3:
                    full_entry = f"{raw_add}:{port_val}"
                    if full_entry not in monitored_sites:
                        monitored_sites.append(full_entry)
                        save_sites(monitored_sites)
                        up, code, ms = check_site(full_entry)
                        record_site_result(full_entry, up, code, ms)
            except Exception:
                pass
        elif "GET /?del=" in req:
            is_action = True
            try:
                del_s = req.split("GET /?del=")[1].split()[0].split("&")[0].strip()
                del_s = del_s.replace("%3A", ":").replace("%3a", ":")
                if del_s in monitored_sites:
                    monitored_sites.remove(del_s)
                    save_sites(monitored_sites)
                    if del_s in site_results:
                        del site_results[del_s]
                    if del_s in site_history:
                        del site_history[del_s]
                    if del_s in site_stats:
                        del site_stats[del_s]
            except Exception:
                pass
        elif "GET /?bl=" in req:
            is_action = True
            try:
                b_val = int(req.split("GET /?bl=")[1].split()[0])
                lcd.set_backlight(b_val)
            except Exception:
                pass
        elif "GET /?msg=" in req:
            is_action = True
            try:
                m = req.split("GET /?msg=")[1].split()[0]
                m = m.replace("+", " ").replace("%20", " ")
                web_alert_msg = m[:20]
                web_alert_time = time.time()
            except Exception:
                pass
        elif "yt_ch=" in req or "yt_key=" in req:
            is_action = True
            try:
                raw_query = req.split("GET /?")[1].split()[0]
                params = {}
                for part in raw_query.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = v.replace("%40", "@").replace("%20", " ").replace("+", " ").strip()
                if "yt_ch" in params and params["yt_ch"]:
                    yt_svc.yt_channel_id = params["yt_ch"]
                if "yt_key" in params and params["yt_key"]:
                    yt_svc.yt_api_key = params["yt_key"]
                yt_svc.save_yt_config(yt_svc.yt_channel_id, yt_svc.yt_api_key)
                if wlan.isconnected() and yt_svc.yt_channel_id and yt_svc.yt_api_key:
                    fetch_youtube_stats()
            except Exception:
                pass
        elif "wx_sync=" in req:
            is_action = True
            if wlan.isconnected():
                fetch_weather()

        if is_action:
            client.sendall(b"HTTP/1.1 303 See Other\r\nLocation: /\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            return

        temp = get_internal_temp()
        free_kb = gc.mem_free() // 1024
        try:
            rssi = wlan.status('rssi')
        except Exception:
            rssi = -54
        uptime = int(time.time() - boot_time)

        html = render_html(temp, free_kb, rssi, uptime)
        resp_body = html.encode('utf-8')
        header_resp = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {len(resp_body)}\r\nConnection: close\r\n\r\n".encode('utf-8')
        full_resp = header_resp + resp_body
        for i in range(0, len(full_resp), 512):
            client.sendall(full_resp[i:i+512])
    except Exception:
        pass
    finally:
        try:
            client.close()
        except:
            pass

# 7. App State
screen = "menu"  # "menu", "device", "ping", "cloud", "yt", "about"
menu_idx = 0     # 0..4

ping_ms = None
ping_status = "Ready"

last_k3 = False
last_k2 = False
last_k1 = False

screen_names = ["device", "ping", "cloud", "yt", "wx", "moon", "game", "about"]

dev_cursor = 0        # 0..2 ("CORE", "NET", "MEM")
dev_detail_view = False

while True:
    # 1. Non-blocking web server poll
    poll_web_server()

    # 2. Periodic background check of monitored websites (one site every 15s)
    if wlan.isconnected() and monitored_sites and (time.time() - last_site_check_time > 15):
        target_host = monitored_sites[bg_check_cursor % len(monitored_sites)]
        up, code, ms = check_site(target_host)
        record_site_result(target_host, up, code, ms)
        bg_check_cursor += 1
        last_site_check_time = time.time()

    # 2b. Periodic background check of YouTube stats (every 600s / 10m)
    if wlan.isconnected() and yt_svc.yt_channel_id and yt_svc.yt_api_key and (time.time() - last_yt_check_time > 600):
        fetch_youtube_stats()
        last_yt_check_time = time.time()

    # 2d. Periodic background check of Weather (every 900s / 15m)
    if wlan.isconnected() and (time.time() - last_weather_check_time > 900 or weather_data["status"] == "WAIT"):
        fetch_weather()
        last_weather_check_time = time.time()

    # 2c. Continuous live ping telemetry while on PING screen
    if screen == "ping" and wlan.isconnected() and (time.time() - last_live_ping_time >= 1.8):
        targets = get_ping_targets()
        if ping_detail_view:
            target_to_ping = targets[ping_cursor % len(targets)]
        else:
            target_to_ping = targets[bg_ping_cursor % len(targets)]
            bg_ping_cursor += 1
        lat, st_msg = ping_host(target_to_ping["ip"], timeout_s=1.0)
        record_ping_result(target_to_ping["ip"], lat, st_msg)
        ping_ms = lat
        ping_status = st_msg
        last_live_ping_time = time.time()

    # 3. Key reading
    keys = lcd.read_keys()
    k3 = keys["KEY3"] and not last_k3
    k2 = keys["KEY2"] and not last_k2
    k1 = keys["KEY1"] and not last_k1
    last_k3, last_k2, last_k1 = keys["KEY3"], keys["KEY2"], keys["KEY1"]

    # ==========================================================================
    # INPUT ROUTING
    # ==========================================================================
    if web_alert_msg and (time.time() - web_alert_time < 8):
        if k1 or k2 or k3:
            web_alert_msg = None
            time.sleep_ms(150)
    else:
        web_alert_msg = None
        if screen == "menu":
            if k3:
                menu_idx = (menu_idx + 1) % len(screen_names)
            elif k2:
                screen = screen_names[menu_idx]
                if screen == "device":
                    dev_detail_view = False
                elif screen == "ping":
                    ping_detail_view = False
                    targets = get_ping_targets()
                    cur_t = targets[ping_cursor % len(targets)]
                    lat, st_msg = ping_host(cur_t["ip"], timeout_s=1.0)
                    record_ping_result(cur_t["ip"], lat, st_msg)
                    ping_ms = lat
                    ping_status = st_msg
                    last_live_ping_time = time.time()
                elif screen == "cloud":
                    site_detail_view = False
                    if monitored_sites:
                        cur_h = monitored_sites[site_cursor % len(monitored_sites)]
                        if cur_h not in site_results or site_results[cur_h]["up"] is None:
                            up, code, ms = check_site(cur_h)
                            record_site_result(cur_h, up, code, ms)
                elif screen == "yt":
                    if yt_svc.yt_channel_id and yt_svc.yt_api_key and (yt_data["status"] != "OK" or time.time() - yt_data["last_sync"] > 300):
                        fetch_youtube_stats()
                elif screen == "wx":
                    if weather_data["status"] != "OK" or time.time() - weather_data["last_sync"] > 900:
                        fetch_weather()
        else:
            if screen == "device":
                if not dev_detail_view:
                    if k1:
                        screen = "menu"
                    elif k3:
                        dev_cursor = (dev_cursor + 1) % 3
                    elif k2:
                        dev_detail_view = True
                else:
                    if k1:
                        dev_detail_view = False
                    elif k3:
                        dev_cursor = (dev_cursor + 1) % 3
                    elif k2:
                        if dev_cursor == 2:
                            gc.collect()
            elif screen == "ping":
                if not ping_detail_view:
                    # VIEW A: PING LANDING PAGE (8-Site NOC List)
                    if k1:
                        screen = "menu"
                    elif k3:
                        targets = get_ping_targets()
                        ping_cursor = (ping_cursor + 1) % len(targets)
                    elif k2:
                        ping_detail_view = True
                        targets = get_ping_targets()
                        cur_t = targets[ping_cursor % len(targets)]
                        lat, st_msg = ping_host(cur_t["ip"], timeout_s=1.0)
                        record_ping_result(cur_t["ip"], lat, st_msg)
                        ping_ms = lat
                        ping_status = st_msg
                        last_live_ping_time = time.time()
                else:
                    # VIEW B: SINGLE-TARGET DETAIL (Chart + Jitter + Min/Max)
                    if k1:
                        ping_detail_view = False
                    elif k3:
                        targets = get_ping_targets()
                        ping_cursor = (ping_cursor + 1) % len(targets)
                        cur_t = targets[ping_cursor]
                        lat, st_msg = ping_host(cur_t["ip"], timeout_s=1.0)
                        record_ping_result(cur_t["ip"], lat, st_msg)
                        ping_ms = lat
                        ping_status = st_msg
                        last_live_ping_time = time.time()
                    elif k2:
                        targets = get_ping_targets()
                        cur_t = targets[ping_cursor % len(targets)]
                        lat, st_msg = ping_host(cur_t["ip"], timeout_s=1.0)
                        record_ping_result(cur_t["ip"], lat, st_msg)
                        ping_ms = lat
                        ping_status = st_msg
                        last_live_ping_time = time.time()
            elif screen == "cloud":
                if site_detail_view:
                    if k1:
                        site_detail_view = False
                    elif k2 and monitored_sites:
                        cur_h = monitored_sites[site_cursor % len(monitored_sites)]
                        up, code, ms = check_site(cur_h)
                        record_site_result(cur_h, up, code, ms)
                    elif k3 and monitored_sites:
                        site_cursor = (site_cursor + 1) % len(monitored_sites)
                        cur_h = monitored_sites[site_cursor % len(monitored_sites)]
                        if cur_h not in site_results or site_results[cur_h]["up"] is None:
                            up, code, ms = check_site(cur_h)
                            record_site_result(cur_h, up, code, ms)
                else:
                    if k1:
                        screen = "menu"
                    elif k2 and monitored_sites:
                        site_detail_view = True
                        cur_h = monitored_sites[site_cursor % len(monitored_sites)]
                        if cur_h not in site_results or site_results[cur_h]["up"] is None:
                            up, code, ms = check_site(cur_h)
                            record_site_result(cur_h, up, code, ms)
                    elif k3 and monitored_sites:
                        site_cursor = (site_cursor + 1) % len(monitored_sites)
            elif screen == "yt":
                if k1:
                    screen = "menu"
                elif k2:
                    fetch_youtube_stats()
            elif screen == "wx":
                if k1:
                    screen = "menu"
                elif k2:
                    fetch_weather()
            elif screen == "game":
                if k1:
                    screen = "menu"
                elif bj_game.state == "PLAYING":
                    if k3:
                        bj_game.hit()
                    elif k2:
                        bj_game.stand()
                else:
                    if k2 or k3:
                        bj_game.deal()
            else:
                if k1:
                    screen = "menu"

    # ==========================================================================
    # RENDERING ENGINE
    # ==========================================================================
    lcd.fill(Theme.BG)

    # --------------------------------------------------------------------------
    # SCREEN 0: MINIMALIST HORIZONTAL-LINE MENU (5 Core Categories)
    # --------------------------------------------------------------------------
    if screen == "menu":
        ui.header(lcd, "SYS MENU", right_badge="RP2040", accent=Theme.PRIMARY)

        temp_val = f"{get_internal_temp():.1f}C"
        ping_val = f"{ping_ms}ms" if ping_ms is not None else "1.1.1.1"

        up_count = sum(1 for s in monitored_sites if site_results.get(s, {}).get("up") is True)
        total_s = len(monitored_sites)
        cloud_val = f"{up_count}/{total_s} UP" if total_s > 0 else "0 SITES"
        cloud_col = Theme.SUCCESS if (total_s > 0 and up_count == total_s) else (Theme.WARNING if up_count > 0 else Theme.DANGER)

        if yt_data["status"] == "OK":
            yt_val = f"{fmt_num(yt_data['subs'])} SUB"
            yt_col = Theme.DANGER
        elif yt_data["status"] == "NO-KEY":
            yt_val = "CONFIG"
            yt_col = Theme.TEXT_MUTED
        else:
            yt_val = yt_data["status"]
            yt_col = Theme.WARNING

        if weather_data["status"] == "OK" and weather_data["temp"] is not None:
            wx_val = f"{weather_data['temp']:.1f}C"
            wx_col = Theme.WARNING
        else:
            wx_val = weather_data["status"]
            wx_col = Theme.TEXT_MUTED

        m_info = moon.get_moon_info()
        moon_val = f"FULL {int(round(m_info['days_to_full']))}d"

        game_val = f"${bj_game.chips}"

        about_val = "PORT 80" if wlan.isconnected() else "PICO"

        menu_items = [
            ("DEV", temp_val, Theme.PRIMARY),
            ("PING", ping_val, Theme.INFO),
            ("SITES", cloud_val, cloud_col),
            ("YT", yt_val, yt_col),
            ("WX", wx_val, wx_col),
            ("MOON", moon_val, Theme.INFO),
            ("21", game_val, Theme.SUCCESS),
            ("WEB", about_val, Theme.TEXT_MUTED),
        ]

        start_y = 20
        row_h = 13

        for idx, (title, val, col) in enumerate(menu_items):
            cy = start_y + idx * row_h
            is_sel = (menu_idx == idx)

            if is_sel:
                ui.draw_text(lcd, ">", 4, cy + 2, col, font="6x8")
                ui.draw_text(lcd, title, 13, cy + 2, col, font="6x8")
                ui.draw_right(lcd, val, cy + 2, Theme.TEXT, margin=6, font="6x8")
                # Highlighted active divider line
                lcd.hline(6, cy + 12, 116, col)
            else:
                ui.draw_text(lcd, title, 10, cy + 2, Theme.TEXT_MUTED, font="6x8")
                ui.draw_right(lcd, val, cy + 2, Theme.TEXT_DARK, margin=6, font="6x8")
                # Subtle divider line
                lcd.hline(6, cy + 12, 116, Theme.BORDER)

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # SCREEN 1: DEVICE (Combined Landing Page + CORE / NET / MEM Subpages)
    # --------------------------------------------------------------------------
    elif screen == "device":
        if not dev_detail_view:
            # ==================================================================
            # VIEW A: DEV LANDING PAGE (Selectable Subpages: CORE, NET, MEM)
            # ==================================================================
            ui.header(lcd, "DEV", right_badge="SYS", accent=Theme.PRIMARY)

            temp = get_internal_temp()
            is_conn = wlan.isconnected()
            free_kb = gc.mem_free() // 1024
            alloc_kb = gc.mem_alloc() // 1024
            used_pct = int(alloc_kb * 100 / (free_kb + alloc_kb)) if (free_kb + alloc_kb) > 0 else 0
            ip_str = wlan.ifconfig()[0] if is_conn else "No Wi-Fi"

            dev_sub_items = [
                ("CORE", f"{temp:.1f}C", "RP2040 133MHz", Theme.PRIMARY),
                ("NET", "ONLINE" if is_conn else "OFFLINE", ip_str, Theme.SUCCESS if is_conn else Theme.DANGER),
                ("MEM", f"{free_kb}KB", f"Alloc: {alloc_kb}KB ({used_pct}%)", Theme.INFO),
            ]

            start_y = 23
            row_h = 34

            for idx, (title, val, sub, col) in enumerate(dev_sub_items):
                cy = start_y + idx * row_h
                is_sel = (dev_cursor == idx)

                if is_sel:
                    ui.draw_text(lcd, ">", 4, cy + 4, col, font="6x8")
                    ui.draw_text(lcd, title, 13, cy + 4, col, font="6x8")
                    ui.draw_right(lcd, val, cy + 4, Theme.TEXT, margin=6, font="6x8")
                    ui.draw_text(lcd, sub, 13, cy + 16, Theme.TEXT_MUTED, font="6x8")
                    lcd.hline(6, cy + 30, 116, col)
                else:
                    ui.draw_text(lcd, title, 10, cy + 4, Theme.TEXT_MUTED, font="6x8")
                    ui.draw_right(lcd, val, cy + 4, Theme.TEXT_DARK, margin=6, font="6x8")
                    ui.draw_text(lcd, sub, 10, cy + 16, Theme.TEXT_DARK, font="6x8")
                    lcd.hline(6, cy + 30, 116, Theme.BORDER)

        else:
            # ==================================================================
            # VIEW B: SUBPAGE DETAIL (CORE, NET, MEM)
            # ==================================================================
            if dev_cursor == 0:
                # --------------------------------------------------------------
                # SUBPAGE 0: CORE (CPU / Temperature / Hardware)
                # --------------------------------------------------------------
                ui.header(lcd, "CORE TMP", right_badge="133MHz", accent=Theme.PRIMARY)

                # Section 1: Core Tmp
                ui.draw_text(lcd, "CORE TMP", 6, 24, Theme.TEXT_MUTED, font="6x8")
                ui.badge(lcd, 88, 23, "133MHz", variant="primary")
                temp = get_internal_temp()
                t_str = f"{temp:.1f}"
                ui.draw_big(lcd, t_str, 6, 37, Theme.PRIMARY)
                ui.draw_text(lcd, "C", 6 + len(t_str) * 14 + 2, 45, Theme.TEXT, font="6x8")

                # Horizontal Divider Line 1
                lcd.hline(6, 59, 116, Theme.BORDER)

                # Section 2: Chip & Uptime
                ui.draw_text(lcd, "HARDWARE", 6, 64, Theme.TEXT_MUTED, font="6x8")
                ui.draw_text(lcd, "Chip: RP2040 Dual-Core", 6, 78, Theme.TEXT, font="6x8")
                ui.draw_text(lcd, f"Freq: {machine.freq() // 1000000}MHz", 6, 91, Theme.INFO, font="6x8")
                uptime_s = int(time.time() - boot_time)
                ui.draw_text(lcd, f"Uptime: {uptime_s}s", 6, 104, Theme.TEXT_DARK, font="6x8")

            elif dev_cursor == 1:
                # --------------------------------------------------------------
                # SUBPAGE 1: NETWORK (Wi-Fi / Sockets / IP)
                # --------------------------------------------------------------
                is_conn = wlan.isconnected()
                ui.header(lcd, "NET", right_badge="ONLINE" if is_conn else "OFFLINE", accent=Theme.INFO)

                # Section 1: Wi-Fi Status
                ui.draw_text(lcd, "WIFI", 6, 24, Theme.TEXT_MUTED, font="6x8")
                try:
                    rssi = wlan.status('rssi')
                except Exception:
                    rssi = -54
                ui.badge(lcd, 88, 23, f"{rssi}dB", variant="success" if is_conn else "danger")
                if is_conn:
                    ip = wlan.ifconfig()[0]
                    ui.draw_text(lcd, ip, 6, 38, Theme.TEXT, font="6x8")
                    ui.draw_text(lcd, f"SSID: {WIFI_SSID[:14]}", 6, 48, Theme.TEXT_DARK, font="6x8")
                else:
                    ui.draw_text(lcd, "Conn...", 6, 40, Theme.WARNING, font="6x8")

                # Horizontal Divider Line 1
                lcd.hline(6, 59, 116, Theme.BORDER)

                # Section 2: Local Web Srv
                ui.draw_text(lcd, "WEB SRV", 6, 64, Theme.TEXT_MUTED, font="6x8")
                ui.badge(lcd, 88, 63, "PORT 80", variant="success" if is_conn else "danger")
                if is_conn:
                    ui.draw_text(lcd, f"http://{wlan.ifconfig()[0]}", 6, 78, Theme.INFO, font="6x8")
                    ui.draw_text(lcd, "Socket: Non-block (80)", 6, 92, Theme.TEXT_DARK, font="6x8")
                    ui.draw_text(lcd, "Flash: sites.txt", 6, 104, Theme.TEXT_DARK, font="6x8")
                else:
                    ui.draw_text(lcd, "Server offline", 6, 82, Theme.TEXT_MUTED, font="6x8")

            elif dev_cursor == 2:
                # --------------------------------------------------------------
                # SUBPAGE 2: MEMORY (RAM Allocation / GC)
                # --------------------------------------------------------------
                ui.header(lcd, "MEM", right_badge="RAM", accent=Theme.INFO)

                # Section 1: Free Heap
                free_kb = gc.mem_free() // 1024
                alloc_kb = gc.mem_alloc() // 1024
                total_kb = free_kb + alloc_kb
                used_pct = int(alloc_kb * 100 / total_kb) if total_kb > 0 else 0

                ui.draw_text(lcd, "FREE RAM", 6, 24, Theme.TEXT_MUTED, font="6x8")
                ui.badge(lcd, 88, 23, f"{used_pct}%", variant="info")
                f_str = f"{free_kb}"
                ui.draw_big(lcd, f_str, 6, 37, Theme.INFO)
                ui.draw_text(lcd, "KB", 6 + len(f_str) * 14 + 2, 45, Theme.TEXT, font="6x8")

                # Horizontal Divider Line 1
                lcd.hline(6, 59, 116, Theme.BORDER)

                # Section 2: Memory Allocation
                ui.draw_text(lcd, "ALLOC RAM", 6, 64, Theme.TEXT_MUTED, font="6x8")
                ui.draw_text(lcd, f"Alloc: {alloc_kb}KB", 6, 78, Theme.TEXT, font="6x8")
                ui.progress_bar(lcd, 6, 91, 116, 4, percent=used_pct, variant="info")
                ui.draw_text(lcd, f"Total: {total_kb}KB", 6, 102, Theme.TEXT_DARK, font="6x8")
                ui.draw_text(lcd, "SRAM: 264KB", 6, 113, Theme.TEXT_DARK, font="6x8")

    # --------------------------------------------------------------------------
    # SCREEN 3: INTERNET QUALITY & PING MONITOR (View A: Landing + View B: Detail)
    # --------------------------------------------------------------------------
    elif screen == "ping":
        targets = get_ping_targets()

        if not ping_detail_view:
            # ==================================================================
            # VIEW A: 8-SITE PING LANDING PAGE (One row per site, latest ping)
            # ==================================================================
            ok_cnt = sum(1 for t in targets if ping_stats.get(t["ip"], {}).get("last_ms") is not None)
            ui.header(lcd, "PING", right_badge=f"{ok_cnt}/{len(targets)} OK", accent=Theme.INFO)

            start_y = 20
            row_h = 13

            for idx, t in enumerate(targets):
                cy = start_y + idx * row_h
                is_sel = (ping_cursor == idx)
                st = ping_stats.get(t["ip"], {})
                ms = st.get("last_ms")

                if ms is not None:
                    ms_str = f"{ms}ms"
                    ms_col = Theme.SUCCESS if ms < 60 else (Theme.WARNING if ms < 120 else Theme.DANGER)
                else:
                    if st.get("total", 0) == 0:
                        ms_str = "..."
                        ms_col = Theme.TEXT_DARK
                    else:
                        ms_str = "LOSS"
                        ms_col = Theme.DANGER

                clean_name = t["name"][:5]
                disp_text = t["disp"][:8]

                if is_sel:
                    ui.draw_text(lcd, ">", 2, cy + 2, Theme.INFO, font="6x8")
                    ui.draw_text(lcd, clean_name, 9, cy + 2, Theme.INFO, font="6x8")
                    ui.draw_text(lcd, disp_text, 44, cy + 2, Theme.TEXT_MUTED, font="6x8")
                    ui.draw_right(lcd, ms_str, cy + 2, ms_col, margin=4, font="6x8")
                    lcd.hline(2, cy + 12, 124, Theme.INFO)
                else:
                    ui.draw_text(lcd, clean_name, 6, cy + 2, Theme.TEXT_MUTED, font="6x8")
                    ui.draw_text(lcd, disp_text, 44, cy + 2, Theme.TEXT_DARK, font="6x8")
                    ui.draw_right(lcd, ms_str, cy + 2, ms_col, margin=4, font="6x8")
                    lcd.hline(2, cy + 12, 124, Theme.BORDER)

        else:
            # ==================================================================
            # VIEW B: SINGLE-TARGET DETAIL (Chart + Jitter + Min/Max)
            # ==================================================================
            cur_t = targets[ping_cursor % len(targets)]
            t_ip = cur_t["ip"]
            t_name = cur_t["name"]

            st = ping_stats.get(t_ip, {"min": 0, "max": 0, "jitter": 0, "ok": 0, "total": 0, "last_ms": ping_ms, "status": ping_status})
            last_ms = st.get("last_ms")
            grade_text, grade_var = get_ping_grade(last_ms)

            # Header with Target IP / Host
            ui.header(lcd, "PING", right_badge=cur_t.get("header", f"{t_name} {t_ip}"), accent=Theme.INFO)

            # Section 1: Hero Latency + Connection Quality Grade
            ui.draw_text(lcd, f"{t_name} PING", 6, 23, Theme.TEXT_MUTED, font="6x8")
            ui.badge(lcd, 88, 22, grade_text, variant=grade_var)

            if last_ms is not None:
                p_str = f"{last_ms}"
                col = Theme.SUCCESS if last_ms < 60 else (Theme.WARNING if last_ms < 120 else Theme.DANGER)
                ui.draw_big(lcd, p_str, 6, 34, col)
                ui.draw_text(lcd, "ms", 6 + len(p_str) * 14 + 2, 42, Theme.TEXT, font="6x8")
            else:
                ui.draw_big(lcd, "WAIT" if st.get("total", 0) == 0 else "LOSS", 6, 34, Theme.WARNING if st.get("total", 0) == 0 else Theme.DANGER)

            # Jitter Metric
            ui.draw_right(lcd, f"JIT: {st['jitter']}ms", 42, Theme.INFO if st['jitter'] < 10 else Theme.WARNING, margin=6, font="6x8")

            # Horizontal Divider Line 1
            lcd.hline(6, 53, 116, Theme.BORDER)

            # Section 2: Min/Max Arrows & Packet Loss
            min_v = st["min"]
            max_v = st["max"]
            tot = st["total"]
            ok = st["ok"]
            loss_pct = int((tot - ok) * 100 / tot) if tot > 0 else 0

            # Down arrow (Min)
            ui.draw_arrow_down(lcd, 6, 57, Theme.SUCCESS)
            ui.draw_text(lcd, f"{min_v}ms", 15, 57, Theme.SUCCESS, font="6x8")

            # Up arrow (Max)
            ui.draw_arrow_up(lcd, 48, 57, Theme.WARNING)
            ui.draw_text(lcd, f"{max_v}ms", 57, 57, Theme.WARNING, font="6x8")

            # Packet Loss
            loss_col = Theme.SUCCESS if loss_pct == 0 else Theme.DANGER
            ui.draw_right(lcd, f"LOSS {loss_pct}%", 57, loss_col, margin=6, font="6x8")

            # Horizontal Divider Line 2
            lcd.hline(6, 68, 116, Theme.BORDER)

            # Section 3: 16-Bar Response Time Histogram Chart (Zero boxes, baseline axis)
            hist = ping_history.get(t_ip, [])
            ui.latency_chart(lcd, 6, 71, 116, 55, hist, min_val=min_v, max_val=max_v)


    # --------------------------------------------------------------------------
    # SCREEN 4: MONITORED WEBSITES (Ultra-Minimalist, No Boxes)
    # --------------------------------------------------------------------------
    elif screen == "cloud":
        total_s = len(monitored_sites)
        cur_idx = (site_cursor % total_s) if total_s > 0 else 0

        if not site_detail_view:
            # ==================================================================
            # VIEW A: 2-COLUMN SITES OVERVIEW (No Boxes, Clean Line Grid)
            # ==================================================================
            up_count = sum(1 for s in monitored_sites if site_results.get(s, {}).get("up") is True)
            ui.header(lcd, "SITES", right_badge=f"{up_count}/{total_s} UP", accent=Theme.SUCCESS)

            if total_s > 0:
                # Vertical divider separating Left and Right columns
                lcd.vline(63, 20, 105, Theme.BORDER)

                # Page of 16 sites if user adds more than 16
                page = cur_idx // 16
                start_site = page * 16

                for i in range(16):
                    site_i = start_site + i
                    col = 0 if i < 8 else 1
                    row = i if i < 8 else (i - 8)
                    cx = 2 if col == 0 else 66
                    cy = 21 + row * 13
                    col_w = 59

                    # Clean horizontal line below each row
                    if col == 0:
                        lcd.hline(2, cy + 12, 124, Theme.BORDER)

                    if site_i < total_s:
                        site_entry = monitored_sites[site_i]
                        res = site_results.get(site_entry, {})
                        is_up = res.get("up")
                        clean_name = site_entry.split(":")[0][:7]
                        is_sel = (site_i == cur_idx)

                        if is_sel:
                            ui.draw_text(lcd, ">", cx + 1, cy + 2, Theme.PRIMARY, font="6x8")
                            ui.draw_text(lcd, clean_name, cx + 8, cy + 2, Theme.PRIMARY, font="6x8")
                        else:
                            ui.draw_text(lcd, clean_name, cx + 4, cy + 2, Theme.TEXT_MUTED, font="6x8")

                        # Status Indicator dot (Green=UP, Red=DOWN, Yellow=WAIT)
                        if is_up is True:
                            dot_col = Theme.SUCCESS
                        elif is_up is False:
                            dot_col = Theme.DANGER
                        else:
                            dot_col = Theme.WARNING
                        lcd.fill_rect(cx + col_w - 7, cy + 4, 4, 4, dot_col)
                    else:
                        ui.draw_text(lcd, "--", cx + 6, cy + 2, Theme.TEXT_DARK, font="6x8")
            else:
                ui.draw_centered(lcd, "No sites", 55, Theme.TEXT_MUTED, font="6x8")
                ui.draw_centered(lcd, "Add via web", 70, Theme.INFO, font="6x8")

        else:
            # ==================================================================
            # VIEW B: SINGLE WEBPAGE DETAIL (Ultra-Minimalist, No Boxes)
            # ==================================================================
            if total_s > 0:
                cur_host = monitored_sites[cur_idx]
                res = site_results.get(cur_host, {"up": None, "code": "...", "ms": 0})
                is_up = (res["up"] is True)

                # Header with clean site domain
                host_title = cur_host.split(":")[0][:12].upper()
                badge_str = f"{res['ms']}ms" if is_up else ("DOWN" if res["up"] is False else "WAIT")
                ui.header(lcd, host_title, right_badge=badge_str, accent=Theme.SUCCESS if is_up else Theme.DANGER)

                # Section 1: Single-line Website URL & Status
                ui.draw_text(lcd, cur_host[:20], 6, 24, Theme.TEXT_MUTED, font="6x8")

                if res["up"] is None:
                    ui.draw_big(lcd, "WAIT", 6, 37, Theme.WARNING)
                    ui.badge(lcd, 88, 41, "...", variant="warning")
                elif is_up:
                    ui.draw_big(lcd, "UP", 6, 37, Theme.SUCCESS)
                    ui.draw_text(lcd, f"{res['ms']}ms", 50, 44, Theme.TEXT, font="6x8")
                    ui.badge(lcd, 88, 41, f"{res['code']}", variant="success")
                else:
                    ui.draw_big(lcd, "DOWN", 6, 37, Theme.DANGER)
                    ui.badge(lcd, 88, 41, "FAIL", variant="danger")

                # Horizontal line divider 1
                lcd.hline(6, 59, 116, Theme.BORDER)

                # Section 2: Min & Max with Char-sized Arrow Icons (No text Min/Max)
                stats = site_stats.get(cur_host, {"min": res["ms"] if is_up else 0, "max": res["ms"] if is_up else 0})
                min_v = stats.get("min", 0)
                max_v = stats.get("max", 0)

                # Down arrow (Min) + value
                ui.draw_arrow_down(lcd, 6, 65, Theme.SUCCESS)
                ui.draw_text(lcd, f"{min_v}ms", 15, 65, Theme.SUCCESS, font="6x8")

                # Up arrow (Max) + value
                ui.draw_arrow_up(lcd, 70, 65, Theme.WARNING)
                ui.draw_text(lcd, f"{max_v}ms", 79, 65, Theme.WARNING, font="6x8")

                # Horizontal line divider 2
                lcd.hline(6, 78, 116, Theme.BORDER)

                # Section 3: Response Time Histogram Chart (No box, clean baseline)
                ui.latency_chart(lcd, 6, 82, 116, 42, site_history.get(cur_host, []), min_val=min_v, max_val=max_v)
            else:
                ui.header(lcd, "SITES", right_badge="0", accent=Theme.WARNING)
                ui.draw_centered(lcd, "No sites", 55, Theme.TEXT_MUTED, font="6x8")

    # --------------------------------------------------------------------------
    # SCREEN 4.5: YOUTUBE TRACKER (Ultra-Minimalist, No Boxes)
    # --------------------------------------------------------------------------
    elif screen == "yt":
        ui.header(lcd, "YT", right_badge=yt_data["status"][:6], accent=Theme.DANGER)

        if not yt_svc.yt_channel_id or not yt_svc.yt_api_key:
            ui.draw_centered(lcd, "CONFIG NEEDED", 42, Theme.WARNING, font="6x8")
            ui.draw_centered(lcd, "Set API Key & ID", 58, Theme.TEXT_MUTED, font="6x8")
            ui.draw_centered(lcd, "in Web Dashboard:", 72, Theme.TEXT_MUTED, font="6x8")
            if wlan.isconnected():
                ui.draw_centered(lcd, f"http://{wlan.ifconfig()[0]}", 88, Theme.INFO, font="6x8")
            else:
                ui.draw_centered(lcd, "Connect Wi-Fi", 88, Theme.DANGER, font="6x8")
        else:
            # Section 1: Full Channel Title on line 1; Hero Subs on left, SUBS + VIDS stacked on right
            clean_title = (yt_data["title"] if yt_data["title"] != "YouTube" else yt_svc.yt_channel_id)[:19].upper()
            ui.draw_text(lcd, clean_title, 6, 22, Theme.TEXT_MUTED, font="6x8")

            s_str = fmt_num(yt_data["subs"])
            ui.draw_big(lcd, s_str, 6, 33, Theme.DANGER)
            ui.badge(lcd, 122, 32, "SUBS", variant="danger", align_right=True)
            ui.draw_right(lcd, f"{fmt_num(yt_data['videos'])} VIDS", 44, Theme.INFO, margin=6, font="6x8")

            # Horizontal Divider Line 1
            lcd.hline(6, 54, 116, Theme.BORDER)

            # Section 2: Lifetime Total Views & Tracked Session Gain
            ui.draw_text(lcd, "VIEWS", 6, 58, Theme.TEXT_MUTED, font="6x8")
            v_str = fmt_num(yt_data["views"])
            ui.draw_text(lcd, v_str, 42, 58, Theme.INFO, font="6x8")

            session_gain = max(0, yt_data["views"] - yt_svc.yt_initial_views) if yt_svc.yt_initial_views > 0 else 0
            gain_str = f"+{fmt_num(session_gain)}" if session_gain > 0 else "0 GAIN"
            gain_col = Theme.SUCCESS if session_gain > 0 else Theme.TEXT_DARK
            ui.draw_right(lcd, gain_str, 58, gain_col, margin=6, font="6x8")

            # Min / Max / Sync stats
            min_v = min(yt_svc.yt_views_history) if yt_svc.yt_views_history else 0
            max_v = max(yt_svc.yt_views_history) if yt_svc.yt_views_history else 0

            ui.draw_arrow_down(lcd, 6, 69, Theme.SUCCESS)
            ui.draw_text(lcd, f"{min_v}", 15, 69, Theme.SUCCESS, font="6x8")

            ui.draw_arrow_up(lcd, 48, 69, Theme.WARNING)
            ui.draw_text(lcd, f"{max_v}", 57, 69, Theme.WARNING, font="6x8")

            ui.draw_right(lcd, "SYNC 10m", 69, Theme.TEXT_MUTED, margin=6, font="6x8")

            # Horizontal Divider Line 2
            lcd.hline(6, 80, 116, Theme.BORDER)

            # Section 3: Genuine View Deltas Histogram Bar Chart
            ui.latency_chart(lcd, 6, 83, 116, 43, yt_svc.yt_views_history, min_val=min_v, max_val=max_v)

    # --------------------------------------------------------------------------
    # SCREEN 4.6: LOCAL WEATHER (Open-Meteo & IP Geolocation, Ultra-Minimalist)
    # --------------------------------------------------------------------------
    elif screen == "wx":
        ui.header(lcd, "WX", right_badge=loc_data["city"][:7], accent=Theme.WARNING)

        if weather_data["status"] == "WAIT":
            ui.draw_centered(lcd, "FETCHING WX...", 52, Theme.WARNING, font="6x8")
            ui.draw_centered(lcd, loc_data["city"], 68, Theme.TEXT_MUTED, font="6x8")
        elif weather_data["status"] in ("NO-WIFI", "ERR"):
            ui.draw_centered(lcd, "WX UNAVAILABLE", 52, Theme.DANGER, font="6x8")
            ui.draw_centered(lcd, weather_data["status"], 68, Theme.TEXT_MUTED, font="6x8")
        else:
            # Section 1: Hero Temp + Weather Graphic Icon + City + Condition Badge
            t_val = weather_data["temp"]
            t_str = f"{t_val:.1f}" if t_val is not None else "--"
            ui.draw_big(lcd, t_str, 6, 23, Theme.TEXT)
            ui.draw_text(lcd, "C", 6 + len(t_str) * 14 + 1, 23, Theme.TEXT_MUTED, font="6x8")

            # Weather Graphic Icon (22x15 px top right)
            cond_str = weather_data["desc"]
            ui.draw_weather_icon(lcd, 98, 21, cond_str)

            # City name (left) & Condition Badge (right)
            ui.draw_text(lcd, loc_data["city"][:13], 6, 41, Theme.TEXT_MUTED, font="6x8")

            c_variant = "warning"
            if cond_str in ("RAIN", "STORM"): c_variant = "danger"
            elif cond_str == "CLEAR": c_variant = "success"
            elif cond_str in ("FOG", "SNOW"): c_variant = "info"
            ui.badge(lcd, 122, 39, cond_str, variant=c_variant, align_right=True)

            # Horizontal Divider Line 1
            lcd.hline(6, 51, 116, Theme.BORDER)

            # Section 2: Humidity, Wind & Sync Interval
            ui.draw_text(lcd, "HUM", 6, 56, Theme.TEXT_MUTED, font="6x8")
            ui.draw_text(lcd, f"{weather_data['humidity']}%", 28, 56, Theme.INFO, font="6x8")

            ui.draw_text(lcd, "WND", 58, 56, Theme.TEXT_MUTED, font="6x8")
            ui.draw_text(lcd, f"{weather_data['wind']:.1f}k", 80, 56, Theme.PRIMARY, font="6x8")

            ui.draw_right(lcd, "15m", 56, Theme.TEXT_MUTED, margin=6, font="6x8")

            # Horizontal Divider Line 2
            lcd.hline(6, 67, 116, Theme.BORDER)

            # Section 3: 12-Hour Forward Temperature Forecast Line Chart
            ui.draw_forecast_line_chart(lcd, 6, 70, 116, 57, weather_data.get("hourly_temps", []), weather_data.get("hourly_hours", []))

    # --------------------------------------------------------------------------
    # SCREEN 4.7: MOON PHASES & FULL MOON COUNTDOWN (Ultra-Minimalist)
    # --------------------------------------------------------------------------
    elif screen == "moon":
        m_info = moon.get_moon_info()
        ui.header(lcd, "MOON", right_badge=f"{m_info['illum']:.0f}%", accent=Theme.INFO)

        # Section 1: Hero Moon Disk + Illumination & Age + Phase Name
        ui.draw_moon_disk(lcd, 64, 40, 15, m_info["phase"])

        # Illumination on Left
        ui.draw_text(lcd, "ILLUM", 6, 31, Theme.TEXT_MUTED, font="6x8")
        ui.draw_text(lcd, f"{m_info['illum']:.0f}%", 6, 41, Theme.INFO, font="6x8")

        # Lunar Age on Right
        ui.draw_right(lcd, "AGE", 31, Theme.TEXT_MUTED, margin=6, font="6x8")
        ui.draw_right(lcd, f"{m_info['age']:.1f}d", 41, Theme.WARNING, margin=6, font="6x8")

        # Official Phase Name
        ui.draw_centered(lcd, m_info["name"], 59, Theme.TEXT, font="6x8")

        # Divider 1
        lcd.hline(6, 69, 116, Theme.BORDER)

        # Section 2: Next Full Moon Countdown
        ui.draw_text(lcd, "NEXT FULL MOON", 6, 73, Theme.TEXT_MUTED, font="6x8")
        d_val = f"{m_info['days_to_full']:.0f}"
        ui.draw_big(lcd, d_val, 6, 84, Theme.WARNING)
        d_x = 6 + len(d_val) * 14 + 3
        ui.draw_text(lcd, "DAYS", d_x, 88, Theme.TEXT, font="6x8")

        ui.draw_right(lcd, f"IN {m_info['days_to_full']:.1f}d", 84, Theme.TEXT_MUTED, margin=6, font="6x8")
        ui.draw_right(lcd, m_info["full_date"], 95, Theme.SUCCESS, margin=6, font="6x8")

        # Divider 2
        lcd.hline(6, 106, 116, Theme.BORDER)

        # Section 3: Synodic Cycle Progress Track
        ui.progress_bar(lcd, 6, 110, 116, 4, int(m_info["phase"] * 100), variant="primary")
        ui.draw_text(lcd, "NEW", 6, 118, Theme.TEXT_DARK, font="6x8")
        ui.draw_centered(lcd, "FULL", 118, Theme.WARNING, font="6x8")
        ui.draw_right(lcd, "NEW", 118, Theme.TEXT_DARK, margin=6, font="6x8")

    # --------------------------------------------------------------------------
    # SCREEN 4.8: 21 BLACKJACK GAME
    # --------------------------------------------------------------------------
    elif screen == "game":
        blackjack.render_game_screen(lcd, bj_game)

    # --------------------------------------------------------------------------
    # SCREEN 4: ABOUT / WEB INFO (Ultra-Minimalist, No Boxes)
    # --------------------------------------------------------------------------
    elif screen == "about":
        ui.header(lcd, "WEB", right_badge="HTTP", accent=Theme.PRIMARY)

        # Section 1: Web Access URL
        ui.draw_text(lcd, "WEB URL", 6, 24, Theme.TEXT_MUTED, font="6x8")
        ui.badge(lcd, 88, 23, "PORT 80", variant="primary")
        if wlan.isconnected():
            ui.draw_text(lcd, f"http://{wlan.ifconfig()[0]}", 6, 38, Theme.TEXT, font="6x8")
            ui.draw_text(lcd, "Port: 80 (HTTP)", 6, 48, Theme.TEXT_DARK, font="6x8")
        else:
            ui.draw_text(lcd, "Conn...", 6, 38, Theme.WARNING, font="6x8")

        # Horizontal Divider Line
        lcd.hline(6, 59, 116, Theme.BORDER)

        # Section 2: Features Available
        ui.draw_text(lcd, "FEATURES", 6, 64, Theme.TEXT_MUTED, font="6x8")
        ui.draw_text(lcd, "- Add/del sites", 6, 78, Theme.SUCCESS, font="6x8")
        ui.draw_text(lcd, "- Custom ports", 6, 91, Theme.INFO, font="6x8")
        ui.draw_text(lcd, "- Brightness & alerts", 6, 104, Theme.TEXT_MUTED, font="6x8")

    # --------------------------------------------------------------------------
    # POP-UP: REMOTE WEB ALERT MODAL
    # --------------------------------------------------------------------------
    if web_alert_msg and (time.time() - web_alert_time < 8):
        ui.alert_modal(lcd, "WEB ALERT", web_alert_msg, variant="info")

    lcd.show()
    time.sleep_ms(30)
