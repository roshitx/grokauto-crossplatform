#!/usr/bin/env python3
"""
Manual Signup Helper
Buka Chrome biasa → user signup manual → export SSO cookies → simpan ke file.
"""
import json, os, time

def main():
    print("=" * 50)
    print("[*] Manual Signup Helper")
    print("=" * 50)
    print()
    print("Steps:")
    print("1. Buka Chrome biasa (bukan Camoufox)")
    print("2. Buka https://accounts.x.ai/sign-up")
    print("3. Signup manual (email, password, solve Turnstile)")
    print("4. Setelah berhasil login, jalankan script ini lagi")
    print("   dengan argumen: python3 manual_register.py export")
    print()
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_cookies()
    else:
        print("Setelah signup manual, jalankan:")
        print("  python3 manual_register.py export")

def export_cookies():
    """Export SSO cookies from Chrome profile."""
    print("\n[*] Searching Chrome profile for cookies...")
    
    # Common Chrome profile paths
    import platform
    system = platform.system()
    
    if system == "Darwin":  # macOS
        chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    elif system == "Linux":
        chrome_path = os.path.expanduser("~/.config/google-chrome/Default")
    else:  # Windows
        chrome_path = os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default")
    
    cookies_db = os.path.join(chrome_path, "Cookies")
    
    if not os.path.exists(cookies_db):
        print(f"[!] Chrome cookies not found at: {cookies_db}")
        print("[*] Try this instead:")
        print("    1. Install extension: EditThisCookie")
        print("    2. Go to accounts.x.ai (after login)")
        print("    3. Click EditThisCookie icon → Export")
        print("    4. Save as cookies.json in this folder")
        return
    
    print(f"[+] Found Chrome cookies: {cookies_db}")
    print("[*] To export cookies, install EditThisCookie extension:")
    print("    https://chrome.google.com/webstore/detail/editthiscookie")
    print()
    print("    After login to x.ai:")
    print("    1. Click EditThisCookie icon")
    print("    2. Click Export (download icon)")
    print("    3. Save as cookies.json in this folder")
    print()
    
    # Check if cookies.json exists
    if os.path.exists("cookies.json"):
        print("[+] cookies.json found!")
        with open("cookies.json") as f:
            cookies = json.load(f)
        
        # Find x.ai cookies
        xai_cookies = [c for c in cookies if "x.ai" in c.get("domain", "")]
        print(f"[+] x.ai cookies: {len(xai_cookies)}")
        
        # Find SSO cookie
        sso = [c for c in xai_cookies if "sso" in c.get("name", "").lower()]
        if sso:
            print(f"[+] SSO cookie: {sso[0].get('name', '')} = {sso[0].get('value', '')[:30]}...")
            
            # Save SSO cookie
            sso_data = {
                "name": sso[0]["name"],
                "value": sso[0]["value"],
                "domain": sso[0]["domain"],
            }
            with open("sso_cookie.json", "w") as f:
                json.dump(sso_data, f, indent=2)
            print("[+] Saved to sso_cookie.json")
        else:
            print("[!] No SSO cookie found in cookies.json")
    else:
        print("[!] cookies.json not found")
        print("    Follow steps above to export cookies")

if __name__ == "__main__":
    main()
