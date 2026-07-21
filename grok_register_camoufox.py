#!/usr/bin/env python3
"""
grokauto CLI using Camoufox (anti-fingerprint Firefox).
"""
import os, sys, json, time, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camoufox_browser import (
    load_config, start_browser, stop_browser, get_page,
    open_signup_page, fill_email_and_submit, poll_for_code,
    fill_code_and_submit, fill_profile_and_submit
)

def log(msg):
    print(msg, flush=True)

def cloudflare_create_temp_address(cfg):
    base = cfg.get("cloudflare_base_url", "https://cf-temp-email.auliarasyidalzahrawi.workers.dev")
    api_key = cfg.get("cloudflare_api_key", "R0SH1T_T3MP_M41L_2026")
    
    import random, string
    r = requests.get(f"{base}/open_api/settings/domains",
        headers={"x-admin-auth": api_key}, timeout=30)
    domains = r.json().get("domains", [])
    domain = random.choice(domains)
    prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    address = f"{prefix}@{domain}"
    
    r = requests.post(f"{base}/open_api/settings/accounts",
        headers={"x-admin-auth": api_key, "Content-Type": "application/json"},
        json={"address": address, "password": "auto"}, timeout=30)
    
    if r.status_code not in (200, 201):
        raise Exception(f"Create address failed: {r.status_code}")
    
    return {"jwt": r.json().get("jwt", ""), "address": address}

def main():
    cfg = load_config()
    
    print("=" * 50)
    print("[*] grokauto Camoufox Registration")
    print("=" * 50)
    
    try:
        start_browser(log_callback=log)
        
        # Step 1
        open_signup_page(log_callback=log)
        
        # Step 2
        result = cloudflare_create_temp_address(cfg)
        email = result["address"]
        log(f"[+] Temp email: {email}")
        
        fill_email_and_submit(email, log_callback=log)
        
        # Step 3
        code = poll_for_code(email, log_callback=log)
        log(f"[+] Verification code: {code}")
        
        fill_code_and_submit(code, log_callback=log)
        
        # Step 4
        profile = fill_profile_and_submit(log_callback=log)
        log(f"[+] Profile: {profile.get('given_name')} {profile.get('family_name')}")
        
        # Check result
        page = get_page()
        url = page.url
        log(f"[*] Final URL: {url}")
        page.screenshot(path="/tmp/result.png")
        log("[+] Screenshot: /tmp/result.png")
        
        # Check cookies for SSO
        cookies = page.context.cookies()
        sso_cookies = [c for c in cookies if "sso" in c.get("name", "").lower() or "session" in c.get("name", "").lower()]
        if sso_cookies:
            log(f"[+] SSO cookie found: {sso_cookies[0].get('name', '')}")
        else:
            log("[!] No SSO cookie found")
        
        log("[+] Done!")
        
    except Exception as e:
        log(f"[!] Error: {e}")
        try:
            page = get_page()
            if page:
                page.screenshot(path="/tmp/error.png")
                log("[+] Error screenshot: /tmp/error.png")
        except:
            pass
    finally:
        stop_browser(log_callback=log)

if __name__ == "__main__":
    main()
