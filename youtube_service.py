import socket
import ssl
import json
import time
import gc

YT_FILE = "youtube.txt"
YT_VIEWS_FILE = "yt_views.txt"

def load_yt_config():
    ch = ""
    key = ""
    try:
        from secrets import YOUTUBE_CHANNEL_ID, YOUTUBE_API_KEY
        ch = YOUTUBE_CHANNEL_ID
        key = YOUTUBE_API_KEY
    except Exception:
        pass
    try:
        with open(YT_FILE, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            if len(lines) >= 1 and lines[0]:
                ch = lines[0]
            if len(lines) >= 2 and lines[1]:
                key = lines[1]
    except Exception:
        pass
    return ch, key

def save_yt_config(ch, key):
    try:
        with open(YT_FILE, "w") as f:
            f.write(ch.strip() + "\n")
            f.write(key.strip() + "\n")
    except Exception:
        pass

def fmt_num(n):
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    elif n >= 10000:
        return f"{n/1000:.1f}K"
    elif n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)

yt_channel_id, yt_api_key = load_yt_config()

yt_data = {
    "subs": 0,
    "views": 0,
    "videos": 0,
    "title": "YouTube",
    "status": "WAIT" if (yt_channel_id and yt_api_key) else "NO-KEY",
    "last_sync": 0,
}
yt_stats = {"min_subs": 0, "max_subs": 0}
yt_history = []
last_yt_check_time = 0

def load_yt_views():
    hist = []
    last_v = 0
    last_t = 0
    try:
        with open(YT_VIEWS_FILE, "r") as f:
            for line in f.readlines():
                line = line.strip()
                if line:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        last_t = int(parts[0])
                        last_v = int(parts[1])
                        hist.append(int(parts[2]))
    except Exception:
        pass
    return hist[-16:], last_v, last_t

def save_yt_views(hist, last_v, last_t):
    try:
        with open(YT_VIEWS_FILE, "w") as f:
            start = max(0, len(hist) - 16)
            for d in hist[start:]:
                f.write(f"{last_t},{last_v},{d}\n")
    except Exception:
        pass

yt_views_history, yt_last_views, yt_last_views_time = load_yt_views()
yt_initial_views = 0

def record_yt_views_sample(cur_views):
    global yt_views_history, yt_last_views, yt_last_views_time, yt_initial_views
    now = time.time()
    if cur_views <= 0:
        return

    if yt_initial_views == 0:
        yt_initial_views = cur_views

    if yt_last_views <= 0:
        yt_last_views = cur_views
        yt_last_views_time = now
        save_yt_views(yt_views_history, yt_last_views, yt_last_views_time)
        return

    interval_s = 3600
    if yt_last_views_time > 0 and (now - yt_last_views_time >= interval_s):
        delta = max(0, cur_views - yt_last_views)
        yt_views_history.append(delta)
        if len(yt_views_history) > 16:
            yt_views_history.pop(0)
        yt_last_views = cur_views
        yt_last_views_time = now
        save_yt_views(yt_views_history, yt_last_views, yt_last_views_time)
    else:
        if yt_views_history:
            live_delta = max(0, cur_views - yt_last_views)
            if live_delta > yt_views_history[-1]:
                yt_views_history[-1] = live_delta
        elif cur_views > yt_last_views:
            yt_views_history.append(cur_views - yt_last_views)

def fetch_youtube_stats(wlan_connected):
    global yt_data, yt_stats, yt_history, yt_channel_id, yt_api_key, yt_views_history
    if not yt_channel_id or not yt_api_key:
        yt_data["status"] = "NO-KEY"
        return False
    if not wlan_connected:
        yt_data["status"] = "NO-WIFI"
        return False

    gc.collect()
    ch = yt_channel_id.strip()
    key = yt_api_key.strip()

    if ch.startswith("UC") and len(ch) >= 20:
        param = f"id={ch}"
    else:
        handle = ch if ch.startswith("@") else f"@{ch}"
        param = f"forHandle=%40{handle.lstrip('@')}"

    path = f"/youtube/v3/channels?part=snippet,statistics&{param}&key={key}"
    s = None
    try:
        ai = socket.getaddrinfo("www.googleapis.com", 443)[0][-1]
        s_raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_raw.settimeout(6.0)
        s_raw.connect(ai)
        s = ssl.wrap_socket(s_raw, server_hostname="www.googleapis.com")

        req = f"GET {path} HTTP/1.1\r\nHost: www.googleapis.com\r\nUser-Agent: PicoW\r\nConnection: close\r\n\r\n".encode()
        s.write(req)

        raw = b""
        while len(raw) < 4096:
            c = s.read(512)
            if not c:
                break
            raw += c
        s.close()
        s = None

        s_idx = raw.find(b'{')
        e_idx = raw.rfind(b'}')
        if s_idx == -1 or e_idx == -1:
            yt_data["status"] = "ERR-RSP"
            return False

        data = json.loads(raw[s_idx:e_idx+1].decode('utf-8', 'ignore'))
        if "error" in data:
            yt_data["status"] = f"E{data['error'].get('code', 400)}"
            return False

        items = data.get("items", [])
        if not items:
            yt_data["status"] = "NO-CHAN"
            return False

        item = items[0]
        title = item.get("snippet", {}).get("title", "YouTube")
        stats = item.get("statistics", {})
        subs = int(stats.get("subscriberCount", 0))
        views = int(stats.get("viewCount", 0))
        vids = int(stats.get("videoCount", 0))

        yt_data["title"] = title
        yt_data["subs"] = subs
        yt_data["views"] = views
        yt_data["videos"] = vids
        yt_data["status"] = "OK"
        yt_data["last_sync"] = time.time()

        record_yt_views_sample(views)

        if not yt_history:
            yt_history.append(subs)
        else:
            yt_history.append(subs)
            if len(yt_history) > 16:
                yt_history.pop(0)

        cur_min = yt_stats.get("min_subs", 0)
        cur_max = yt_stats.get("max_subs", 0)
        if cur_min == 0 or subs < cur_min:
            yt_stats["min_subs"] = subs
        if subs > cur_max:
            yt_stats["max_subs"] = subs
        return True
    except Exception:
        yt_data["status"] = "ERR"
        return False
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        gc.collect()
