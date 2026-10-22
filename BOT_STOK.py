
import os
import random
import re
import json
import logging
import asyncio
import requests
import time
import contextlib
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
try:
    from playwright.async_api import async_playwright, TimeoutError as ATimeout
    import aiohttp 
except ImportError as e:
    import sys
    # Fallback checking
    if "aiohttp" in str(e):
         print("❌ Library aiohttp belum terinstall. Install dulu: pip install aiohttp")
         sys.exit(1)
    import sys
    if "DLL load failed" in str(e):
        print("\n" + "="*60)
        print("❌ ERROR: Gagal memuat library sistem (DLL Load Failed).")
        print("Kemungkinan besar Windows Anda belum terinstall 'Visual C++ Redistributable'.")
        print("Solusi: Silakan install 'vc_redist.x64.exe' dari Microsoft.")
        print("="*60 + "\n")
    raise e

print("✅ Library sistem berhasil dimuat.\\n", flush=True)
from html import escape

# ===================== KONFIGURASI =====================
SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / "BOT_STOK.env"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)] if 'sys' in locals() else [logging.StreamHandler()]
)

load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
HEADLESS = os.getenv("HEADLESS", "True").lower() not in ("0", "false", "False")
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()

BASE_URL = "https://subsiditepatlpg.mypertamina.id"
ACCOUNTS_FILE = SCRIPT_DIR / "accounts.json"

if not BOT_TOKEN:
    logging.warning("⚠️ BOT_TOKEN belum diset di BOT_STOK.env")

# ===================== HELPER FUNCTIONS =====================
def load_accounts():
    if not ACCOUNTS_FILE.exists(): return {}
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Gagal load accounts: {e}")
        return {}

def save_accounts(data):
    try:
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Gagal save accounts: {e}")
        return False

def parse_credential_line(s: str):
    parts = s.split("|", 1)
    if len(parts) != 2: return None, None
    email, pin = parts[0].strip(), parts[1].strip()
    return (email, pin) if (email and pin) else (None, None)

def angka_awal(s: str) -> int:
    m = re.search(r"(\d+)", s or "")
    if m:
        return int(m.group(1))
    return -1

def get_stok_tanda(jumlah: int) -> str:
    if jumlah < 0: return "❓"
    if jumlah <= 50: return "🟢"
    if jumlah <= 90: return "⚠️"
    return "🚨🚨"

def format_one_result(nama: str, stok: str) -> str:
    jumlah = angka_awal(stok)
    if jumlah < 0:
        body = "Tidak Diketahui ❓"
    elif jumlah == 0:
        body = "✅Done"
    else:
        tanda = get_stok_tanda(jumlah)
        body = f"{stok} Tbg {tanda}"
    return f"<b>{escape(nama)}</b> | {escape(body)}"

# ===================== ASYNC TELEGRAM HELPERS =====================
async def tg_send_async(text, chat_id, markup=None):
    if not chat_id or not BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if markup: payload["reply_markup"] = json.dumps(markup)
    
    try:
        # Disable SSL Verify (Workaround for Local/SSL Issues)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=payload, timeout=20) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    logging.error(f"TG Send Failed: {resp.status} - {err_text}")
    except Exception as e:
        logging.error(f"TG Send Error: {e}")

async def tg_send_menu_async(chat_id, text, state="MAIN"):
    if state == "MAIN":
        buttons = [
            [{"text": "CEK LAPORAN PANGKALAN"}],
            [{"text": "INPUT AKUN"}]
        ]
    else:
        buttons = [[{"text": "KEMBALI"}]]
    
    kb = {
        "keyboard": buttons, 
        "resize_keyboard": True,
        "one_time_keyboard": False
    }
    await tg_send_async(text, chat_id, markup=kb)

def clear_screen():
    """Membersihkan layar terminal"""
    os.system('cls' if os.name == 'nt' else 'clear')

# ===================== CORE LOGIC: CEK STOK =====================
# Diambil dari BOT1_CAPTCHA.py > cek_stok_satu_async

async def _login_and_setup(browser, email, pin):
    """Helper: Login dan navigate ke valid state. Return (context, page, nama_pangkalan)"""
    context = await browser.new_context()
    page = await context.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(60000)
    
    try:
        logging.info(f"[{email}] Mulai proses login...")
        # === LOGIN ===
        logging.info(f"[{email}] Navigasi ke URL Login...")
        await page.goto(f"{BASE_URL}/merchant-login", wait_until="domcontentloaded")
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        logging.info(f"[{email}] Isi Form Login...")
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.get_by_role("textbox", name="Nomor Ponsel atau Email").fill(email)
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.get_by_role("textbox", name="PIN").fill(pin)
        await page.wait_for_timeout(random.randint(3000, 4000))
        
        logging.info(f"[{email}] Klik Login...")
        await page.get_by_role("button", name="MASUK").click()
        
        # === CEK HASIL LOGIN ===
        logging.info(f"[{email}] Menunggu masuk dashboard...")
        login_success = False
        for check in range(60): # Max 60 detik
            await page.wait_for_timeout(1000)
            try:
                # Cek dashboard loaded (indikator stok tabung visible)
                if await page.locator("text=/\\b\\d+\\s+Tabung\\b/i").first.is_visible(timeout=500):
                    login_success = True
                    logging.info(f"[{email}] Dashboard muncul!")
                    break
            except: pass
            
        if not login_success:
            raise Exception("Login timeout/gagal: Dashboard tak kunjung muncul.")

        logging.info(f"Akun {email}: Login sukses! Stabilisasi 2s...")
        await page.wait_for_timeout(2000) # Stabilize

        # === AMBIL NAMA PANGKALAN ===
        nama = email
        try:
            nama_pangkalan = await page.evaluate("""
                () => {
                    const allElements = document.querySelectorAll('*');
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;
                    let topMostName = null;
                    let topMostTop = Infinity;
                    for (let el of allElements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > viewportWidth * 0.5 && rect.top < viewportHeight * 0.3 && rect.height > 0) {
                            const text = el.innerText?.trim() || '';
                            if (text && text.length >= 5 && text.length < 100) {
                                const words = text.split(/\\s+/);
                                if (words.length >= 2 && words.length <= 5 && words.every(w => /^[A-Z]/.test(w))) {
                                    if (rect.top < topMostTop) {
                                        topMostTop = rect.top;
                                        topMostName = text;
                                    }
                                }
                            }
                        }
                    }
                    return topMostName;
                }
            """)
            if nama_pangkalan:
                # Ambil baris pertama, bersihkan whitespace, dan pastikan tidak duplikat
                raw_name = nama_pangkalan.strip()
                if '\n' in raw_name:
                    lines = raw_name.split('\n')
                    # Cek if lines are duplicates (e.g. "NAME\nNAME")
                    if len(lines) > 1 and lines[0].strip() == lines[1].strip():
                         nama = lines[0].strip()
                    else:
                         nama = lines[0].strip()
                else:
                    nama = raw_name
        except: pass

        return context, page, nama

    except Exception as e:
        await context.close()
        raise e

async def _set_date_filter(page):
    """Helper: Set filter tanggal (Awal Bulan - Hari Ini)"""
    now = datetime.now()
    day_str = str(now.day)
    # month_str = now.strftime("%B") # Indo locale issue potentially, relying on UI state
    
    # Buka Date Picker (Cari button yang ada di area filter)
    # Codegen approach: page.get_by_role("button", name="Jan 2026 – 31 Jan 2026").click()
    # Dynamic approach: Cari button terdekat dengan label "Atur Rentang Waktu" atau text range tanggal
    try:
        # Klik input date picker
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("button.mantine-DatePickerInput-input").first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        # Klik Tanggal 1 (Start)
        # Cari button tanggal 1 yang visible dan enabled
        # Filter untuk hari di bulan aktif (bukan outside)
        await page.locator("button.mantine-Day-day:not([data-outside])").get_by_text("1", exact=True).first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        # Klik Tanggal Hari Ini (End)
        await page.locator("button.mantine-Day-day:not([data-outside])").get_by_text(day_str, exact=True).first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
    except Exception as e:
        logging.warning(f"Gagal set tanggal: {e}")
        # Lanjut saja, mungkin range default sudah benar/cukup

async def cek_stok_satu_async(browser, email: str, pin: str):
    try:
        context, page, nama = await _login_and_setup(browser, email, pin)
    except Exception as e:
        logging.warning(f"Akun {email} gagal login: {e}")
        return None

    try:
        stok = "Tidak Diketahui"
        for _ in range(5):
            try:
                el = page.locator("text=/\\b\\d+\\s+Tabung\\b/i").first
                if await el.is_visible():
                    txt = await el.inner_text()
                    m = re.search(r"(\d+)", txt)
                    if m:
                        stok = m.group(1)
                        break
            except: pass
            await page.wait_for_timeout(2000)
        
        logging.info(f"Akun {email}: {nama} | Stok = {stok} Tabung")
        await context.close()
        return (nama, stok)
    except Exception as e:
        await context.close()
        logging.warning(f"Error cek stok {email}: {e}")
        return None

async def cek_rekap_satu_async(browser, email: str, pin: str):
    """Fitur Rekap Penjualan: Total Tabung Terjual"""
    try:
        context, page, nama = await _login_and_setup(browser, email, pin)
    except Exception as e:
        return None

    try:
        logging.info(f"{nama}: Buka Menu Rekap Penjualan...")
        # Menu Navigasi
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Laporan Penjualan$")).first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Rekap Penjualan$")).nth(1).click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        # Filter Tanggal
        await _set_date_filter(page)
        logging.info(f"{nama}: Tunggu data loading 3 detik...")
        await page.wait_for_timeout(3000)
        
        # Scrape Data (Total Tabung Terjual)
        total_stok = "Tidak Diketahui"
        try:
             # Cari text "Total Tabung Terjual" dan ambil angka di dekatnya
             # Biasanya di footer table/card
             # Locator strategy: Cari text "Total Tabung Terjual", lalu sibling/containernya
             el = page.locator("text=Total Tabung Terjual").first
             if await el.is_visible():
                  # Asumsi struktur: <div><span>Total...</span><span>1820 Tbg</span></div>
                  # Atau parent contains text. 
                  # Ambil text parentnya
                  parent = el.locator("..")
                  full_text = await parent.inner_text()
                  m = re.search(r"(\d+)\s*Tbg", full_text)
                  if m:
                      total_stok = m.group(1)
        except Exception as e:
            logging.warning(f"Gagal scrape total: {e}")

        # Format Result: "NAAMA | Total: 100"
        result_str = f"Total: {total_stok} Tabung"
        
        await context.close()
        return (nama, result_str)

    except Exception as e:
        await context.close()
        logging.warning(f"Error rekap {email}: {e}")
        return None

async def cek_jenis_pelanggan_satu_async(browser, email: str, pin: str):
    """Fitur Laporan Jenis Pelanggan"""
    try:
        context, page, nama = await _login_and_setup(browser, email, pin)
    except Exception: return None

    try:
        logging.info(f"{nama}: Buka Menu Jenis Pelanggan...")
        # Menu Navigasi
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Laporan Penjualan$")).first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Rekap Penjualan$")).nth(1).click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        # Klik Tab JENIS PELANGGAN
        await page.get_by_role("tab", name="JENIS PELANGGAN").click()
        await page.wait_for_timeout(random.randint(2000, 3000))

        # Filter Tanggal
        await _set_date_filter(page)
        logging.info(f"{nama}: Tunggu data loading 3 detik...")
        await page.wait_for_timeout(3000)
        
        # Scrape Data (Python Side Parsing)
        try:
            # Ambil seluruh teks halaman
            content = await page.inner_text("body")
            
            # Helper regex
            def get_val(label):
                # Cari Label ... angka ... Tbg
                pattern = re.compile(re.escape(label) + r".{0,100}?(\d+)\s*Tbg", re.IGNORECASE | re.DOTALL)
                match = pattern.search(content)
                if match:
                    return match.group(1)
                return "0"

            targets = {
                "Rumah Tangga": "RT", 
                "Usaha Mikro": "UM", 
                "Petani Sasaran": "PS",
                "Nelayan Sasaran": "NS", 
                "Pengecer": "P", 
                "Subpangkalan": "SP"
            }
            
            parts = []
            order = ["Rumah Tangga", "Usaha Mikro", "Petani Sasaran", "Nelayan Sasaran", "Pengecer", "Subpangkalan"]
            
            for key in order:
                val = get_val(key)
                if val != "0":
                    code = targets[key]
                    parts.append(f"{code} : {val} Tbg")
            
            # Total Tabung Terjual
            total_val = get_val("Total Tabung Terjual")
            total_str = f"Total Tabung Terjual : {total_val} Tbg"
            
            line_str = " | ".join(parts)
            
            if line_str:
                body = f"{line_str}\n{total_str}"
            else:
                body = total_str
            
        except Exception as e:
            logging.error(f"Python Scraping error: {e}")
            body = f"Gagal scrape data: {e}"

        await context.close()
        return (nama, body)

    except Exception as e:
        await context.close()
        logging.warning(f"Error jenis pelanggan {email}: {e}")
        return None

async def cek_laporan_lengkap_satu_async(browser, email: str, pin: str):
    """Gabungan Cek Stok & Jenis Pelanggan"""
    try:
        context, page, nama = await _login_and_setup(browser, email, pin)
    except Exception: return None

    try:
        # 1. AMBIL STOK (Logic dari cek_stok)
        stok = "Tidak Diketahui"
        try:
            for _ in range(5):
                el = page.locator("text=/\\b\\d+\\s+Tabung\\b/i").first
                if await el.is_visible():
                    txt = await el.inner_text()
                    m = re.search(r"(\d+)", txt)
                    if m:
                        stok = m.group(1)
                        break
                await page.wait_for_timeout(2000)
        except: pass
        
        logging.info(f"{nama}: Stok = {stok}. Lanjut cek laporan...")

        # 2. NAVIGASI KE LAPORAN
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Laporan Penjualan$")).first.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        await page.locator("div").filter(has_text=re.compile(r"^Rekap Penjualan$")).nth(1).click()
        await page.wait_for_timeout(random.randint(2000, 3000))
        
        # Klik Tab JENIS PELANGGAN
        await page.get_by_role("tab", name="JENIS PELANGGAN").click()
        await page.wait_for_timeout(random.randint(2000, 3000))

        # Filter Tanggal
        await _set_date_filter(page)
        logging.info(f"{nama}: Tunggu data loading 3 detik...")
        await page.wait_for_timeout(3000)
        
        # 3. SCRAPE DATA Laporan
        try:
            content = await page.inner_text("body")
            
            def get_val(label):
                pattern = re.compile(re.escape(label) + r".{0,100}?(\d+)\s*Tbg", re.IGNORECASE | re.DOTALL)
                match = pattern.search(content)
                if match: return match.group(1)
                return "0"

            targets = {
                "Rumah Tangga": "RT", "Usaha Mikro": "UM", "Petani Sasaran": "PS",
                "Nelayan Sasaran": "NS", "Pengecer": "P", "Subpangkalan": "SP"
            }
            
            parts = []
            order = ["Rumah Tangga", "Usaha Mikro", "Petani Sasaran", "Nelayan Sasaran", "Pengecer", "Subpangkalan"]
            
            for key in order:
                val = get_val(key)
                if val != "0":
                    code = targets[key]
                    parts.append(f"{code} : {val} Tbg")
            
            total_val = get_val("Total Tabung Terjual")
            
        except Exception as e:
            logging.error(f"Scraping error: {e}")
            parts = []
            total_val = "0"

        await context.close()
        
        # 4. FORMAT OUTPUT
        # 「 Pandu Wijaya 」
        # ၊| Stok: 0 Tbg
        # ၊| RT : 497 Tbg | UM : 18 Tbg
        # ၊| Total Tabung Terjual : 515 Tbg
        
        jumlah = angka_awal(stok)
        tanda = get_stok_tanda(jumlah) if jumlah >= 0 else "❓"
        
        header = f"╭─〔<b>*{nama}*</b> 〕"
        line_stok = f"┊・Stok: {stok} Tbg {tanda}"
        line_jenis = f"┊・{' | '.join(parts)}" if parts else "၊| Nihil"
        line_total = f"┊・Total Tabung Terjual : {total_val} Tbg\n╰┈"
        
        full_text = f"{header}\n{line_stok}\n{line_jenis}\n{line_total}"
        return (nama, full_text)

    except Exception as e:
        await context.close()
        logging.warning(f"Error laporan lengkap {email}: {e}")
        return None


async def process_batch_async(creds: list, worker_func, max_workers: int = 1):
    """Proses batch akun secara paralel dengan worker function dinamis"""
    if not creds: return [], []

    results = []
    failures = []
    sem = asyncio.Semaphore(max_workers)

    async with async_playwright() as p:
        logging.info(f"🚀 Meluncurkan Browser (Headless={HEADLESS})...")
        try:
            browser = await asyncio.wait_for(p.chromium.launch(
                headless=HEADLESS,
                slow_mo=2500,
                timeout=30000 
            ), timeout=35) # 35s max wait for launch
            logging.info("✅ Browser berhasil diluncurkan.")
        except Exception as e:
            logging.error(f"❌ Gagal meluncurkan browser: {e}")
            return [], [f"System Error: Browser Launch Failed ({e})"]

        logging.info("Tunggu 3 detik (warmup)...")
        await asyncio.sleep(3)

        async def one_account(email: str, pin: str):
            try:
                async with sem:
                    # Timeout 3.5 menit per akun
                    res = await asyncio.wait_for(
                        worker_func(browser, email, pin),
                        timeout=210 
                    )

                    # Jeda 3 detik sebelum lanjut (User Request)
                    logging.info("⏳ Jeda 3 detik...")
                    await asyncio.sleep(3)

                if res:
                    results.append(res)
                    return
            except ATimeout:
                logging.warning(f"Timeout untuk akun {email}")
            except Exception as e:
                logging.warning(f"Error untuk akun {email}: {e}")
            
            failures.append(f"{email}|{pin}")

        tasks = [asyncio.create_task(one_account(em, pn)) for (em, pn) in creds]
        await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    return results, failures

async def send_stok_report_async(results: list, chat_id: str):
    """Kirim laporan stok ke Telegram"""
    if not results:
        await tg_send_async("❌ Tidak ada hasil yang berhasil diambil.", chat_id=chat_id)
        return
    
    results.sort(key=lambda x: angka_awal(x[1]), reverse=True)
    lines = [f"{i}. {format_one_result(nm, sk)}" for i, (nm, sk) in enumerate(results, 1)]
    
    try:
        html_text = "<b>📊 Laporan Stok Tabung</b>\n\n" + "\n".join(lines)
        await tg_send_async(html_text, chat_id)
    except Exception as e:
        logging.error(f"Gagal kirim laporan: {e}")
        await tg_send_async("❌ Gagal mengirim laporan stok.", chat_id)

# ===================== MAIN ASYNC LOOP =====================

# Global user states for async context
user_states = {}

async def handle_update(upd):
    """Handle satu pesan update Telegram secara async"""
    msg = upd.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "").strip()
    
    if not chat_id or not text: return
    
    # Pengecekan Akses (ALLOWED_CHAT_ID)
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        logging.warning(f"Akses ditolak untuk chat_id: {chat_id}")
        return
    
    # Simple State Management
    state = user_states.get(chat_id, "MAIN")
    logging.info(f"[{chat_id}] Msg: {text} | State: {state}")
    
    # --- COMMAND HANDLER ---
    if text.lower() == "/start":
        user_states[chat_id] = "MAIN"
        await tg_send_menu_async(chat_id, "👋 Halo! Ini Bot Khusus Cek Stok.\nSilakan pilih menu:", "MAIN")
        return

    if text.upper() == "KEMBALI":
        user_states[chat_id] = "MAIN"
        await tg_send_menu_async(chat_id, "Menu Utama", "MAIN")
        return

    # --- STATE HANDLER ---
    if state == "MAIN":
        if text == "CEK STOK TABUNG":
            user_states[chat_id] = "WAITING_STOK"
            await tg_send_menu_async(chat_id, "🔥 <b>CEK STOK TABUNG</b>\nMasukkan akun (email|pin). Bisa banyak baris.", "WAITING")
            
        elif text == "CEK LAPORAN PANGKALAN":
            user_states[chat_id] = "WAITING_JP"
            await tg_send_menu_async(chat_id, "👥 <b>CEK LAPORAN PANGKALAN</b>\n\nMasukkan akun (email|pin).", "WAITING")
            
        elif text == "INPUT AKUN":
            user_states[chat_id] = "WAITING_INPUT_AKUN"
            await tg_send_menu_async(chat_id, "📝 <b>INPUT AKUN</b>\n\nMasukkan akun (email|pin).\n\nData ini akan diproses otomatis setiap Jam 08:05.", "WAITING")

        else:
            await tg_send_async("Gunakan tombol menu ya.", chat_id)

    elif state in ("WAITING_STOK", "WAITING_JP", "WAITING_INPUT_AKUN"):
        if "|" in text:
            if state == "WAITING_INPUT_AKUN":
                accounts_data = load_accounts()
                lines = text.splitlines()
                valid_creds = []
                for line in lines:
                    em, pn = parse_credential_line(line)
                    if em and pn:
                         valid_creds.append(f"{em}|{pn}")
                
                if valid_creds:
                     accounts_data[chat_id] = valid_creds
                     save_accounts(accounts_data)
                     user_states[chat_id] = "MAIN"
                     await tg_send_menu_async(chat_id, f"✅ Sukses menyimpan {len(valid_creds)} akun untuk proses otomatis harian.", "MAIN")
                else:
                     await tg_send_async("❌ Tidak ada akun valid yang ditemukan.", chat_id)
            else:
                # Process Request immediately in background
                asyncio.create_task(process_user_request(chat_id, text, state))
                
                # Reset state immediately or keep waiting? 
                # Better reset to MAIN to avoid double input, user can click menu again.
                user_states[chat_id] = "MAIN"
                await tg_send_menu_async(chat_id, "⏳ SABAR BANG....!", "MAIN")
        else:
             await tg_send_async("❌ Format salah. Wajib pakai separator '|'. Contoh: email|pin", chat_id)

async def process_user_request(chat_id, text, state):
    """Background task untuk memproses request user"""
    lines = text.splitlines()
    creds = []
    invalid_lines = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        em, pn = parse_credential_line(line)
        if em and pn:
            creds.append((em, pn))
        else:
            invalid_lines.append(line)
    
    if creds:
        worker = cek_stok_satu_async if state == "WAITING_STOK" else cek_laporan_lengkap_satu_async
        label = "Stok Tabung" if state == "WAITING_STOK" else "Laporan Lengkap"
        
        await tg_send_async(f"🚀 Okee bang proses {label} untuk {len(creds)} akun...", chat_id)
        
        try:
            # PENTING: process_batch_async sudah async, jadi kita await langsung.
            # Karena ini berjalan di dalam create_task, dia tidak memblokir user lain.
            results, failures = await process_batch_async(creds, worker, max_workers=1)
            
            # Report
            if state == "WAITING_STOK":
                await send_stok_report_async(results, chat_id)
            else:
                if results:
                    def get_stok_val(txt):
                        m = re.search(r"Stok:\s*(\d+)", txt)
                        return int(m.group(1)) if m else -1
                    results.sort(key=lambda x: get_stok_val(x[1]), reverse=True)
                    msg_lines = [val + "\n" for nm, val in results]
                    full_msg = "\n".join(msg_lines)
                    
                    if len(full_msg) > 4000:
                        chunks = [msg_lines[i:i+5] for i in range(0, len(msg_lines), 5)]
                        for chunk in chunks:
                             await tg_send_async("\n".join(chunk), chat_id)
                    else:
                        await tg_send_async(full_msg, chat_id)
                else:
                    await tg_send_async("❌ Tidak ada hasil.", chat_id)

            if failures:
                fail_msg = "⚠️ Gagal/Timeout:\n" + "\n".join(failures[:10])
                if len(failures) > 10: fail_msg += f"\n...dan {len(failures)-10} lainnya"
                await tg_send_async(fail_msg, chat_id)
                
            if invalid_lines:
                inv_msg = "⚠️ Format salah (skip):\n" + "\n".join(invalid_lines[:5])
                await tg_send_async(inv_msg, chat_id)

            await tg_send_async("✅ Done bang.!", chat_id)
            
            # Request USER: Pembersihan log
            clear_screen()
            logging.info("🧹 Terminal logs cleaned.")

        except Exception as e:
            logging.error(f"Error task user {chat_id}: {e}")
            await tg_send_async(f"❌ Terjadi kesalahan sistem: {e}", chat_id)
    else:
        await tg_send_async("❌ Tidak ada akun valid yang ditemukan.", chat_id)


async def daily_scheduler():
    while True:
        now = datetime.now()
        target = now.replace(hour=8, minute=5, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        logging.info(f"⏳ Menunggu scheduler jam 08:05... {(wait_seconds/3600):.2f} jam lagi.")
        
        try:
            await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            break
        
        logging.info("⏰ Waktu menunjukkan 08:05! Memulai proses otomatis harian...")
        accounts_data = load_accounts()
        for chat_id, account_list in accounts_data.items():
            if not account_list: continue
            creds_text = "\n".join(account_list)
            
            try:
                await tg_send_async("⏳ <b>PROSES OTOMATIS HARIAN</b> (08:05)\nMemulai pengecekan laporan pangkalan...", chat_id)
                asyncio.create_task(process_user_request(chat_id, creds_text, "WAITING_JP"))
            except Exception as e:
                logging.error(f"Gagal memicu proses otomatis untuk {chat_id}: {e}")
        
        # Beri jeda sedikit agar tidak langsung terpicu lagi di detik yang sama
        await asyncio.sleep(60)

async def main_loop():
    logging.info(f"🤖 Bot Started Async Mode (PID: {os.getpid()})")
    logging.info(f"Headless Mode: {HEADLESS}")
    print(f"Bot Token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:] if BOT_TOKEN else ''}")
    
    asyncio.create_task(daily_scheduler())
    
    offset = 0
    logging.info("🚀 Memulai Loop Polling (Requests Method)...")
    offset = 0
    while True:
        try:
            # Polling Telegram via Requests (Wrapped in Thread)
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"timeout": 20, "offset": offset}
            
            # Disable SSL warning
            requests.packages.urllib3.disable_warnings() 
            resp = await asyncio.to_thread(requests.get, url, params=params, timeout=30, verify=False)
            
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", [])
                
                if result:
                    logging.info(f"📩 Masuk {len(result)} pesan baru.")
                
                for update in result:
                    offset = update["update_id"] + 1
                    asyncio.create_task(handle_update(update))
            else:
                logging.warning(f"Polling gagal: {resp.status_code} - {resp.text}")
                await asyncio.sleep(5)
        
        except Exception as e:
            logging.error(f"Polling Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Bot stopped.")
