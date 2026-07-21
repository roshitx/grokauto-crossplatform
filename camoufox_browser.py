"""
Camoufox-based browser for grokauto.
"""
import os, sys, json, time, re, random, string

try:
    from camoufox.sync_api import Camoufox
except ImportError:
    print("Install: pip install 'camoufox[geoip]'")
    sys.exit(1)

_browser = None
_pw_browser = None
_page = None
_config = {}

def load_config():
    global _config
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path) as f:
            raw = f.read()
        # Strip trailing commas (common JSON issue)
        import re as _re
        raw = _re.sub(r',\s*([}\]])', r'\1', raw)
        _config = json.loads(raw)
    except Exception as e:
        print(f"[!] config.json error: {e}")
        print(f"[*] Fixing config.json from git...")
        # Try to re-read from clean source
        _config = {
            "cloudflare_api_base": "https://cf-temp-email.auliarasyidalzahrawi.workers.dev",
            "cloudflare_api_key": "R0SH1T_T3MP_M41L_2026",
            "proxy": "",
            "headless": False,
            "captcha_api_key": "",
        }
    return _config

def start_browser(log_callback=None):
    global _browser, _pw_browser, _page
    log = log_callback or (lambda msg: print(msg))
    
    proxy = _config.get("proxy", "")
    headless = _config.get("headless", False)
    
    log("[+] Starting Camoufox (anti-fingerprint Firefox)...")
    
    proxy_args = None
    if proxy:
        parts = proxy.split(":")
        if len(parts) == 4:
            proxy_args = {"server": f"http://{parts[0]}:{parts[1]}", "username": parts[2], "password": parts[3]}
        else:
            proxy_args = {"server": proxy}
    
    _browser = Camoufox(headless=headless, proxy=proxy_args, geoip=True)
    _pw_browser = _browser.start()
    context = _pw_browser.new_context(viewport={"width": 1366, "height": 768}, locale="en-US", timezone_id="America/New_York")
    _page = context.new_page()
    
    log("[+] Camoufox started")
    return _page

def stop_browser(log_callback=None):
    global _browser, _pw_browser, _page
    log = log_callback or (lambda msg: print(msg))
    try:
        if _page: _page.close()
        if _pw_browser: _pw_browser.close()
    except: pass
    _browser = None; _pw_browser = None; _page = None
    log("[+] Browser stopped")

def get_page():
    return _page

# ── Helpers ─────────────────────────────────────────────
def open_signup_page(log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    page.goto("https://accounts.x.ai/sign-up", wait_until="domcontentloaded")
    time.sleep(3)
    log("[+] Signup page opened")
    try:
        btn = page.locator("text=Accept All Cookies")
        if btn.is_visible(timeout=3000):
            btn.click()
            log("[+] Cookies accepted")
            time.sleep(1)
    except: pass

def fill_email_and_submit(email, log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    page.locator("text=Sign up with email").wait_for(state="visible", timeout=5000)
    page.locator("text=Sign up with email").click()
    log("[+] Clicked 'Sign up with email'")
    time.sleep(2)
    page.locator("input[type='email']").fill(email)
    time.sleep(1)
    page.locator("button[type='submit']").click()
    log(f"[+] Email submitted: {email}")
    time.sleep(5)

def poll_for_code(address, log_callback=None, max_wait=90):
    log = log_callback or (lambda msg: print(msg))
    import requests as req
    base = _config.get("cloudflare_api_base", "https://cf-temp-email.auliarasyidalzahrawi.workers.dev")
    api_key = _config.get("cloudflare_api_key", "R0SH1T_T3MP_M41L_2026")
    
    for _ in range(max_wait // 3):
        time.sleep(3)
        try:
            r = req.get(f"{base}/admin/mails?limit=10&offset=0", headers={"x-admin-auth": api_key}, timeout=30)
            if not r.ok: continue
            for msg in r.json().get("results", []):
                if address.lower() not in msg.get("address", "").lower(): continue
                raw = msg.get("raw", "")
                body = msg.get("body", "") or msg.get("text", "") or msg.get("html", "") or raw
                subject = re.search(r'Subject:\s*([^\r\n]+)', raw).group(1) if re.search(r'Subject:\s*([^\r\n]+)', raw) else ""
                for src in [subject, body]:
                    m = re.search(r'([A-Z0-9]{3}-[A-Z0-9]{3})', src, re.I)
                    if m: return m.group(1)
                m = re.search(r'\b(\d{6})\b', body)
                if m: return m.group(1)
        except: pass
    raise Exception("Tidak menerima kode verifikasi")

def fill_code_and_submit(code, log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    page = get_page()
    code_clean = code.replace("-", "")
    chars = page.locator("input[maxlength='1']")
    if chars.count() >= 6:
        log(f"[+] Using {chars.count()} individual inputs")
        for i, ch in enumerate(code_clean):
            if i < chars.count():
                chars.nth(i).fill(ch)
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
    log("[*] Waiting for profile form...")
    page.wait_for_selector("input[name='givenName']", timeout=15000)
    log("[+] Profile form ready")
    
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
        time.sleep(3)
        
        # Click checkbox inside Turnstile iframe
        tf = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
        try:
            tf.locator("input[type='checkbox']").click(timeout=5000)
            log("[+] Turnstile checkbox clicked")
        except:
            try:
                tf.locator("body").click(timeout=5000)
                log("[+] Turnstile body clicked")
            except:
                log("[!] Could not click Turnstile")
        time.sleep(5)
        
        # Check auto-solve
        token_el = page.locator("input[name='cf-turnstile-response']")
        if token_el.count() > 0:
            val = token_el.get_attribute("value") or ""
            if len(val) > 10:
                log(f"[+] Turnstile auto-solved! Token: {val[:30]}...")
            else:
                log("[!] Turnstile not auto-solved")
                # Try 2captcha
                api_key = _config.get("captcha_api_key", "")
                if api_key:
                    log("[+] Solving via 2captcha...")
                    sitekey = _find_sitekey(page)
                    if sitekey:
                        token = _solve_2captcha(sitekey, page.url)
                        page.evaluate(f"document.querySelector('input[name=\"cf-turnstile-response\"]').value = '{token}'")
                        log(f"[+] Token injected: {token[:30]}...")
                else:
                    log("[!] No captcha_api_key set")
    except Exception as e:
        log(f"[!] Turnstile error: {e}")
    
    # Submit
    page.locator("button[type='submit']").click()
    log("[+] Profile submitted")
    time.sleep(10)
    
    return {"given_name": first, "family_name": last, "password": password}

def _find_sitekey(page):
    # From data-sitekey
    try:
        el = page.locator("[data-sitekey]").first
        sk = el.get_attribute("data-sitekey")
        if sk: return sk
    except: pass
    # From HTML
    html = page.content()
    m = re.search(r'data-sitekey="([^"]+)"', html)
    if m: return m.group(1)
    # From scripts
    try:
        result = page.evaluate("""
            var scripts = document.querySelectorAll('script');
            for (var i = 0; i < scripts.length; i++) {
                var t = scripts[i].textContent || '';
                var m = t.match(/0x4[A-Za-z0-9]{20,}/);
                if (m) return m[0];
            }
            return null;
        """)
        if result: return result
    except: pass
    return None

def _solve_2captcha(sitekey, page_url):
    import requests as req
    api_key = _config.get("captcha_api_key", "")
    r = req.post("https://api.2captcha.com/createTask", json={
        "clientKey": api_key,
        "task": {"type": "TurnstileTaskProxyless", "websiteURL": page_url, "websiteKey": sitekey}
    }, timeout=30)
    task_id = r.json()["taskId"]
    for _ in range(60):
        time.sleep(2)
        r = req.post("https://api.2captcha.com/getTaskResult", json={"clientKey": api_key, "taskId": task_id}, timeout=30)
        if r.json().get("status") == "ready":
            return r.json()["solution"]["token"]
    raise Exception("2captcha timeout")
