"""
Find Turnstile sitekey by:
1. Waiting for dynamic load
2. Checking iframes from challenges.cloudflare.com
3. Intercepting network requests
4. Checking JS global variables
"""
import json
with open('config.json') as f:
    cfg = json.load(f)
cfg['proxy'] = ''
cfg['headless'] = False
with open('config.json', 'w') as f:
    json.dump(cfg, f, indent=2)

import grok_core
grok_core.load_config()

page = grok_core.start_browser()
grok_core.open_signup_page()

import time, re
time.sleep(10)

# Accept cookies
try:
    cookie_btn = page.ele("text=Accept All Cookies")
    if cookie_btn:
        cookie_btn.click()
        time.sleep(1)
except: pass

# Click Sign up with email
email_btn = page.ele("text=Sign up with email")
email_btn.click()
time.sleep(5)

# Create temp email and fill
result = grok_core.cloudflare_create_temp_address()
email = result["address"]

email_input = page.ele("css:input[type='email']")
email_input.clear()
email_input.input(email)
time.sleep(1)

btn = page.ele("css:button[type='submit']")
if not btn: btn = page.ele("text=Next")
btn.click()
time.sleep(8)

# Fill code
code_input = page.ele("css:input[type='text']")
if code_input:
    import requests
    jwt = result.get("jwt", "")
    for attempt in range(30):
        r = requests.get(f"https://cf-temp-email.auliarasyidalzahrawi.workers.dev/admin/mails?limit=5&offset=0",
            headers={"x-admin-auth": "R0SH1T_T3MP_M41L_2026"}, timeout=30)
        if r.ok:
            msgs = r.json().get("results", [])
            for msg in msgs:
                raw = msg.get("raw", "")
                m = re.search(r'confirmation code[:\s]+([A-Z0-9]{3}-[A-Z0-9]{3})', raw, re.I)
                if m:
                    code = m.group(1)
                    code_clean = code.replace("-", "")
                    code_input.clear()
                    code_input.input(code_clean)
                    time.sleep(1)
                    btn = page.ele("css:button[type='submit']")
                    if not btn: btn = page.ele("text=Next")
                    if btn: btn.click()
                    time.sleep(5)
                    print(f"Code submitted: {code}")
                    break
            else:
                continue
            break
        time.sleep(2)

# Now on profile page - ANALYZE TURNSTILE
print("\n=== TURNSTILE ANALYSIS ===")
time.sleep(5)  # Wait for dynamic content

# 1. Check iframes
iframes = page.eles("css:iframe")
print(f"Iframes: {len(iframes)}")
for i, f in enumerate(iframes):
    src = f.attr("src") or ""
    name = f.attr("name") or ""
    print(f"  iframe[{i}]: src={src[:150]}, name={name}")

# 2. Check all divs with cf-turnstile class
cf_divs = page.eles("css:.cf-turnstile, [data-sitekey], [id*='turnstile'], [class*='turnstile']")
print(f"Turnstile elements: {len(cf_divs)}")
for d in cf_divs:
    print(f"  class={d.attr('class')}, data-sitekey={d.attr('data-sitekey')}, id={d.attr('id')}")

# 3. Check hidden inputs
hidden = page.eles("css:input[type='hidden']")
print(f"Hidden inputs: {len(hidden)}")
for h in hidden:
    print(f"  name={h.attr('name')}, value={h.attr('value')[:50] if h.attr('value') else ''}")

# 4. Check JS globals
try:
    result = page.run_js("""
        return {
            turnstile: typeof window.turnstile,
            cf_turnstile: typeof window.cf_turnstile,
            cfChallenge: typeof window.__CF\$cv\$params,
            turnstileResp: window.__turnstileResp,
            allInputs: Array.from(document.querySelectorAll('input')).map(i => ({name: i.name, type: i.type, value: i.value.substring(0,50)}))
        }
    """)
    print(f"\nJS globals: {json.dumps(result, indent=2)[:500]}")
except Exception as e:
    print(f"JS error: {e}")

# 5. Check page HTML for turnstile
html = page.html
sitekey_matches = re.findall(r'data-sitekey="([^"]+)"', html)
print(f"\ndata-sitekey in HTML: {sitekey_matches}")

cf_turnstile = re.findall(r'cf-turnstile[^"\']*', html)
print(f"cf-turnstile in HTML: {cf_turnstile[:5]}")

# 6. Check for challenge platform scripts
challenge_scripts = re.findall(r'challenges\.cloudflare\.com[^"\']*', html)
print(f"Challenge scripts: {challenge_scripts[:3]}")

# 7. Check network requests for turnstile
try:
    perf = page.run_js("""
        return performance.getEntriesByType('resource')
            .filter(e => e.name.includes('turnstile') || e.name.includes('challenge'))
            .map(e => e.name)
    """)
    print(f"\nNetwork: {json.dumps(perf, indent=2)[:500]}")
except:
    pass

grok_core.stop_browser()
