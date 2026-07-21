"""
Camoufox-based browser for grokauto.
Uses patched Firefox with anti-fingerprinting.
"""
import os, sys, json, time

try:
    from camoufox.sync_api import Camoufox
except ImportError:
    print("Install: pip install camoufox[geoip]")
    sys.exit(1)

_browser = None
_pw_browser = None
_context = None
_page = None
_config = {}

def load_config():
    global _config
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path) as f:
        _config = json.load(f)
    return _config

def start_browser(log_callback=None):
    global _browser, _pw_browser, _context, _page
    log = log_callback or (lambda msg: print(msg))
    
    proxy = _config.get("proxy", "")
    headless = _config.get("headless", False)
    
    log("[+] Starting Camoufox (anti-fingerprint Firefox)...")
    
    proxy_args = None
    if proxy:
        parts = proxy.split(":")
        if len(parts) == 4:
            proxy_args = {
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": parts[3],
            }
        else:
            proxy_args = {"server": proxy}
    
    _browser = Camoufox(
        headless=headless,
        proxy=proxy_args,
        geoip=True,
    )
    
    _pw_browser = _browser.start()
    _context = _pw_browser.new_context(
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
    )
    _page = _context.new_page()
    
    log("[+] Camoufox started (stealth Firefox)")
    return _page

def stop_browser(log_callback=None):
    global _browser, _pw_browser, _context, _page
    log = log_callback or (lambda msg: print(msg))
    try:
        if _page:
            _page.close()
        if _pw_browser:
            _pw_browser.close()
    except:
        pass
    _browser = None
    _pw_browser = None
    _context = None
    _page = None
    log("[+] Browser stopped")

def get_page():
    return _page

# ── Playwright-compatible helpers ───────────────────────
def open_signup_page(log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    if not page:
        raise Exception("Browser not started")
    
    page.goto("https://accounts.x.ai/sign-up", wait_until="domcontentloaded")
    time.sleep(3)
    log("[+] Signup page opened")
    
    # Accept cookies
    try:
        cookie_btn = page.locator("text=Accept All Cookies")
        cookie_btn.wait_for(state="visible", timeout=5000)
        cookie_btn.click()
        log("[+] Cookies accepted")
        time.sleep(1)
    except:
        pass

def fill_email_and_submit(email, log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    
    # Click "Sign up with email"
    page.locator("text=Sign up with email").wait_for(state="visible", timeout=5000)
    page.locator("text=Sign up with email").click()
    log("[+] Clicked 'Sign up with email'")
    time.sleep(2)
    
    # Fill email
    page.locator("input[type='email']").fill(email)
    time.sleep(1)
    
    # Submit
    page.locator("button[type='submit']").click()
    log(f"[+] Email submitted: {email}")
    time.sleep(5)

def poll_for_code(address, log_callback=None, max_wait=90):
    log = log_callback or (lambda msg: print(msg))
    base = _config.get("cloudflare_base_url", "https://cf-temp-email.auliarasyidalzahrawi.workers.dev")
    api_key = _config.get("cloudflare_api_key", "R0SH1T_T3MP_M41L_2026")
    
    import requests as req
    
    for attempt in range(max_wait // 3):
        time.sleep(3)
        try:
            r = req.get(f"{base}/admin/mails?limit=10&offset=0",
                headers={"x-admin-auth": api_key}, timeout=30)
            if not r.ok:
                continue
            
            for msg in r.json().get("results", []):
                if address.lower() not in msg.get("address", "").lower():
                    continue
                
                raw = msg.get("raw", "")
                body = msg.get("body", "") or msg.get("text", "") or msg.get("html", "") or raw
                
                subject = ""
                sub_m = re.search(r'Subject:\s*([^\r\n]+)', raw) if raw else None
                if sub_m:
                    subject = sub_m.group(1)
                
                # 3-3 alphanumeric (x.ai format)
                for src in [subject, body]:
                    m = re.search(r'([A-Z0-9]{3}-[A-Z0-9]{3})', src, re.I)
                    if m:
                        return m.group(1)
                
                # 6-digit fallback
                m = re.search(r'\b(\d{6})\b', body)
                if m:
                    return m.group(1)
        except:
            pass
    
    raise Exception("Tidak menerima kode verifikasi")

def fill_code_and_submit(code, log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    
    code_clean = code.replace("-", "")
    
    # Try individual char inputs
    char_inputs = page.locator("input[maxlength='1']")
    count = char_inputs.count()
    
    if count >= 6:
        log(f"[+] Using {count} individual inputs")
        for i, ch in enumerate(code_clean):
            if i < count:
                char_inputs.nth(i).fill(ch)
                time.sleep(0.2)
    else:
        otp = page.locator("input[type='text']")
        if otp.count() > 0:
            otp.first.fill(code_clean)
            log("[+] Using single input")
    
    time.sleep(1)
    page.locator("button[type='submit']").click()
    log("[+] Code submitted")
    time.sleep(5)

def fill_profile_and_submit(log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    
    # Wait for form
    log("[*] Waiting for profile form...")
    page.wait_for_selector("input[name='givenName']", timeout=15000)
    log("[+] Profile form ready")
    
    import random, string
    first_names = ["Alex", "Jordan", "Casey", "Morgan", "Taylor", "Riley", "Quinn", "Avery"]
    last_names = ["Chen", "Kim", "Lee", "Park", "Wang", "Zhang", "Liu", "Yang"]
    first = random.choice(first_names)
    last = random.choice(last_names)
    password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    
    page.locator("input[name='givenName']").fill(first)
    page.locator("input[name='familyName']").fill(last)
    page.locator("input[type='password']").fill(password)
    log(f"[+] Profile: {first} {last}")
    time.sleep(2)
    
    # Wait for Turnstile
    log("[*] Waiting for Turnstile...")
    try:
        page.wait_for_selector("iframe[src*='challenges.cloudflare.com']", timeout=15000)
        log("[+] Turnstile loaded")
        time.sleep(2)
        
        # Click checkbox inside Turnstile iframe
        tf = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
        try:
            tf.locator("input[type='checkbox']").click(timeout=5000)
            log("[+] Turnstile checkbox clicked")
        except:
            try:
                tf.locator("body").click(timeout=5000)
                log("[+] Turnstile iframe body clicked")
            except:
                log("[!] Could not click Turnstile")
        
        time.sleep(5)
    except:
        log("[!] Turnstile not found")
    
    # Submit
    page.locator("button[type='submit']").click()
    log("[+] Profile submitted")
    time.sleep(10)
    
    return {"given_name": first, "family_name": last, "password": password}
