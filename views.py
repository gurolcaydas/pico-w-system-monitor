import math
import framebuf
import time
import services

_char_buf = bytearray(8)
_char_fb = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.MONO_HLSB)

def draw_big_text(fb, text, x, y, sx=2, sy=3, color=1):
    cur_x = x
    for ch in text:
        _char_fb.fill(0)
        _char_fb.text(ch, 0, 0, 1)
        for py in range(8):
            for px in range(8):
                if _char_fb.pixel(px, py):
                    fb.fill_rect(cur_x + px * sx, y + py * sy, sx, sy, color)
        cur_x += 8 * sx

def draw_vertical_pane(oled, x_offset, cur_val, unit, min_v, max_v, values):
    pane_w = 64
    val_str = f"{cur_val}{unit}"
    val_w = len(val_str) * 16
    val_x = x_offset + max(0, (pane_w - val_w) // 2)
    draw_big_text(oled, val_str, val_x, 2, sx=2, sy=2, color=1)
    range_str = f"{min_v}-{max_v}"
    range_w = len(range_str) * 8
    range_x = x_offset + max(0, (pane_w - range_w) // 2)
    oled.text(range_str, range_x, 20, 1)
    
    chart_x = x_offset + 5
    chart_w = 54
    chart_y = 31
    chart_h = 30
    oled.hline(chart_x, chart_y + chart_h - 1, chart_w, 1)
    
    if len(values) >= 2:
        span = max_v - min_v if max_v != min_v else 1
        step_x = chart_w / (len(values) - 1)
        prev_x, prev_y = None, None
        for i, val in enumerate(values):
            px = int(chart_x + i * step_x)
            if px > chart_x + chart_w - 1: px = chart_x + chart_w - 1
            py = int((chart_y + chart_h - 3) - ((val - min_v) / span) * (chart_h - 6))
            if prev_x is not None: oled.line(prev_x, prev_y, px, py, 1)
            prev_x, prev_y = px, py
        if prev_x is not None:
            oled.fill_rect(prev_x - 1, prev_y - 1, 3, 3, 1)
    elif len(values) == 1:
        oled.fill_rect(chart_x + chart_w // 2 - 1, chart_y + chart_h // 2 - 1, 3, 3, 1)

def draw_moon(oled, cx, cy, r, age):
    synodic = 29.53058867
    phase_angle = 2 * math.pi * age / synodic
    is_waxing = age < (synodic / 2)
    for dy in range(-r, r + 1):
        dx_max = int(math.sqrt(r * r - dy * dy))
        oled.pixel(cx - dx_max, cy + dy, 1)
        oled.pixel(cx + dx_max, cy + dy, 1)
        x_term = int(dx_max * math.cos(phase_angle))
        if is_waxing:
            x_start = min(x_term, dx_max)
            x_end = dx_max
        else:
            x_start = -dx_max
            x_end = max(-dx_max, x_term)
        if x_end >= x_start:
            oled.hline(cx + x_start, cy + dy, x_end - x_start + 1, 1)

def render_moon_view(oled, moon):
    oled.fill(0)
    phase = moon["phase_name"]
    top_str = f"AY • {phase}"
    top_x = max(0, (128 - len(top_str) * 8) // 2)
    oled.text(top_str, top_x, 2, 1)
    oled.hline(0, 12, 128, 1)
    
    draw_moon(oled, 26, 38, 22, moon["age_days"])
    
    illum_str = f"ISIK: %{moon['illumination_pct']}"
    oled.text(illum_str, 54, 16, 1)
    oled.hline(54, 28, 70, 1)
    
    oled.text("DOLUNAY:", 54, 33, 1)
    d = moon["days_to_full_int"]
    d_str = "BUGUN!" if d == 0 else f"{d} GUN"
    oled.text(d_str, 54, 44, 1)
    
    age_str = f"YAS: {int(moon['age_days'])}G"
    oled.text(age_str, 54, 54, 1)

def render_datetime_view(oled):
    oled.fill(0)
    t = services.get_now_tuple()
    y, m, d, hh, mm, ss, weekday = t[0], t[1], t[2], t[3], t[4], t[5], t[6]
    day_name = services.DAYS[weekday % 7]
    month_name = services.MONTHS[(m - 1) % 12]
    top_str = f"{day_name}, {d:02d} {month_name}"
    top_x = max(0, (128 - len(top_str) * 8) // 2)
    oled.text(top_str, top_x, 4, 1)
    oled.hline(16, 16, 96, 1)
    colon = ":" if (ss % 2 == 0) else " "
    time_str = f"{hh:02d}{colon}{mm:02d}"
    draw_big_text(oled, time_str, (128 - len(time_str) * 16) // 2, 22, sx=2, sy=3, color=1)
    bot_str = f"{y} • ISTANBUL TSI"
    oled.text(bot_str, max(0, (128 - len(bot_str) * 8) // 2), 52, 1)

def render_usd_view(oled):
    oled.fill(0)
    rates = services.usd_rates["history_30d"]
    try: cur_val = float(services.tcmb_rates["selling"])
    except Exception: cur_val = rates[-1]
    min_r, max_r = min(rates), max(rates)
    oled.text("USD/TRY", 0, 2, 1)
    val_str = f"{cur_val:.2f}"
    oled.text(val_str, 128 - len(val_str) * 8, 2, 1)
    oled.text(f"30G: {min_r:.2f}-{max_r:.2f}", 0, 12, 1)
    oled.hline(0, 23, 128, 1)
    chart_x, chart_y, chart_w, chart_h = 4, 26, 120, 36
    span = max_r - min_r if max_r != min_r else 0.01
    step_x = chart_w / (len(rates) - 1) if len(rates) > 1 else chart_w
    prev_px, prev_py = None, None
    for i, r in enumerate(rates):
        px = int(chart_x + i * step_x)
        if px > chart_x + chart_w - 1: px = chart_x + chart_w - 1
        py = int((chart_y + chart_h - 2) - ((r - min_r) / span) * (chart_h - 4))
        if prev_px is not None: oled.line(prev_px, prev_py, px, py, 1)
        prev_px, prev_py = px, py
    if prev_px is not None: oled.fill_rect(prev_px - 2, prev_py - 2, 4, 4, 1)

def render_eur_view(oled):
    oled.fill(0)
    rates = services.eur_rates["history_30d"]
    cur_val, min_r, max_r = rates[-1], min(rates), max(rates)
    oled.text("EUR/TRY", 0, 2, 1)
    val_str = f"{cur_val:.2f}"
    oled.text(val_str, 128 - len(val_str) * 8, 2, 1)
    oled.text(f"30G: {min_r:.2f}-{max_r:.2f}", 0, 12, 1)
    oled.hline(0, 23, 128, 1)
    chart_x, chart_y, chart_w, chart_h = 4, 26, 120, 36
    span = max_r - min_r if max_r != min_r else 0.01
    step_x = chart_w / (len(rates) - 1) if len(rates) > 1 else chart_w
    prev_px, prev_py = None, None
    for i, r in enumerate(rates):
        px = int(chart_x + i * step_x)
        if px > chart_x + chart_w - 1: px = chart_x + chart_w - 1
        py = int((chart_y + chart_h - 2) - ((r - min_r) / span) * (chart_h - 4))
        if prev_px is not None: oled.line(prev_px, prev_py, px, py, 1)
        prev_px, prev_py = px, py
    if prev_px is not None: oled.fill_rect(prev_px - 2, prev_py - 2, 4, 4, 1)

def render_gold_view(oled):
    oled.fill(0)
    rates = services.gold_rates["history_30d"]
    cur_val, min_r, max_r = rates[-1], min(rates), max(rates)
    oled.text("GRAM ALTIN", 0, 2, 1)
    val_str = f"{int(cur_val)} TL"
    oled.text(val_str, 128 - len(val_str) * 8, 2, 1)
    oled.text(f"30G: {int(min_r)}-{int(max_r)}", 0, 12, 1)
    oled.hline(0, 23, 128, 1)
    chart_x, chart_y, chart_w, chart_h = 4, 26, 120, 36
    span = max_r - min_r if max_r != min_r else 1
    step_x = chart_w / (len(rates) - 1) if len(rates) > 1 else chart_w
    prev_px, prev_py = None, None
    for i, r in enumerate(rates):
        px = int(chart_x + i * step_x)
        if px > chart_x + chart_w - 1: px = chart_x + chart_w - 1
        py = int((chart_y + chart_h - 2) - ((r - min_r) / span) * (chart_h - 4))
        if prev_px is not None: oled.line(prev_px, prev_py, px, py, 1)
        prev_px, prev_py = px, py
    if prev_px is not None: oled.fill_rect(prev_px - 2, prev_py - 2, 4, 4, 1)

def render_sun_view(oled):
    oled.fill(0)
    sun = services.calculate_sun_times()
    top_str = "GUNES VAKITLERI"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 4, 1)
    oled.hline(14, 15, 100, 1)
    oled.text("DOGUS", 18, 20, 1)
    draw_big_text(oled, sun["sunrise"], 12, 32, sx=1, sy=2, color=1)
    oled.vline(63, 18, 30, 1)
    oled.text("BATIS", 82, 20, 1)
    draw_big_text(oled, sun["sunset"], 76, 32, sx=1, sy=2, color=1)
    oled.hline(14, 50, 100, 1)
    bot_str = f"GUNDUZ: {sun['daylight']}"
    oled.text(bot_str, max(0, (128 - len(bot_str) * 8) // 2), 54, 1)

def render_sky_view(oled):
    oled.fill(0)
    top_str = "KAPADOKYA HAVA"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 2, 1)
    oled.hline(0, 12, 128, 1)
    t_str = f"{services.sky_weather['temp']:.1f}C"
    draw_big_text(oled, t_str, max(0, (128 - len(t_str) * 16) // 2), 15, sx=2, sy=2, color=1)
    hw_str = f"{services.sky_weather['humidity']}% • RZGR:{services.sky_weather['wind']:.1f}k"
    oled.text(hw_str, max(0, (128 - len(hw_str) * 8) // 2), 34, 1)
    cond_str = services.sky_weather.get("condition", "ACIK HAVA")
    oled.text(cond_str[:16], max(0, (128 - len(cond_str[:16]) * 8) // 2), 45, 1)
    loc_str = "GOREME • 1050M"
    oled.text(loc_str, max(0, (128 - len(loc_str) * 8) // 2), 55, 1)

def get_short_weather_code(c):
    if c == 0: return "ACIK "
    elif c in (1, 2): return "AZ BL"
    elif c == 3: return "KAPAL"
    elif c in (45, 48): return "SISLI"
    elif c in (51, 53, 55, 61, 63, 65, 80, 81, 82): return "YAGMR"
    elif c in (71, 73, 75, 85, 86): return "KARLI"
    elif c in (95, 96, 99): return "FIRTN"
    return "ACIK "

def render_3day_view(oled):
    oled.fill(0)
    top_fc = "3 GUNLUK TAHMIN"
    oled.text(top_fc, (128 - len(top_fc) * 8) // 2, 2, 1)
    oled.hline(0, 12, 128, 1)
    t_now = services.get_now_tuple()
    weekday = t_now[6]
    d_names = ["BUG", services.DAYS_SHORT[(weekday + 1) % 7], services.DAYS_SHORT[(weekday + 2) % 7]]
    daily = services.sky_weather.get("daily_3day", {})
    codes = daily.get("weather_code", [0, 0, 0])
    highs = daily.get("temperature_2m_max", [15.0, 15.0, 15.0])
    lows = daily.get("temperature_2m_min", [5.0, 5.0, 5.0])
    y_pos = [16, 32, 48]
    for idx in range(min(3, len(highs))):
        d_str = f"{d_names[idx]:3s} {int(round(highs[idx])):>2d}/{int(round(lows[idx])):>2d}C {get_short_weather_code(codes[idx]):5s}"
        oled.text(d_str, 0, y_pos[idx], 1)
        if idx < 2: oled.hline(0, y_pos[idx] + 11, 128, 1)

def render_balloon_view(oled):
    oled.fill(0)
    top_str = "BALON UCUSU"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 2, 1)
    oled.hline(0, 12, 128, 1)
    banner = f"{services.sky_weather['balloon_day']} • {services.sky_weather['balloon_date']}"
    oled.text(banner, max(0, (128 - len(banner) * 8) // 2), 16, 1)
    status = services.sky_weather["balloon_status"]
    draw_big_text(oled, status, max(0, (128 - len(status) * 16) // 2), 28, sx=2, sy=2, color=1)
    w_str = f"RUZGAR: {services.sky_weather['balloon_wind']:.1f} km/s"
    oled.text(w_str, max(0, (128 - len(w_str) * 8) // 2), 46, 1)
    slot_str = f"06:00 UCUSU {services.sky_weather['balloon_slot_temp']:.1f}C"
    oled.text(slot_str, max(0, (128 - len(slot_str) * 8) // 2), 55, 1)

def render_stargazing_view(oled):
    oled.fill(0)
    st = services.calc_stargazing()
    top_st = "YILDIZ GOZLEM"
    oled.text(top_st, (128 - len(top_st) * 8) // 2, 2, 1)
    oled.hline(0, 12, 128, 1)
    sc_str = f"%{st['score']}"
    draw_big_text(oled, sc_str, (128 - len(sc_str) * 16) // 2, 15, sx=2, sy=2, color=1)
    st_status = f"DURUM: {st['desc']}"
    oled.text(st_status, (128 - len(st_status) * 8) // 2, 34, 1)
    l1 = f"BULUT ORANI: %{st['cloud_cover']}"
    oled.text(l1, (128 - len(l1) * 8) // 2, 45, 1)
    l2 = f"AY ISIGI:    %{st['moon_illum']}"
    oled.text(l2, (128 - len(l2) * 8) // 2, 55, 1)

def render_earthquake_view(oled):
    oled.fill(0)
    top_str = "KANDILLI DEPREM"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 2, 1)
    oled.hline(0, 12, 128, 1)
    mag_str = f"{services.earthquake_data['mag']} ML"
    draw_big_text(oled, mag_str, max(0, (128 - len(mag_str) * 16) // 2), 16, sx=2, sy=2, color=1)
    loc = services.earthquake_data["loc"][:16]
    oled.text(loc, max(0, (128 - len(loc) * 8) // 2), 35, 1)
    sub = f"{services.earthquake_data['depth']}KM • {services.earthquake_data['time']}"
    oled.text(sub, max(0, (128 - len(sub) * 8) // 2), 46, 1)
    bot = "TURKIYE DEPREM"
    oled.text(bot, max(0, (128 - len(bot) * 8) // 2), 56, 1)

def render_air_quality_view(oled):
    oled.fill(0)
    top_str = "HAVA KALITESI"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 2, 1)
    oled.hline(0, 12, 128, 1)
    aqi_str = f"AQI {services.air_quality_data['aqi']}"
    draw_big_text(oled, aqi_str, max(0, (128 - len(aqi_str) * 16) // 2), 16, sx=2, sy=2, color=1)
    q_str = services.air_quality_data["aqi_txt"]
    oled.text(q_str, max(0, (128 - len(q_str) * 8) // 2), 35, 1)
    pm_str = f"PM2.5:{services.air_quality_data['pm25']} PM10:{int(services.air_quality_data['pm10'])}"
    oled.text(pm_str, max(0, (128 - len(pm_str) * 8) // 2), 46, 1)
    uv_str = f"UV INDEKSI: {services.air_quality_data['uv']:.1f}"
    oled.text(uv_str, max(0, (128 - len(uv_str) * 8) // 2), 56, 1)

def render_prayer_view(oled):
    oled.fill(0)
    pr = services.calc_prayer_times()
    top_str = "NAMAZ VAKITLERI"
    oled.text(top_str, (128 - len(top_str) * 8) // 2, 2, 1)
    oled.hline(0, 12, 128, 1)
    
    next_name = pr["next_name"]
    next_time = "05:09"
    next_idx = 0
    for i, s in enumerate(pr["slots"]):
        if s[0] == next_name:
            next_time = s[2]
            next_idx = i
            break
            
    n_str = f"SIRADAKI: {next_name}"
    oled.text(n_str, (128 - len(n_str) * 8) // 2, 16, 1)
    
    draw_big_text(oled, next_time, (128 - 5 * 16) // 2, 27, sx=2, sy=2, color=1)
    
    c_str = f"{pr['countdown']} KALDI"
    oled.text(c_str, (128 - len(c_str) * 8) // 2, 46, 1)
    
    following = pr["slots"][(next_idx + 1) % len(pr["slots"])]
    f_str = f"SONRA {following[0][:3]} {following[2]}"
    oled.text(f_str, (128 - len(f_str) * 8) // 2, 56, 1)

def render_iss_view(oled):
    oled.fill(0)
    top_str = "UZAY ISTASYONU"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 2, 1)
    oled.hline(0, 12, 128, 1)
    dist = services.iss_data["dist_km"]
    d_str = f"{dist} KM" if dist < 10000 else f"{dist//1000}k KM"
    draw_big_text(oled, d_str, max(0, (128 - len(d_str) * 16) // 2), 16, sx=2, sy=2, color=1)
    if dist < 1500: banner = "• TEPEDEN GECIS •"
    elif dist < 3000: banner = "BOLGEYE YAKLASIYOR"
    else: banner = f"IRTIFA: {services.iss_data['alt']} KM"
    oled.text(banner[:16], max(0, (128 - len(banner[:16]) * 8) // 2), 35, 1)
    pos_str = f"ENM:{services.iss_data['lat']:.1f} BYL:{services.iss_data['lon']:.1f}"
    oled.text(pos_str, max(0, (128 - len(pos_str) * 8) // 2), 46, 1)
    bot_str = f"GORUNUR: {services.iss_data['vis']}"
    oled.text(bot_str, max(0, (128 - len(bot_str) * 8) // 2), 56, 1)

def render_ping_view(oled):
    oled.fill(0)
    top_p = "INTERNET HIZI"
    oled.text(top_p, (128 - len(top_p) * 8) // 2, 2, 1)
    oled.hline(0, 12, 128, 1)
    lat = services.ping_data["current_ms"]
    p_str = f"{lat} MS"
    draw_big_text(oled, p_str, (128 - len(p_str) * 16) // 2, 16, sx=2, sy=2, color=1)
    rating = "HIZLI • 1.1.1.1" if lat < 50 else ("NORMAL • 1.1.1.1" if lat < 100 else "YAVAS • 1.1.1.1")
    oled.text(rating, (128 - len(rating) * 8) // 2, 34, 1)
    hist = services.ping_data["history"]
    if hist:
        p_min, p_max = min(hist) - 2, max(hist) + 2
        p_span = p_max - p_min if p_max != p_min else 1
        oled.hline(4, 62, 120, 1)
        for i in range(len(hist)):
            px = int(4 + i * (120 / max(1, len(hist) - 1)))
            py = int(60 - ((hist[i] - p_min) / p_span) * 14)
            oled.pixel(px, py, 1)
            if i > 0:
                prev_x = int(4 + (i-1) * (120 / max(1, len(hist) - 1)))
                prev_y = int(60 - ((hist[i-1] - p_min) / p_span) * 14)
                oled.line(prev_x, prev_y, px, py, 1)

def render_holiday_view(oled):
    oled.fill(0)
    top_m = "SIRADAKI BAYRAM"
    oled.text(top_m, (128 - len(top_m) * 8) // 2, 2, 1)
    oled.hline(0, 12, 128, 1)
    hol = services.calc_next_holiday()
    m_name = f"{hol['name']} {hol['sub']}"[:16]
    oled.text(m_name, (128 - len(m_name) * 8) // 2, 16, 1)
    d_txt = f"{hol['days']} GUN"
    draw_big_text(oled, d_txt, (128 - len(d_txt) * 16) // 2, 27, sx=2, sy=2, color=1)
    r_str = f"{hol['d_remain']}G {hol['h_remain']:02d}S KALDI"
    oled.text(r_str, (128 - len(r_str) * 8) // 2, 46, 1)
    b_str = f"{hol['target_date']} • TR"
    oled.text(b_str, (128 - len(b_str) * 8) // 2, 56, 1)

def render_telemetry_view(oled, telem):
    oled.fill(0)
    top_str = "CIHAZ BILGISI"
    oled.text(top_str, max(0, (128 - len(top_str) * 8) // 2), 4, 1)
    oled.hline(14, 15, 100, 1)
    rssi = telem["rssi"]
    if rssi >= -60: bars = "[||||]"
    elif rssi >= -70: bars = "[|||.]"
    elif rssi >= -80: bars = "[||..]"
    else: bars = "[|...]"
    oled.text(f"ISLEMCI:  {telem['cpu_temp']:.1f}C", 10, 20, 1)
    oled.text(f"WIFI: {rssi}dBm {bars}", 10, 31, 1)
    oled.text(f"BOS RAM:  {telem['free_ram_kb']} KB", 10, 42, 1)
    oled.text(f"CALISMA:  {telem['uptime_str'][:10]}", 10, 53, 1)
