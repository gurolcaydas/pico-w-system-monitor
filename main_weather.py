import network
import socket
import machine
import dht
import time
import json
import gc
import ntptime

from secrets import WIFI_SSID, WIFI_PASSWORD
from ssd1306 import SSD1306_I2C

import services
import views

# --- Hardware Initialization ---
led = machine.Pin("LED", machine.Pin.OUT)
led.value(0)

try:
    i2c0 = machine.I2C(0, sda=machine.Pin(0), scl=machine.Pin(1), freq=400000)
    oled1 = SSD1306_I2C(128, 32, i2c0)
    has_oled1 = True
except Exception:
    has_oled1 = False

try:
    i2c1 = machine.I2C(1, sda=machine.Pin(2), scl=machine.Pin(3), freq=400000)
    oled2 = SSD1306_I2C(128, 64, i2c1)
    has_oled2 = True
except Exception:
    has_oled2 = False

def oled_show_status(line1, line2=""):
    if has_oled1:
        try:
            oled1.fill(0)
            oled1.rect(0, 0, 128, 32, 1)
            oled1.text(line1[:14], 8, 5, 1)
            if line2: oled1.text(line2[:14], 8, 18, 1)
            oled1.show()
        except Exception:
            pass
    if has_oled2:
        try:
            oled2.fill(0)
            oled2.rect(0, 0, 128, 64, 1)
            oled2.text("PICO W CLIMATE", 8, 8, 1)
            oled2.hline(0, 20, 128, 1)
            oled2.text(line1[:15], 8, 28, 1)
            if line2: oled2.text(line2[:15], 8, 42, 1)
            oled2.show()
        except Exception:
            pass

oled_show_status("PICO W BASLIYOR", "WiFi Baglaniyor")

dht_sensor = dht.DHT11(machine.Pin(28))
adc_cpu = machine.ADC(4)

sensor_data = {
    "temperature_c": 22,
    "temperature_f": 71.6,
    "humidity_pct": 46,
    "status": "initializing"
}

daily_stats = {
    "date": "",
    "min_temp": 999, "min_temp_time": "--:--",
    "max_temp": -999, "max_temp_time": "--:--",
    "min_hum": 999, "min_hum_time": "--:--",
    "max_hum": -999, "max_hum_time": "--:--"
}

all_time_stats = {
    "min_temp": 999, "min_temp_time": "",
    "max_temp": -999, "max_temp_time": "",
    "min_hum": 999, "min_hum_time": "",
    "max_hum": -999, "max_hum_time": ""
}

history = []
MAX_HISTORY = 60
last_history_time = 0
last_read_time = 0
start_time = time.ticks_ms()
ntp_synced = False

def sync_time():
    global ntp_synced
    try:
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        ntp_synced = True
        print("-> NTP Time Synced successfully!")
    except Exception as e:
        print("NTP sync warning:", e)

def update_sensor():
    global last_read_time, last_history_time
    now = time.ticks_ms()
    if time.ticks_diff(now, last_read_time) > 2000 or last_read_time == 0:
        try:
            dht_sensor.measure()
            tc = dht_sensor.temperature()
            h = dht_sensor.humidity()
            tf = round((tc * 9/5) + 32, 1)
            sensor_data["temperature_c"] = tc
            sensor_data["temperature_f"] = tf
            sensor_data["humidity_pct"] = h
            sensor_data["status"] = "ok"
            last_read_time = now

            today = services.get_date_str()
            t_short = services.get_short_time_str()
            t_full = services.get_time_str()
            if daily_stats["date"] != today:
                daily_stats["date"] = today
                daily_stats["min_temp"] = tc; daily_stats["min_temp_time"] = t_short
                daily_stats["max_temp"] = tc; daily_stats["max_temp_time"] = t_short
                daily_stats["min_hum"] = h; daily_stats["min_hum_time"] = t_short
                daily_stats["max_hum"] = h; daily_stats["max_hum_time"] = t_short
            else:
                if tc < daily_stats["min_temp"]: daily_stats["min_temp"] = tc; daily_stats["min_temp_time"] = t_short
                if tc > daily_stats["max_temp"]: daily_stats["max_temp"] = tc; daily_stats["max_temp_time"] = t_short
                if h < daily_stats["min_hum"]: daily_stats["min_hum"] = h; daily_stats["min_hum_time"] = t_short
                if h > daily_stats["max_hum"]: daily_stats["max_hum"] = h; daily_stats["max_hum_time"] = t_short

            if tc < all_time_stats["min_temp"]: all_time_stats["min_temp"] = tc; all_time_stats["min_temp_time"] = f"{today} {t_full}"
            if tc > all_time_stats["max_temp"]: all_time_stats["max_temp"] = tc; all_time_stats["max_temp_time"] = f"{today} {t_full}"
            if h < all_time_stats["min_hum"]: all_time_stats["min_hum"] = h; all_time_stats["min_hum_time"] = f"{today} {t_full}"
            if h > all_time_stats["max_hum"]: all_time_stats["max_hum"] = h; all_time_stats["max_hum_time"] = f"{today} {t_full}"

            if time.ticks_diff(now, last_history_time) >= 15000 or not history:
                history.append({"t": t_short, "temp": tc, "hum": h})
                if len(history) > MAX_HISTORY: history.pop(0)
                last_history_time = now
        except OSError:
            pass

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print(f"Connecting to '{WIFI_SSID}'...")
    max_wait = 20
    dot_count = 0
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3: break
        led.value(not led.value())
        dot_count = (dot_count + 1) % 4
        oled_show_status("CONNECTING...", WIFI_SSID + ("." * dot_count))
        time.sleep(0.5)
        max_wait -= 1

    if wlan.status() != 3:
        led.value(0)
        oled_show_status("WIFI HATASI", "Sifreyi Kontrol")
        raise RuntimeError("Wi-Fi connection failed")
    else:
        led.value(1)
        ip = wlan.ifconfig()[0]
        print(f"-> Connected! IP: http://{ip}")
        oled_show_status("WIFI BAGLANDI", ip)
        time.sleep(1)
        return ip

def refresh_oled_displays(ip=None, frame=0):
    tc = sensor_data["temperature_c"]
    h  = sensor_data["humidity_pct"]

    if has_oled1:
        try:
            oled1.fill(0)
            text1 = f"{tc}C {h}%"
            views.draw_big_text(oled1, text1, max(0, (128 - len(text1) * 16) // 2), 4, sx=2, sy=3, color=1)
            oled1.show()
        except Exception:
            pass

    if has_oled2:
        try:
            view_mode = (time.ticks_ms() // 6000) % 18
            if view_mode == 0:
                oled2.fill(0)
                oled2.vline(63, 0, 64, 1)
                t_vals = [pt["temp"] for pt in history] if history else [tc]
                h_vals = [pt["hum"] for pt in history] if history else [h]
                hi_t = daily_stats["max_temp"] if daily_stats["max_temp"] != -999 else max(t_vals)
                lo_t = daily_stats["min_temp"] if daily_stats["min_temp"] != 999 else min(t_vals)
                hi_h = daily_stats["max_hum"] if daily_stats["max_hum"] != -999 else max(h_vals)
                lo_h = daily_stats["min_hum"] if daily_stats["min_hum"] != 999 else min(h_vals)
                views.draw_vertical_pane(oled2, 0, tc, "C", lo_t, hi_t, t_vals)
                views.draw_vertical_pane(oled2, 64, h, "%", lo_h, hi_h, h_vals)
                oled2.show()
            elif view_mode == 1:
                views.render_moon_view(oled2, services.get_moon_info())
                oled2.show()
            elif view_mode == 2:
                views.render_datetime_view(oled2)
                oled2.show()
            elif view_mode == 3:
                views.render_usd_view(oled2)
                oled2.show()
            elif view_mode == 4:
                views.render_eur_view(oled2)
                oled2.show()
            elif view_mode == 5:
                views.render_gold_view(oled2)
                oled2.show()
            elif view_mode == 6:
                views.render_sun_view(oled2)
                oled2.show()
            elif view_mode == 7:
                views.render_sky_view(oled2)
                oled2.show()
            elif view_mode == 8:
                views.render_3day_view(oled2)
                oled2.show()
            elif view_mode == 9:
                views.render_balloon_view(oled2)
                oled2.show()
            elif view_mode == 10:
                views.render_stargazing_view(oled2)
                oled2.show()
            elif view_mode == 11:
                views.render_earthquake_view(oled2)
                oled2.show()
            elif view_mode == 12:
                views.render_air_quality_view(oled2)
                oled2.show()
            elif view_mode == 13:
                views.render_prayer_view(oled2)
                oled2.show()
            elif view_mode == 14:
                views.render_iss_view(oled2)
                oled2.show()
            elif view_mode == 15:
                views.render_ping_view(oled2)
                oled2.show()
            elif view_mode == 16:
                views.render_holiday_view(oled2)
                oled2.show()
            else:
                telem = services.read_device_telemetry(adc_cpu, start_time)
                views.render_telemetry_view(oled2, telem)
                oled2.show()
        except Exception:
            pass

def send_response(client, status_code, content_type, body):
    reason = "OK" if status_code == 200 else ("Not Found" if status_code == 404 else "Error")
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    header = f"HTTP/1.0 {status_code} {reason}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body_bytes)}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
    client.send(header.encode("utf-8"))
    client.send(body_bytes)

def send_file_response(client, filepath, content_type="text/html; charset=utf-8"):
    try:
        header = f"HTTP/1.0 200 OK\r\nContent-Type: {content_type}\r\nConnection: close\r\n\r\n"
        client.send(header.encode('utf-8'))
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(512)
                if not chunk: break
                client.send(chunk)
    except Exception as e:
        print("Send file error:", e)

def start_server():
    ip = connect_wifi()
    sync_time()
    oled_show_status("ISTASYON AKTIF", ip)

    services.update_tcmb_rates()
    services.update_usd_history()
    services.update_eur_history()
    services.update_gold_history()
    services.update_ping()
    services.update_cappadocia_weather()
    services.update_earthquake()
    services.update_air_quality()
    services.update_iss()

    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(4)
    server.settimeout(0.8)
    
    print(f"--- Climate Station listening on http://{ip} ---")
    frame = 0

    while True:
        frame += 1
        update_sensor()
        services.update_tcmb_rates()
        services.update_usd_history()
        services.update_eur_history()
        services.update_gold_history()
        services.update_ping()
        services.update_cappadocia_weather()
        services.update_earthquake()
        services.update_air_quality()
        services.update_iss()
        refresh_oled_displays(ip, frame)
        gc.collect()

        try:
            client, client_addr = server.accept()
        except OSError:
            continue

        try:
            client.settimeout(2.0)
            req = client.recv(1024).decode('utf-8', 'ignore')
            first_line = req.split('\r\n')[0] if req else ''
            uptime = time.ticks_diff(time.ticks_ms(), start_time) // 1000
            tc = sensor_data["temperature_c"]
            tf = sensor_data["temperature_f"]
            h  = sensor_data["humidity_pct"]

            if '/api/history' in first_line:
                body = json.dumps(history)
                send_response(client, 200, "application/json", body)

            elif '/api/stats' in first_line:
                payload = {
                    "current": {"temperature_c": tc, "temperature_f": tf, "humidity_pct": h},
                    "today": daily_stats,
                    "all_time": all_time_stats,
                    "comfort": services.get_comfort_rating(tc, h),
                    "dew_point_c": services.get_dew_point(tc, h),
                    "moon": services.get_moon_info(),
                    "sun": services.calculate_sun_times(),
                    "sky": services.sky_weather,
                    "telemetry": services.read_device_telemetry(adc_cpu, start_time),
                    "earthquake": services.earthquake_data,
                    "air_quality": services.air_quality_data,
                    "prayer": services.calc_prayer_times(),
                    "iss": services.iss_data,
                    "rates": {"usd_try_buy": services.tcmb_rates["buying"], "usd_try_sell": services.tcmb_rates["selling"]},
                    "rates_30d": services.usd_rates["history_30d"],
                    "eur_rates_30d": services.eur_rates["history_30d"],
                    "gold": {"history_30d": services.gold_rates["history_30d"], "latest_tl": services.gold_rates["history_30d"][-1] if services.gold_rates["history_30d"] else 6542.0},
                    "ping": {"current_ms": services.ping_data["current_ms"], "history": services.ping_data["history"]},
                    "cappadocia_3day": services.sky_weather.get("daily_3day", {}),
                    "stargazing": services.calc_stargazing(),
                    "next_holiday": services.calc_next_holiday(),
                    "local_time": services.get_time_str(),
                    "date": services.get_date_str(),
                    "uptime_sec": uptime,
                    "history_points": len(history)
                }
                body = json.dumps(payload)
                send_response(client, 200, "application/json", body)

            elif '/api/temp' in first_line:
                payload = {
                    "temperature_c": tc, "temperature_f": tf, "humidity_pct": h,
                    "comfort": services.get_comfort_rating(tc, h),
                    "dew_point_c": services.get_dew_point(tc, h),
                    "moon": services.get_moon_info(),
                    "sun": services.calculate_sun_times(),
                    "sky": services.sky_weather,
                    "telemetry": services.read_device_telemetry(adc_cpu, start_time),
                    "earthquake": services.earthquake_data,
                    "air_quality": services.air_quality_data,
                    "prayer": services.calc_prayer_times(),
                    "iss": services.iss_data,
                    "rates": {"usd_try_buy": services.tcmb_rates["buying"], "usd_try_sell": services.tcmb_rates["selling"]},
                    "rates_30d": services.usd_rates["history_30d"],
                    "eur_rates_30d": services.eur_rates["history_30d"],
                    "gold": {"history_30d": services.gold_rates["history_30d"], "latest_tl": services.gold_rates["history_30d"][-1] if services.gold_rates["history_30d"] else 6542.0},
                    "ping": {"current_ms": services.ping_data["current_ms"]},
                    "stargazing": services.calc_stargazing(),
                    "next_holiday": services.calc_next_holiday(),
                    "time": services.get_time_str(),
                    "uptime_sec": uptime
                }
                body = json.dumps(payload)
                send_response(client, 200, "application/json", body)

            else:
                send_file_response(client, "dashboard.html")

        except Exception as e:
            print("Client handler error:", e)
        finally:
            try: client.close()
            except Exception: pass

if __name__ == "__main__":
    start_server()
