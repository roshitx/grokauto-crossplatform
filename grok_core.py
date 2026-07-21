"""
grok_core.py — Cross-platform replacement for grok_core.pyd
Works on Mac, Linux, Windows via DrissionPage browser automation.

Based on analysis of the original Nuitka-compiled grok_core.pyd.
"""
from __future__ import annotations
import os, sys, json, time, re, random, string, threading, logging
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urljoin

# ── DrissionPage (lazy import) ─────────────────────────────────
ChromiumPage = None
ChromiumOptions = None

def _ensure_drissionpage():
    global ChromiumPage, ChromiumOptions
    if ChromiumPage is None:
        try:
            from DrissionPage import ChromiumPage as _CP, ChromiumOptions as _CO
            ChromiumPage = _CP
            ChromiumOptions = _CO
        except ImportError:
            raise ImportError(
                "DrissionPage required: pip install DrissionPage\n"
                "https://github.com/g1879/DrissionPage"
            )

# ── Config ────────────────────────────────────────────────────
SIGNUP_URL = "https://accounts.x.ai/sign-up"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

config: dict = {}
_io_lock = threading.Lock()
_stats_lock = threading.Lock()

_browser = None  # ChromiumPage | None
_worker_id: int = 0
_cpa_async_threads: list = []

# ── Logging ───────────────────────────────────────────────────
_LOG_LEVEL_RANK = {"debug": 0, "info": 1, "warn": 2, "error": 3}

def _noop_log(_: str) -> None:
    pass

def _log(msg: str, callback: Callable | None = None) -> None:
    if callback:
        callback(msg)
    else:
        print(msg)

# ── Config ────────────────────────────────────────────────────
def load_config(path: str = "") -> dict:
    global config
    p = path or CONFIG_FILE
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            config = json.load(f)
    return config

def save_config(cfg: dict = None, path: str = "") -> None:
    global config
    if cfg is not None:
        config = cfg
    p = path or CONFIG_FILE
    with open(p, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# ── Browser ───────────────────────────────────────────────────
def _get_browser() -> ChromiumPage | None:
    global _browser
    return _browser

def _get_page() -> ChromiumPage | None:
    return _get_browser()

def create_browser_options():
    _ensure_drissionpage()
    opts = ChromiumOptions()
    opts.set_argument("--no-sandbox")
    opts.set_argument("--disable-dev-shm-usage")
    opts.set_argument("--disable-gpu")
    opts.set_argument("--disable-blink-features=AutomationControlled")
    # Anti-detection: realistic user agent
    opts.set_argument("--disable-features=IsolateOrigins,site-per-process")
    opts.set_user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    profile_dir = config.get("profile_dir", "")
    if profile_dir:
        opts.set_user_data_path(profile_dir)
    # Proxy from config — DataImpulse format: host:port:user:pass
    proxy = config.get("proxy", "")
    if proxy:
        parts = proxy.split(":")
        if len(parts) == 4:
            # host:port:user:pass → set proxy-server without auth, auth handled via CDP
            opts.set_argument(f"--proxy-server={parts[0]}:{parts[1]}")
        else:
            # Already formatted (e.g. http://host:port)
            opts.set_argument(f"--proxy-server={proxy}")
    # Headless from config
    if config.get("headless", False):
        opts.headless()
    return opts

def _setup_proxy_auth(page):
    """Set proxy auth via CDP for DataImpulse (host:port:user:pass format)."""
    proxy = config.get("proxy", "")
    if not proxy:
        return
    parts = proxy.split(":")
    if len(parts) != 4:
        return
    user, pwd = parts[2], parts[3]
    auth = f"{user}:{pwd}"
    import base64
    encoded = base64.b64encode(auth.encode()).decode()
    js = f"""
    const encoded = '{encoded}';
    const decoded = atob(encoded);
    const [username, password] = decoded.split(':');
    window.__proxy_auth = {{username, password}};
    """
    try:
        page.run_js(js)
    except Exception:
        pass

def start_browser(log_callback: Callable = None) -> ChromiumPage:
    global _browser
    log = log_callback or _noop_log
    opts = create_browser_options()
    _browser = ChromiumPage(opts)
    _setup_proxy_auth(_browser)
    log("[+] Browser started")
    return _browser

def stop_browser(log_callback: Callable = None) -> None:
    global _browser
    log = log_callback or _noop_log
    if _browser:
        try:
            _browser.quit()
        except Exception:
            pass
        _browser = None
    log("[*] Browser stopped")

def restart_browser(log_callback: Callable = None) -> ChromiumPage:
    log = log_callback or _noop_log
    stop_browser(log)
    time.sleep(1)
    return start_browser(log)

def cleanup_runtime_memory() -> None:
    global _browser
    if _browser:
        try:
            _browser.quit()
        except Exception:
            pass
        _browser = None

# ── Worker ────────────────────────────────────────────────────
def _set_worker_id(wid: int) -> None:
    global _worker_id
    _worker_id = wid

def _track_cpa_async_thread(t: threading.Thread) -> None:
    _cpa_async_threads.append(t)

def _wait_cpa_async_threads(timeout: float = 120) -> None:
    for t in _cpa_async_threads:
        t.join(timeout=timeout)
    _cpa_async_threads.clear()

def _join_threads_interruptible(threads: list, stop_event: threading.Event, timeout: float = 5) -> None:
    for t in threads:
        t.join(timeout=timeout)
        if stop_event.is_set():
            break

# ── Sleep ─────────────────────────────────────────────────────
def sleep_with_cancel(seconds: float, cancel_callback: Callable = None) -> None:
    end = time.time() + seconds
    while time.time() < end:
        if cancel_callback and cancel_callback():
            raise Exception("Cancelled")
        time.sleep(0.2)

# ── Cloudflare Mail API ──────────────────────────────────────
def cloudflare_build_headers(cfg: dict = None) -> dict:
    c = cfg or config
    mode = c.get("cloudflare_auth_mode", "x-admin-auth")
    key = c.get("cloudflare_api_key", "")
    if mode == "x-admin-auth":
        return {"x-admin-auth": key}
    else:
        return {"Authorization": f"Bearer {key}"}

def cloudflare_apply_auth_params(url: str, cfg: dict = None) -> str:
    """No-op for admin auth — API key in header, not URL."""
    return url

def cloudflare_get_domains(cfg: dict = None) -> list[str]:
    c = cfg or config
    import requests
    base = c["cloudflare_api_base"].rstrip("/")
    path = c.get("cloudflare_path_domains", "/api/domains")
    headers = cloudflare_build_headers(c)
    # For admin auth, we need a JWT first — use settings endpoint
    settings_path = "/open_api/settings"
    r = requests.get(f"{base}{settings_path}", headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("domains", [])

def cloudflare_create_temp_address(domain: str = "", cfg: dict = None) -> dict:
    """Create a temp email address. Returns {"address": "...", "jwt": "..."}."""
    c = cfg or config
    import requests
    base = c["cloudflare_api_base"].rstrip("/")
    path = c.get("cloudflare_path_accounts", "/admin/new_address")
    headers = cloudflare_build_headers(c)
    headers["Content-Type"] = "application/json"
    if not domain:
        domains = c.get("cloudflare_domains", c.get("domains", []))
        default = c.get("cloudflare_default_domain", c.get("default_domains", "roshit.site"))
        if isinstance(default, list):
            domain = default[0] if default else (domains[0] if domains else "roshit.site")
        else:
            domain = default or (domains[0] if domains else "roshit.site")
    # Generate random local part
    local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    body = {"enablePrefix": True, "name": local, "domain": domain}
    r = requests.post(f"{base}{path}", json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()  # {"jwt": "...", "address": "...", "address_id": 1}

def cloudflare_create_account(cfg: dict = None) -> dict:
    """Alias for create_temp_address."""
    return cloudflare_create_temp_address(cfg=cfg)

def cloudflare_get_messages(address: str = "", jwt: str = "", cfg: dict = None) -> dict:
    c = cfg or config
    import requests
    base = c["cloudflare_api_base"].rstrip("/")
    path = c.get("cloudflare_path_messages", "/api/mails")
    headers = {"Authorization": f"Bearer {jwt}"}
    r = requests.get(f"{base}{path}?limit=10&offset=0", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def cloudflare_get_message_detail(message_id: str, jwt: str = "", cfg: dict = None) -> dict:
    c = cfg or config
    import requests
    base = c["cloudflare_api_base"].rstrip("/")
    headers = {"Authorization": f"Bearer {jwt}"}
    r = requests.get(f"{base}/api/mail/{message_id}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def cloudflare_get_oai_code(address: str, jwt: str = "", cfg: dict = None, max_wait: int = 60) -> str:
    """Poll inbox for OpenAI/xAI verification code."""
    import requests
    c = cfg or config
    base = c["cloudflare_api_base"].rstrip("/")
    headers = {"Authorization": f"Bearer {jwt}"}
    for _ in range(max_wait):
        r = requests.get(f"{base}/api/mails?limit=5&offset=0", headers=headers, timeout=30)
        if r.ok:
            data = r.json()
            results = data.get("results", [])
            for msg in results:
                body = msg.get("body", "") or msg.get("text", "") or msg.get("html", "") or msg.get("raw", "")
                # Extract subject from raw email headers
                subject = ""
                sub_match = re.search(r'Subject:\s*([^\r\n]+)', msg.get("raw", ""))
                if sub_match:
                    subject = sub_match.group(1).strip()
                # Extract xAI verification code: alphanumeric like P0W-KXG
                # Try Subject first: "SpaceXAI confirmation code: P0W-KXG"
                m = re.search(r'confirmation code[:\s]+([A-Z0-9]{3}-[A-Z0-9]{3})', subject, re.I)
                if not m:
                    m = re.search(r'confirmation code[:\s]+([A-Z0-9]{3}-[A-Z0-9]{3})', body, re.I)
                if not m:
                    # Try bold table cell: font-weight:bold;">P0W-KXG</td>
                    m = re.search(r'font-weight:\s*bold[^>]*>([A-Z0-9]{3}-[A-Z0-9]{3})<', body, re.I)
                if not m:
                    # Fallback: any 3-3 alphanumeric code
                    m = re.search(r'\b([A-Z0-9]{3}-[A-Z0-9]{3})\b', body, re.I)
                if m:
                    return m.group(1)
        time.sleep(2)
    raise Exception("Tidak menerima kode verifikasi dalam waktu yang ditentukan")

def cloudflare_get_token(address: str, jwt: str = "", cfg: dict = None) -> str:
    """Alias — return the JWT itself."""
    return jwt

def cloudflare_next_default_domain(cfg: dict = None) -> str:
    c = cfg or config
    default = c.get("cloudflare_default_domain", c.get("default_domains", ["roshit.site"]))
    return default[0] if isinstance(default, list) else default

def cloudflare_is_admin_create_path(cfg: dict = None) -> bool:
    c = cfg or config
    return "admin" in c.get("cloudflare_path_accounts", "")

# ── Registration Flow (browser automation) ────────────────────
def open_signup_page(log_callback: Callable = None, cancel_callback: Callable = None) -> None:
    log = log_callback or _noop_log
    page = _get_page()
    if not page:
        raise Exception("Browser not started")
    page.get(SIGNUP_URL)
    time.sleep(8)  # Wait for JS to render
    # Accept cookies if banner present
    try:
        cookie_btn = page.ele("text=Accept All Cookies")
        if cookie_btn:
            cookie_btn.click()
            time.sleep(1)
            log("[+] Cookies accepted")
    except Exception:
        pass
    log("[+] Signup page opened")

def fill_email_and_submit(log_callback: Callable = None, cancel_callback: Callable = None) -> tuple[str, str]:
    """Create temp email, fill it on signup page, submit. Returns (email, dev_token)."""
    log = log_callback or _noop_log
    page = _get_page()
    if not page:
        raise Exception("Browser not started")

    # Create temp email via API
    result = cloudflare_create_temp_address()
    email = result["address"]
    jwt = result.get("jwt", "")
    log(f"[+] Temp email created: {email}")

    # Click "Sign up with email" button first
    try:
        email_btn = page.ele("text=Sign up with email")
        if email_btn:
            email_btn.click()
            time.sleep(3)
            log("[+] Clicked 'Sign up with email'")
        else:
            log("[!] 'Sign up with email' button not found, trying direct input")
    except Exception as e:
        log(f"[!] Error clicking email button: {e}")

    # Fill email field on x.ai signup page
    try:
        email_input = page.ele("css:input[type='email']")
        if not email_input:
            # Try text input as fallback
            email_input = page.ele("css:input[type='text']")
        if email_input:
            email_input.clear()
            email_input.input(email)
            time.sleep(0.5)
            # Click submit/next button
            btn = page.ele("css:button[type='submit']")
            if not btn:
                # Try "Next" button
                btn = page.ele("text=Next")
            if btn:
                btn.click()
                time.sleep(3)
                log("[+] Email submitted")
            else:
                log("[!] Submit button not found")
        else:
            log("[!] Email input not found")
    except Exception as e:
        log(f"[!] Error filling email: {e}")
        raise

    return email, jwt

def fill_code_and_submit(email: str, dev_token: str, log_callback: Callable = None, cancel_callback: Callable = None) -> str:
    """Poll for verification code, fill it, submit."""
    log = log_callback or _noop_log
    page = _get_page()
    if not page:
        raise Exception("Browser not started")

    # Poll for code
    code = cloudflare_get_oai_code(email, jwt=dev_token, max_wait=60)
    log(f"[+] Verification code: {code}")

    # Fill code field
    try:
        code_input = page.ele("css:input[type='text']")
        if code_input:
            code_input.clear()
            code_input.input(code)
            time.sleep(0.5)
            btn = page.ele("css:button[type='submit']")
            if btn:
                btn.click()
                time.sleep(2)
    except Exception as e:
        log(f"[!] Error filling code: {e}")
        raise

    return code

def fill_profile_and_submit(log_callback: Callable = None, cancel_callback: Callable = None) -> dict:
    """Fill profile form (name, password). Returns profile dict."""
    log = log_callback or _noop_log
    page = _get_page()
    if not page:
        raise Exception("Browser not started")

    # Generate random name
    first_names = ["Alex", "Jordan", "Casey", "Morgan", "Taylor", "Riley", "Quinn", "Avery"]
    last_names = ["Chen", "Kim", "Lee", "Park", "Wang", "Zhang", "Liu", "Yang"]
    first = random.choice(first_names)
    last = random.choice(last_names)
    password = "".join(random.choices(string.ascii_letters + string.digits, k=16))

    profile = {"given_name": first, "family_name": last, "password": password}

    try:
        # Fill first name
        fn_input = page.ele("css:input[name='givenName']")
        if fn_input:
            fn_input.clear()
            fn_input.input(first)

        # Fill last name
        ln_input = page.ele("css:input[name='familyName']")
        if ln_input:
            ln_input.clear()
            ln_input.input(last)

        # Fill password
        pw_input = page.ele("css:input[type='password']")
        if pw_input:
            pw_input.clear()
            pw_input.input(password)

        # Submit
        btn = page.ele("css:button[type='submit']")
        if btn:
            btn.click()
            time.sleep(3)
    except Exception as e:
        log(f"[!] Error filling profile: {e}")

    return profile

def wait_for_sso_cookie(log_callback: Callable = None, cancel_callback: Callable = None, timeout: int = 60) -> str:
    """Wait for SSO cookie to appear. Returns SSO token string."""
    log = log_callback or _noop_log
    page = _get_page()
    if not page:
        raise Exception("Browser not started")

    start = time.time()
    while time.time() - start < timeout:
        if cancel_callback and cancel_callback():
            raise Exception("Cancelled")
        cookies = page.cookies()
        for cookie in cookies:
            name = cookie.get("name", "")
            if "sso" in name.lower() or "auth" in name.lower() or "token" in name.lower():
                val = cookie.get("value", "")
                if val:
                    log(f"[+] SSO cookie found: {name}")
                    return val
        time.sleep(2)

    # Try localStorage
    try:
        sso = page.run_js("return localStorage.getItem('sso') || localStorage.getItem('token') || ''")
        if sso:
            return sso
    except Exception:
        pass

    raise Exception("SSO cookie tidak ditemukan dalam waktu yang ditentukan")

# ── NSFW ──────────────────────────────────────────────────────
def enable_nsfw_for_token(token: str, log_callback: Callable = None) -> tuple[bool, str]:
    """Enable NSFW mode for a token via API."""
    log = log_callback or _noop_log
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # xAI NSFW settings endpoint
        r = requests.put(
            "https://grok.com/rest/user/preferences",
            json={"isEnhancedDataEnabled": True},
            headers=headers,
            timeout=30
        )
        if r.ok:
            return True, "NSFW enabled"
        else:
            return False, f"API returned {r.status_code}"
    except Exception as e:
        return False, str(e)

def open_nsfw(*args, **kwargs) -> tuple[bool, str]:
    return enable_nsfw_for_token(*args, **kwargs)

def update_nsfw_settings(*args, **kwargs) -> tuple[bool, str]:
    return enable_nsfw_for_token(*args, **kwargs)

# ── CPA Export ────────────────────────────────────────────────
def export_cpa_xai_for_account(email: str, password: str, sso: str = "",
                                log_callback: Callable = None, page=None,
                                cfg: dict = None) -> dict:
    """Export CPA xAI credentials."""
    log = log_callback or _noop_log
    c = cfg or config
    if not c.get("cpa_export_enabled", False):
        return {"ok": False, "skipped": True, "error": "CPA export disabled"}
    try:
        from cpa_xai.mint import mint_and_export
        return mint_and_export(email, password, sso=sso, log_callback=log, page=page, cfg=c)
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Token Pool ────────────────────────────────────────────────
def add_token_to_grok2api_pools(token: str, email: str = "", log_callback: Callable = None) -> bool:
    log = log_callback or _noop_log
    c = config
    pool_name = c.get("grok2api_pool_name", "ssoBasic")
    token_file = c.get("grok2api_local_token_file", "grok2api_tokens.json")

    try:
        tokens = []
        if os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8") as f:
                tokens = json.load(f)

        tokens.append({
            "token": token,
            "email": email,
            "pool": pool_name,
            "created": int(time.time())
        })

        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)

        log(f"[+] Token added to pool '{pool_name}'")
        return True
    except Exception as e:
        log(f"[!] Failed to add token to pool: {e}")
        return False

def add_token_to_token_only_file(token: str, log_callback: Callable = None) -> bool:
    log = log_callback or _noop_log
    token_file = config.get("token_only_file", "tokens_only.txt")
    try:
        with open(token_file, "a", encoding="utf-8") as f:
            f.write(token + "\n")
        log(f"[+] Token added to {token_file}")
        return True
    except Exception as e:
        log(f"[!] Failed to add token: {e}")
        return False

def add_token_to_grok2api_remote_pool(*args, **kwargs) -> bool:
    """Stub — remote pool not implemented."""
    _log("[*] Remote pool not implemented in cross-platform version")
    return False

# ── License (stub) ───────────────────────────────────────────
def check_activated_license(*args, **kwargs) -> bool:
    return True

def verify_and_activate_license(*args, **kwargs) -> tuple[bool, str]:
    return True, "License bypassed"

def check_license_cli(*args, **kwargs) -> bool:
    return True

def check_license_gui(*args, **kwargs) -> bool:
    return True

# ── CLI ───────────────────────────────────────────────────────
def run_registration_cli(*args, **kwargs):
    raise NotImplementedError("CLI mode — use grok_register_ttk.py")

# ── Utilities ─────────────────────────────────────────────────
def clean_code(text: str) -> str:
    return re.sub(r'[^0-9]', '', text)

def clean_exc(e: Exception) -> str:
    return str(e)

def clean_html(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html)

def build_profile(*args, **kwargs) -> dict:
    return {"given_name": "User", "family_name": "Test"}

def run_js(js: str) -> Any:
    page = _get_page()
    if page:
        return page.run_js(js)
    return None

# ── Exports ───────────────────────────────────────────────────
__all__ = [
    # Config
    "config", "load_config", "save_config",
    # Browser
    "_get_browser", "_get_page", "start_browser", "stop_browser", "restart_browser",
    "create_browser_options", "cleanup_runtime_memory",
    # Worker
    "_set_worker_id", "_track_cpa_async_thread", "_wait_cpa_async_threads",
    "_join_threads_interruptible", "_io_lock", "_stats_lock",
    # Sleep
    "sleep_with_cancel",
    # Registration
    "open_signup_page", "fill_email_and_submit", "fill_code_and_submit",
    "fill_profile_and_submit", "wait_for_sso_cookie",
    # Cloudflare Mail
    "cloudflare_build_headers", "cloudflare_apply_auth_params",
    "cloudflare_get_domains", "cloudflare_create_temp_address",
    "cloudflare_create_account", "cloudflare_get_messages",
    "cloudflare_get_message_detail", "cloudflare_get_oai_code",
    "cloudflare_get_token", "cloudflare_next_default_domain",
    "cloudflare_is_admin_create_path",
    # NSFW
    "enable_nsfw_for_token", "open_nsfw", "update_nsfw_settings",
    # CPA
    "export_cpa_xai_for_account",
    # Token
    "add_token_to_grok2api_pools", "add_token_to_token_only_file",
    "add_token_to_grok2api_remote_pool",
    # License
    "check_activated_license", "verify_and_activate_license",
    "check_license_cli", "check_license_gui",
    # Utilities
    "clean_code", "clean_exc", "clean_html", "build_profile", "run_js",
    "run_registration_cli",
    # CLI + License
    "main_cli", "reset_9router_connections_status",
    "get_hwid", "get_log_level",
]

# Load config on import
load_config()

# ── Missing functions (discovered via import analysis) ─────────
def main_cli():
    """CLI registration loop."""
    global config
    config = load_config()
    count = config.get("register_count", 1)
    worker_count = config.get("worker_count", 1)
    log = print

    log(f"[*] Starting CLI registration: {count} accounts, {worker_count} workers")
    start_browser(log_callback=log)

    success = 0
    for i in range(count):
        try:
            log(f"\n{'='*50}")
            log(f"[*] Account {i+1}/{count}")
            log(f"{'='*50}")

            open_signup_page(log_callback=log)
            email, dev_token = fill_email_and_submit(log_callback=log)
            log(f"[+] Email: {email}")

            code = fill_code_and_submit(email, dev_token, log_callback=log)
            log(f"[+] Code: {code}")

            profile = fill_profile_and_submit(log_callback=log)
            log(f"[+] Profile: {profile.get('given_name')} {profile.get('family_name')}")

            sso = wait_for_sso_cookie(log_callback=log)
            log(f"[+] SSO: {sso[:30]}...")

            add_token_to_grok2api_pools(sso, email=email, log_callback=log)
            add_token_to_token_only_file(sso, log_callback=log)

            success += 1
            log(f"[+] Account {i+1} done!")

        except Exception as e:
            log(f"[!] Account {i+1} failed: {e}")
            restart_browser(log_callback=log)

    stop_browser(log_callback=log)
    log(f"\n[*] Done: {success}/{count} accounts registered")

def reset_9router_connections_status(callback=None):
    """Stub — 9router integration not implemented."""
    if callback:
        callback("[*] 9router status reset (stub)")

def get_hwid():
    """Get hardware ID for license."""
    import platform
    import hashlib
    data = f"{platform.node()}-{platform.machine()}-{platform.system()}"
    return hashlib.md5(data.encode()).hexdigest()[:16]

def get_log_level():
    """Get configured log level."""
    return config.get("log_level", "info")
