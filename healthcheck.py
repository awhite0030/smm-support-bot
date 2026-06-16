#!/usr/bin/env python3
"""Bot healthcheck: verifies webhook endpoints, processes, and auto-recovers."""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime

LOG = "/var/log/bot-healthcheck.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def read_token(env_path, key):
    with open(env_path) as f:
        for line in f:
            k = line.split("=", 1)[0].strip()
            if k == key:
                return line.strip().split("=", 1)[1]
    return None

def check_webhook(name, token):
    try:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())["result"]
        wh_url = data.get("url", "")
        pending = data.get("pending_update_count", 0)
        err = data.get("last_error_message", "")
        if not wh_url:
            log(f"ERROR: {name} webhook not set!")
            return False
        if err:
            log(f"WARN: {name} webhook error: {err} (pending: {pending})")
            return False
        log(f"OK: {name} webhook={wh_url} pending={pending}")
        return True
    except Exception as e:
        log(f"ERROR: {name} webhook check failed: {e}")
        return False

def check_process(name, pattern):
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], stderr=subprocess.DEVNULL)
        if out.strip():
            log(f"OK: {name} process running")
            return True
    except subprocess.CalledProcessError:
        pass
    log(f"ERROR: {name} process NOT running!")
    return False

def check_endpoint(name, url):
    try:
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=5)
        code = resp.getcode()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = 0
    if code == 0:
        log(f"ERROR: {name} endpoint not responding")
        return False
    log(f"OK: {name} endpoint HTTP {code}")
    return True

def main():
    smm_token = read_token("/opt/bots/smm-bot/.env", "TOKEN")
    sup_token = read_token("/opt/bots/.env", "BOT_TOKEN")
    
    fail = False
    if not check_process("smm-bot", "smm-bot/.venv/bin/python run.py"): fail = True
    if not check_process("support-bot", r"\.venv/bin/python -m app"): fail = True
    if smm_token and not check_webhook("SMM", smm_token): fail = True
    if sup_token and not check_webhook("Support", sup_token): fail = True
    if not check_endpoint("smm-bot", "http://127.0.0.1:8081/telegram/webhook"): fail = True
    if not check_endpoint("support-bot", "http://127.0.0.1:8780/telegram/webhook"): fail = True
    
    if fail:
        log("RECOVERY: restarting failed services...")
        subprocess.run(["supervisorctl", "restart", "smm-bot", "support-bot"])
        time.sleep(10)
        log("RECOVERY: done")
    
    # Rotate log if >1MB
    try:
        if os.path.getsize(LOG) > 1_048_576:
            os.rename(LOG, LOG + ".old")
    except FileNotFoundError:
        pass
    
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
