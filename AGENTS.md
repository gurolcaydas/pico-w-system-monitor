# Pico Project AI Agent Guidelines & Engineering Rules

## 1. Hardware Constraints (RP2040 + Waveshare 1.44" LCD)
- **Target Microcontroller**: Raspberry Pi Pico W (RP2040 @ 133 MHz, 264 KB SRAM, CYW43439 Wi-Fi).
- **Display**: Waveshare Pico-LCD-1.44 (ST7735S, 128×128 pixels, 16-bit RGB565 little-endian byte-swapped).
- **Physical Key Navigation**:
  - `KEY3` (GP3, Top): Move / Up / Next / Cycle.
  - `KEY2` (GP2, Middle): Select / Action / Enter Detail / Re-probe.
  - `KEY1` (GP17, Bottom): Back / Exit to Parent Menu.
  - `KEY0` (GP15): **Physically broken**. Hardcoded to `False`. NEVER use or wait on KEY0.

## 2. UI & Aesthetics Rules
- **No Key Map / Hint Text**: NEVER display button hints (`K3:NEXT`, `K2:SELECT`, `K1:MENU`, `Press K2...`, or footers) anywhere in the UI.
- **Ultra-Minimalist Horizontal-Line Architecture (Zero Boxes)**:
  - **No Boxes / Enclosing Cards**: NEVER use bounding card boxes (`ui.card`, `lcd.rect`) across any screen in the UI.
  - **Faded Pill Badges (Zero Border Boxes)**: Badges (`ui.badge`) render as borderless, subtle rounded pills with a soft, faded dark-tint background (`get_badge_colors`) and bright, high-contrast typography. NEVER draw hard bounding border boxes (`lcd.rect`) around badges (e.g. `dB` in Wi-Fi, `PORT 80`, `133MHz`, `PASS`).
  - **1px Horizontal Dividers**: Separate sections and rows using clean 1-pixel horizontal lines (`lcd.hline`) in `Theme.BORDER`.
  - **Main Menu**: 9-category list with 8-item scroll window separated by 1px horizontal lines (`DEV`, `PING`, `LAN`, `SITES`, `YT`, `WX`, `MOON`, `GAMES`, `WEB`), active row indicated by `>` cursor and highlighted accent line (`start_y = 20`, `row_h = 13`).
  - **LAN Subsystem (`LAN`)**: Dedicated Local Network Explorer with View A (scrollable device list with IP, role badge, latency) and View B (device detail with open port badges, TCP service classification, re-probe action).
  - **Games Subsystem (`GAMES`)**: Dedicated Games Hub Menu (`View A`) listing games (`21 BLACKJACK`, `GALAXY QUEST`), where `KEY2` launches selected game (`View B`) and `KEY1` returns to Games Hub.
  - **Combined DEV Subsystem**: Like `SITES` and `GAMES`, `DEV` features a dedicated Landing Page (View A) with selectable subpages (`CORE`, `NET`, `MEM`), where KEY2 enters the full detail view (View B) and KEY1 returns to the landing page.
  - **Detail Screens (DEV Subpages, Ping, Sites, YT, WX, Web)**: Divided into clean sections by 1px horizontal lines on a unified dark canvas.
  - **Progress Bars**: Sleek track lines without outer border boxes.
- **Canvas Budget (128×128 px)**:
  - Header: `y = 0..18` (18 px).
  - Usable area: `y = 19..127` (109 px).
- **Typography & Anti-Smudge**:
  - High-density 6×8 font (`picoui.draw_text`, 21 chars/line) for all menus and lists.
  - 1-pixel crisp strokes only. Never use artificial double-strike bolding.
  - Use luminance contrast and subtle line accents for hierarchy.
- **Abbreviated Technical Vocabulary Rule (No Long Words)**:
  - On the 128×128 panel, NEVER use verbose labels or long words that waste spatial budget.
  - Use concise standard technical abbreviations across all labels, menus, and badges:
    - `Temperature` -> `Tmp` (e.g. `CORE TMP`)
    - `Device` -> `Dev`
    - `Network` -> `Net`
    - `Memory` -> `Mem`
    - `Allocated` -> `Alloc` (e.g. `Alloc: 42KB`)
    - `Connecting` -> `Conn...`
    - `Server` -> `Srv` (e.g. `WEB SRV`)
    - `Protocol` -> `Proto` (e.g. `Proto: ICMP`)
    - `Cloudflare` -> `CF` (e.g. `CF PING`, `1.1.1.1 (CF)`)
    - `YouTube` -> `YT` (e.g. `YT` menu item, `SUBS`, `VIDS`, `VIEWS`)
    - `Weather` -> `WX` (e.g. `WX` menu item, `HUM`, `WND`)
    - `Min / Max` -> Char-sized icons `↓` / `↑` (zero text labels)

## 3. Memory Management & Circular Buffer Rule
- **Bounded Buffers Only**: Any chart data, telemetry series, logs, or repeating job records **MUST be strictly bounded / circular with a fixed maximum size** (e.g. `len(history) <= 16`, `len(yt_history) <= 16`).
- **Pruning**: Always prune with FIFO `pop(0)` or circular ring buffers when appending new samples. Unbounded list growth will fragment MicroPython heap and cause OOM crashes.
- **Garbage Collection**: Run `gc.collect()` before and after heavy network operations (DNS lookup, HTTP socket reads, mbedTLS handshakes).

## 4. Internet Quality & Ping Architecture (`PING`)
- **View A (Landing Page - 8-Site NOC List)**:
  - 8 lines across the screen (`row_h = 13`, `start_y = 20`), one target per line:
    - `GW` (Local Router Gateway)
    - `CF` (Cloudflare `1.1.1.1`)
    - `GOOG` (Google `8.8.8.8`)
    - `CLOUD` (`caydas.cloud` - Personal Remote Server)
    - `QUAD9` (Quad9 `9.9.9.9`)
    - `OPEN` (OpenDNS `208.67.222.222`)
    - `LUMEN` (Lumen `4.2.2.2`)
    - `CF2` (Cloudflare `1.0.0.1`)
  - Each row shows: Target label, address, latest ping time (color-coded), and horizontal 1px divider.
  - Active selection highlighted with `>` cursor and cyan line.
  - Round-robin auto-probing in background updates all 8 targets continuously.
- **View B (Single-Target Detail)**:
  - Hero latency in big digits + Quality Grade pill badge (`GREAT` <30ms, `GOOD` <60ms, `FAIR` <120ms, `POOR` >=120ms, `LOSS`).
  - Consecutive packet jitter (`JIT: Xms`).
  - Char-sized Min (`↓`) & Max (`↑`) arrow icons + Packet Loss percentage (`LOSS X%`).
  - 16-bar response time histogram chart (`ui.latency_chart`) plotting live latency pulses.
- **Hardware Controls**:
  - On View A: `KEY3` moves cursor, `KEY2` enters Detail View, `KEY1` exits to SYS MENU.
  - On View B: `KEY3` cycles targets, `KEY2` sends instant re-probe, `KEY1` returns to View A Landing Page.

## 5. Sites Monitor Architecture
- **View A (Overview)**: 2-column NOC list showing up to 16 websites simultaneously (8 rows × 2 columns), with vertical divider at `x = 63` and color-coded status dots (Green = UP, Red = DOWN, Yellow = WAIT).
- **View B (Site Detail)**: Ultra-minimalist single-site view with **zero boxes/cards**:
  - Section 1: Single-line website URL + port, followed by hero status (`UP`/`DOWN`), latency, and HTTP code.
  - 1px horizontal line divider (`y = 59`).
  - Section 2: Daily Min and Max values using char-sized 5×7 arrow icons (`↓` for Min, `↑` for Max) without `MIN:` or `MAX:` text labels.
  - 1px horizontal line divider (`y = 78`).
  - Section 3: 16-bar response time histogram chart with baseline axis and color-coded spikes.

## 5. YouTube Channel Tracker Architecture
- **API**: Official YouTube Data API v3 (`https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&...`) over TLS port 443 with RP2040 built-in `ssl.wrap_socket`.
- **Query Frequency**: Automatically polls every 600 seconds (10 minutes) in the background (using 144 quota units/day out of 10,000 free units/day). KEY2 triggers manual sync on demand.
- **Data Extracted**: Channel Title, Subscriber Count, Cumulative Lifetime View Count, Public Video Count.
- **Dedicated Screen (`YT`)**:
  - Section 1: Single-line channel title, hero subscriber count (`ui.draw_big`), `SUBS` badge, and video count (`VIDS`).
  - 1px horizontal line divider (`y = 54`).
  - Section 2: Lifetime Total Views (`VIEWS: X.XK`), real tracked Session Gain (`+X GAIN`), and Min & Max interval views with char-sized `↓` / `↑` arrow icons.
  - 1px horizontal line divider (`y = 80`).
  - Section 3: Genuine View Deltas histogram bar chart (16 bounded bars, 1 hour per bar) with clean baseline axis and color-coded spikes (zero synthetic seed data).
- **Persistence**: Persistently stored in `youtube.txt` (channel + key) and `yt_views.txt` (bounded genuine view deltas).
- **Web UI Management**: Live config form on port 80 (`http://<pico_ip>/`) to update channel handle/ID and API key on the fly without re-flashing.

## 6. Local Weather & IP Geolocation Architecture (`WX`)
- **Auto-Detection**: Automatic IP Geolocation via `http://ip-api.com/json` over plain HTTP Port 80 (zero API key, zero SSL RAM overhead) detects current city, latitude, and longitude on boot.
- **Forecast Engine**: Official `http://api.open-meteo.com/v1/forecast` queries real-time temperature, humidity, wind speed, and weather code.
- **Query Frequency**: Automatically polls every 900 seconds (15 minutes) in the background. KEY2 triggers instant manual re-sync.
- **Dedicated Screen (`WX`)**:
  - Section 1: Hero temperature in big digits (`ui.draw_big`), condition pill badge (`CLEAR`, `RAIN`, `CLOUDY`, `FOG`, `SNOW`, `STORM`), and detected city.
  - 1px horizontal line divider (`y = 54`).
  - Section 2: Humidity (`HUM: XX%`), Wind (`WND: X.Xk`), Min (`↓`) & Max (`↑`) arrow icons, and `SYNC 15m`.
  - 1px horizontal line divider (`y = 80`).
  - Section 3: 16-bar temperature trend chart (`latency_chart`) plotting recent readings.
- **Web UI Management**: Live weather card on port 80 displaying detected city, temperature, humidity, wind, and re-sync button.

## 7. LAN Device & Service Explorer Architecture (`LAN`)
- **Discovery Engine (`lan_scanner.py`)**:
  - Automatically interrogates local subnet (e.g. `192.168.1.0/24`) determined via `wlan.ifconfig()`.
  - Non-blocking stepped TCP connect probes with low timeout (50ms) to detect active devices and signature service ports:
    - `80`: HTTP, `443`: HTTPS, `22`: SSH, `53`: DNS, `445`: SMB, `1883`: MQTT, `8123`: Home Assistant, `8080`: Alt Web, `3000`: Node/Dev, `5000`: UPnP, `3389`: RDP.
    - Active host detection via TCP SYN-ACK (`OPEN`) or TCP RST (`ECONNREFUSED` / Errno 111).
  - Priority scan ordering: Gateway (`.1`), Pico itself, common static blocks (`.2`..`.40`), and DHCP blocks (`.50`..`.75`, `.100`..`.135`).
  - Automatic role classification: `ROUTER`, `THIS PICO`, `HASS/IOT`, `DNS/PI`, `NAS/PC`, `LINUX/PI`, `WEB SRV`, `APP SRV`, `NODE`.
  - Bounded storage (max 16 hosts) persistently saved to `lan_devices.txt`.
- **Dedicated Screen (`LAN`)**:
  - **View A (Device List)**: Minimalist scrollable list of discovered devices with IP address, role pill badge (`RTR`, `PI`, `NAS`, `WEB`, `DEV`), latency in ms, and 1px horizontal dividers.
  - **View B (Device Detail)**: Host IP, online status badge, role classification, detected open service badges (`80:HTTP`, `22:SSH`, `53:DNS`), and response latency.
- **Hardware Controls**:
  - View A: `KEY3` moves selection / scrolls list, `KEY2` enters Detail View (or triggers full scan if empty), `KEY1` returns to SYS MENU.
  - View B: `KEY3` cycles devices, `KEY2` re-probes current device completely, `KEY1` returns to View A list.
- **Web UI Management**: Live LAN Devices card on port 80 displaying discovered hosts, open services, latency, and "Scan Local LAN" trigger button.

## 8. Games Subsystem Architecture (`GAMES`)
- **Extensible Games Hub (View A)**:
  - Header with `GAMES` and position badge (e.g. `1/7`).
  - 4-item scroll window with 1px horizontal dividers:
    - `21 BLACKJACK` (`blackjack.py`): Card game with chips badge (`$100`).
    - `GALAXY QUEST` (`galaxy.py`): Real-time space shooter with high score badge (`HI:X`).
    - `CYBER COPTER` (`copter.py`): Procedural cave runner with thrust & missiles (`HI:X`).
    - `NEON VIPER` (`viper.py`): 2-button relative-steer cyberpunk snake (`HI:X`).
    - `CYBER BRICK` (`brick.py`): Arkanoid / Breakout brick breaker (`HI:X`).
    - `LUNAR LANDER` (`lander.py`): Vector gravity descent simulator with landing pads (`HI:X`).
    - `PICO PONG` (`pong.py`): Player vs Pico CPU AI tennis match (`W:X`).
  - Navigation: `KEY3` cycles down/scrolls list, `KEY2` launches selected game, `KEY1` exits to SYS MENU.
- **Controls Across Games (View B)**:
  - `KEY1`: Always exits back to the Games Hub Menu.
  - In 21: `KEY3` = Hit, `KEY2` = Stand / Deal.
  - In Galaxy Quest: `KEY3` = Corridor lane, `KEY2` = Torpedo / Restart.
  - In Cyber Copter: `KEY3` = Thrust / Ascend, `KEY2` = Missile / Restart.
  - In Neon Viper: `KEY3` = Turn 90° Left, `KEY2` = Turn 90° Right / Restart.
  - In Cyber Brick: `KEY3` = Paddle Left, `KEY2` = Paddle Right / Restart.
  - In Lunar Lander: `KEY3` = Main Thruster, `KEY2` = RCS Attitude Tilt / Next Mission / Restart.
  - In Pico Pong: `KEY3` = Paddle Up, `KEY2` = Paddle Down / Restart.

## 9. Color Logo & Screensaver Architecture (`screensaver.py`)
- **Vibrant Multi-Color Logo**:
  - Pure vector graphics rendering of the official Raspberry Pi Pico W emblem without external bitmaps:
    - Upper emerald leaf cluster with highlights (`C_LEAF_HI`) and sepal collar.
    - 14 multi-toned ruby berry drupelets with 3D specular highlight and shadow dots.
    - Central RP2040 microcontroller silicon core with golden circuit pins and cyan glowing core.
    - Crisp high-contrast typography badge (`PICO W`).
- **Screensaver Bouncing Dynamics**:
  - Automatically activates after **1 minute (60 seconds)** of button inactivity.
  - Classic retro DVD-style smooth bouncing physics (`vx = 0.82`, `vy = 0.62`) avoiding LCD static image persistence.
  - Dynamic wall bounce triggers: cycles accent colors (Cyan, Emerald, Ruby, Amber, Violet) and spawns 5 sparkle particles.
  - Multi-plane background cosmic star dust drifting smoothly in deep space.
  - Subtle bottom ambient telemetry: system uptime and RP2040 core temperature.
- **Zero-Action Instant Wake**:
  - Pressing any key (`KEY3`, `KEY2`, or `KEY1`) wakes up the screen immediately.
  - The wake-up button press is consumed cleanly so it never triggers an accidental menu navigation or game action.
  - Background web server on port 80 and network probes run uninterrupted during screensaver.

## 10. Web Server & Persistence
- Non-blocking socket listener on Port 80 (`s.setblocking(False)`), integrated into the main loop without blocking UI rendering or button response.
- Post/Redirect/Get pattern (HTTP 303 to `/`) for all POST/GET mutations.
- Monitored sites persistently saved to `sites.txt`, YouTube config in `youtube.txt`, high scores in `gq_hiscore.txt`.

## 11. Flashing & Deployment
- Automated deployment via `upload_to_pico.py` on `COM3` at 115200 baud over MicroPython Raw REPL.

## 12. 🧠 Note for Next AI: Deep Dive into `picoui.py`
Dear future AI agent, when you read or modify `picoui.py`, keep these crucial architecture details in mind:

1. **The RGB565 Little-Endian Byte-Swap Rule**:
   - The ST7735S driver and RP2040 FrameBuffer send 16-bit color words over SPI in little-endian byte order (`[low, high]`).
   - If you write standard big-endian RGB565 `((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)`, the colors will look inverted/swapped on the LCD panel.
   - **Always** use `picoui.color565(r, g, b)` (which byte-swaps `((c & 0xFF) << 8) | ((c >> 8) & 0xFF)`) or the pre-calibrated `Theme` tokens (`Theme.PRIMARY`, `Theme.SUCCESS`, `Theme.BG`, etc.).

2. **The 6×8 High-Density Font Engine**:
   - Standard MicroPython `framebuf.text()` is fixed at 8×8 pixels, allowing only 16 characters across 128 px.
   - `picoui.py` has a built-in raster font dictionary `FONT_6X8` (ASCII 32..126) with 5×7 glyphs + 1px spacing = **6×8 pixels** (allowing **21 characters per line**).
   - Core functions:
     - `draw_text(lcd, text, x, y, color, font="6x8")`
     - `draw_centered(lcd, text, y, color, font="6x8")`
     - `draw_right(lcd, text, y, color, margin=4, font="6x8")`
     - `draw_big(lcd, text, x, y, color)`: 2× scaled (16×16) hero metric numbers, accelerated via `@micropython.native`.
   - **NEVER use artificial double-strike bolding** (`(x+1, y)`). On a 128×128 panel, double-striking closes glyph loops (`B`, `8`, `e`) into unreadable ink blobs. Use luminance contrast and container elevation (`Theme.SURFACE_ALT`) instead.

3. **No Footer / No Button Hint Rule**:
   - `picoui.footer()` is retained only for backward compatibility. **DO NOT call it** in active dashboard screens.
   - The user strictly requires a clean, distraction-free UI with zero key-mapping text (`K3:NEXT`, `K2:SELECT`, `K1:MENU`, `Press K2...`). Removing the 14px footer reclaims valuable vertical space (`y = 19..127`).

4. **Component Palette**:
   - `card(lcd, x, y, w, h, is_active=False, border_color=None)`: Elevated container with border.
   - `badge(lcd, x, y, text, variant="info", align_right=False)`: Borderless pill badge with faded tint background and bright high-contrast font. Zero boxes.
   - `progress_bar(lcd, x, y, w, h, percent, variant="primary")`: Bounded progress indicator.
   - `latency_chart(lcd, x, y, w, h, values, min_val=None, max_val=None)`: 16-bar response histogram with baseline axis and color-coded latency spikes.
   - `alert_modal(lcd, title, message, variant="info", prompt=None)`: Centered modal dialog.

5. **Memory Safety Contract**:
   - When passing time-series or latency data into `latency_chart()` or UI widgets, **always ensure the data array is bounded / circular** (e.g. `history[-16:]`). MicroPython heap fragmentation happens easily on RP2040; never store unbounded lists.

