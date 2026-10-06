# 🍓 Raspberry Pi Pico W System Monitor & Micro-UI

A high-performance, minimalist MicroPython dashboard and embedded network monitoring system designed for the **Raspberry Pi Pico W** and **Waveshare Pico-LCD-1.44** display.

---

## 📌 1. Hardware Baseline & Pinout

| Subsystem | Specification | Hardware Details |
| :--- | :--- | :--- |
| **Microcontroller** | Raspberry Pi Pico W | RP2040 Dual-Core ARM Cortex-M0+ @ 133 MHz, 264 KB SRAM, 2 MB Flash |
| **Wireless** | CYW43439 | 2.4 GHz 802.11n Wi-Fi, onboard antenna |
| **Display Panel** | Waveshare Pico-LCD-1.44 | 1.44" TFT LCD (ST7735S driver, 128×128 px, 16-bit RGB565 little-endian) |
| **SPI Interface** | SPI1 @ 10 MHz | `SCK=GP10`, `MOSI=GP11`, `DC=GP8`, `CS=GP9`, `RST=GP12`, `BL=GP13` |
| **Framebuffer** | 32 KB Static Buffer | Pre-allocated `32,768` bytes in RP2040 SRAM |
| **Physical Keys** | 3 Active Buttons | `KEY3` (GP3), `KEY2` (GP2), `KEY1` (GP17). **`KEY0` (GP15) is broken.** |

---

## 🎮 2. Physical Button Navigation Contract

> [!IMPORTANT]
> **Broken Button Rule**: `KEY0` (GP15) is physically damaged and non-functional. It is hardcoded to `False` in `lcd1in44.py`. The UI and applications **must never** depend on, listen to, or block on `KEY0`.

All interactions are strictly optimized for a 3-button navigation model:

| Button | Pin | Position | Global Role | Sites Monitor (List) | Sites Monitor (Detail) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`KEY3`** | GP3 | Top | **Next / Cycle / Up** | Move cursor (1–16) | Next website detail |
| **`KEY2`** | GP2 | Middle | **Select / Action** | Enter Site Detail view | Re-probe / Re-check site |
| **`KEY1`** | GP17 | Bottom | **Back / Return** | Exit to Main Menu | Return to Sites List |

---

## 🎨 3. UI Design Principles & Aesthetic Rules

1. **Zero Key Map / Hint Text Anywhere**:
   - **Never** render button hint text, footer action bars (`K3:NEXT`, `K2:SELECT`, `K1:MENU`), or prompts (`Press K2...`, `K1:OK`).
   - The user interface must remain clean, uncluttered, and professional at all times.

2. **Ultra-Minimalist Horizontal-Line Architecture (Zero Boxes)**:
   - **Never use bounding card boxes (`ui.card`, `lcd.rect`)** across any screen in the UI.
   - **Faded Pill Badges (Zero Border Boxes)**: Status badges (`ui.badge`) use a borderless rounded pill with a subtle faded dark-tint background and bright, high-contrast font. Hard bounding outline boxes (`lcd.rect`) are eliminated.
   - **1px Horizontal Dividers**: Separate sections and rows using clean 1-pixel horizontal lines (`lcd.hline`) in `Theme.BORDER`.
   - **Main Menu**: 5-category list with horizontal lines separating each row (`DEV`, `PING`, `SITES`, `YT`, `WEB`), active row indicated by `>` cursor and highlighted accent line (`start_y = 23`, `row_h = 20`).
   - **Combined DEV Subsystem**: Like `SITES`, `DEV` features a dedicated Landing Page with selectable subpages (`CORE`, `NET`, `MEM`), where KEY2 enters the full detail view and KEY1 returns to the landing page.
   - **Detail Screens (DEV Subpages, Ping, Sites, YT, Web)**: Divided into clean sections by 1px horizontal lines on a unified dark canvas.
   - **Progress Bars**: Sleek track lines without outer border boxes.

3. **Screen Canvas Budget (128 × 128 px)**:
   - **Header Bar**: `y = 0..18` (18 px height) with accent line at `y = 18`.
   - **Usable Canvas**: `y = 19..127` (109 px available height).

4. **Typography & Anti-Smudge Rule**:
   - **High-Density 6×8 Font**: Custom raster font (5×7 glyph + 1px spacing) providing **21 characters per line** rendered via `@micropython.native`.
   - **1-Pixel Crisp Strokes**: Never use artificial `(x+1, y)` bold double-strikes (which blur small glyphs). Contrast is achieved using luminance and container elevation (e.g. bright text on deep Slate-900 surface).
   - **Hero Metrics**: 2× scaled numbers for sensor readouts, ping latency, and clock displays.

5. **Abbreviated Technical Vocabulary Rule (No Long Words)**:
   - On the 128×128 panel, verbose labels waste spatial budget. Use standard concise abbreviations:
     - `Temperature` -> `Tmp` (e.g. `CORE TMP`)
     - `Device` -> `Dev`
     - `Network` -> `Net`
     - `Memory` -> `Mem`
     - `Allocated` -> `Alloc` (e.g. `Alloc: 42KB`)
     - `Connecting` -> `Conn...`
     - `Server` -> `Srv` (e.g. `WEB SRV`)
     - `Protocol` -> `Proto` (e.g. `Proto: ICMP`)
     - `Cloudflare` -> `CF` (e.g. `CF PING`)
     - `Min / Max` -> Char-sized icons `↓` / `↑` (zero text labels)

---

## 💾 4. Memory Management & Data Retention Rules

> [!CAUTION]
> **Limited Heap**: MicroPython on RP2040 operates with ~100–120 KB of free heap after boot and display framebuffer allocation. Memory leaks or fragmented allocations will crash the board.

1. **Circular / Capped Buffer Rule**:
   - **Charts & Histograms**: Any data series plotted on screen (e.g., latency history in `site_history`) **must be capped at a fixed maximum length** (e.g., `MAX_POINTS = 16` or `20`). Always prune with FIFO `pop(0)` or circular indexing when appending new samples.
   - **Telemetry & Logs**: Telemetry samples, circular buffers, or repeating job records must have strict upper boundaries. Unbounded list appending is strictly prohibited.
2. **Periodic Garbage Collection**:
   - Call `gc.collect()` regularly, especially before/after heavy network sockets, DNS resolution, and HTTP requests.
3. **No Dynamic Framebuffer Reallocation**:
   - The ST7735S 32 KB framebuffer is allocated once at startup. Do not allocate secondary full-screen buffers.

---

## 🌐 5. Sites Monitor & Network Architecture

1. **View A — 2-Column NOC Overview**:
   - Displays up to **16 monitored websites** simultaneously on a single screen (8 rows × 2 columns).
   - Clean vertical divider at `x = 63`.
   - Each site entry features a 4×4 status square:
     - 🟢 **Green (`Theme.SUCCESS`)**: Online (HTTP 200/301 or TCP-OK)
     - 🔴 **Red (`Theme.DANGER`)**: Offline / Timeout
     - 🟡 **Yellow (`Theme.WARNING`)**: Pending probe
   - Automatic paging if more than 16 sites are configured.

2. **View B — Ultra-Minimalist Site Detail**:
   - **Zero Next-Site Clutter & No Boxes**: Unified canvas background without enclosing cards.
   - **Section 1**: Single-line website URL + port, hero status badge (`UP` / `DOWN`), latency, and HTTP response code.
   - **1px Horizontal Divider**: Clean separation line at `y = 59`.
   - **Section 2 (Min & Max)**: Character-sized 5×7 arrow icons (`↓` for Min in green, `↑` for Max in amber) without `MIN:` or `MAX:` text labels.
   - **1px Horizontal Divider**: Clean separation line at `y = 78`.
   - **Section 3 (Histogram Chart)**: 16-bar response time histogram chart with baseline axis and color-coded spike detection.

3. **Embedded Web Server (Port 80)**:
   - Non-blocking socket listener running inside the main event loop (`s.setblocking(False)`).
   - Supports live configuration: Add website with custom port (defaults to `80`, supports `443` HTTPS TCP check, `8080`, `3001`, etc.), remove websites, adjust LCD backlight brightness, configure YouTube channel/key, and push remote alert messages.
   - Implements **Post/Redirect/Get (HTTP 303)** pattern to prevent duplicate form submissions.
   - Saves websites persistently to `sites.txt` and YouTube config to `youtube.txt` on the Pico's flash storage.

---

## ⚡ 6. Internet Connection & Quality Monitor (`PING`)

- **View A — 8-Site NOC Landing Page**:
  - Displays all 8 critical network checkpoints across 8 clean rows (`row_h = 13`):
    - `GW` (Local Router Gateway)
    - `CF` (Cloudflare `1.1.1.1`)
    - `GOOG` (Google `8.8.8.8`)
    - `CLOUD` (`caydas.cloud` — Personal Remote Server)
    - `QUAD9` (Quad9 `9.9.9.9`)
    - `OPEN` (OpenDNS `208.67.222.222`)
    - `LUMEN` (Lumen `4.2.2.2`)
    - `CF2` (Cloudflare `1.0.0.1`)
  - Displays target abbreviation, address, and color-coded latest ping time.
  - Active selection highlighted with `>` cursor and cyan line.
  - Round-robin background auto-pinging refreshes all 8 targets continuously.
- **View B — Single-Target Quality Detail**:
  - Hero latency in bold digits + borderless faded Quality Grade pill badge (`GREAT` <30ms, `GOOD` <60ms, `FAIR` <120ms, `POOR` >=120ms, `LOSS`).
  - Consecutive packet jitter (`JIT: Xms`).
  - Char-sized Min (`↓`) & Max (`↑`) arrows + Packet Loss rate (`LOSS X%`).
  - **16-Bar Response Time Histogram Chart**: Live pulse telemetry updating every 2.0s.
- **Hardware Controls**:
  - On View A: `KEY3` moves cursor, `KEY2` opens Detail View, `KEY1` exits to SYS MENU.
  - On View B: `KEY3` cycles targets, `KEY2` sends instant re-probe, `KEY1` returns to View A Landing Page.

---

## 📺 7. YouTube Channel Tracker

- **API Integration**: Connects directly to Google's official YouTube Data API v3 (`https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&...`) over hardware TLS (port 443) via MicroPython `ssl.wrap_socket`.
- **Handle & Channel ID Support**: Automatically detects handles (`@yourchannel` or `yourchannel`) or Channel IDs (`UC...`).
- **Telemetry Displayed**:
  - Hero Subscriber count in bold (`Theme.DANGER` rose) + `SUBS` badge and `VIDS` count.
  - Lifetime Total Views (`VIEWS`) and tracked session gain (`+X GAIN`).
  - Min & Max interval delta views with char-sized `↓` / `↑` arrow icons.
  - 16-bar genuine views histogram chart with color-coded spikes on a 1px baseline axis.
  - Polling status (`SYNC 10m` background poll, ~144 quota units/day, well under YouTube's free 10,000 quota limit).
- **Persistence**: Saved persistently to `yt_views.txt` and `youtube.txt` on flash storage.
- **Dynamic Web Configuration**: Enter API key and channel handle directly from the browser at `http://<pico_ip>/` — instantly saves to `youtube.txt` and updates the LCD display without reflashing.

---

## 🚀 7. Project Files & Deployment

```
pico/
├── lcd1in44.py       # Waveshare ST7735S display driver & button debouncing
├── picoui.py         # Tailwind design tokens, 6x8 font, arrows, & latency chart
├── main.py           # Core dashboard app, web server, YouTube tracker & NOC monitor
├── secrets.py        # Wi-Fi SSID, Password, and fallback YouTube API credentials
├── upload_to_pico.py # Automated Raw-REPL deployment tool over COM3 (115200 baud)
├── sites.txt         # Persistent monitored website entries
├── youtube.txt       # Persistent YouTube channel ID and API key configuration
├── AGENTS.md         # Engineering guidelines, design tokens, & memory rules
└── README.md         # Architecture, navigation contract, & project documentation
```

### Flashing to Pico W
```bash
python upload_to_pico.py
```
This utility:
1. Connects to `COM3` at 115200 baud.
2. Interrupts the board into MicroPython Raw REPL (`Ctrl-C`, `Ctrl-A`).
3. Uploads `lcd1in44.py`, `ssd1306.py`, `secrets.py`, `picoui.py`, and `main.py` in 512-byte chunks.
4. Soft-reboots the MCU (`Ctrl-B`, `Ctrl-D`) into production mode.

---

## 🎨 7. Notes on `picoui.py` Micro-UI Framework

For any developer or AI extending the user interface:

- **Hardware Little-Endian Color Swap**: RP2040 `framebuf` requires little-endian byte-swapped RGB565 words (`((c & 0xFF) << 8) | ((c >> 8) & 0xFF)`). Always use `Theme` tokens or `color565(r, g, b)`.
- **6×8 High-Density Font**: Built-in 5×7 glyph raster dictionary yielding 21 characters/line (compared to MicroPython's 16 chars/line). Fast assembly rendering via `@micropython.native`.
- **Anti-Smudge Typography**: Crisp 1-pixel strokes only. Never simulate bolding via double-striking; use container elevation (`Theme.SURFACE_ALT`) and luminance contrast instead.
- **Component Palette**: Reusable cards, progress bars, pill badges, and a 16-bar response histogram (`latency_chart()`) with color-coded spike detection.
- **No-Key-Map Rule**: Never display button hints or footers (`K3:...`, `K2:...`). The screen layout takes full advantage of the entire 109px height without footers.

