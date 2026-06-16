#!/bin/bash
# Bot healthcheck: verifies webhook endpoints and auto-recovers
LOG="/var/log/bot-healthcheck.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

# Read tokens via Python to avoid shell escaping issues
read_tokens() {
    python3 -c "
import sys
tokens = {}
for path, key in [('/opt/bots/smm-bot/.env', 'SMM'), ('/opt/bots/.env', 'SUP')]:
    with open(path) as f:
        for line in f:
            k = line.split('=',1)[0].strip()
            if k in ('TOKEN', 'BOT_TOKEN'):
                tokens[key] = line.strip().split('=',1)[1]
                break
print(tokens.get('SMM',''))
print(tokens.get('SUP',''))
"
}

TOKENS=*** read_tokens)
SMM_TOKEN="${TOKENS[0]}"
SUP_TOKEN="${TOKENS[1]}"

check_webhook() {
    local name=$1 token=$2
    local info
    info=$(curl -s "https://api.telegram.org/bot${token}/getWebhookInfo" 2>/dev/null)
    local url pending err
    url=$(echo "$info" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'].get('url',''))" 2>/dev/null)
    pending=$(echo "$info" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'].get('pending_update_count',0))" 2>/dev/null)
    err=$(echo "$info" | python3 -c "import sys,json; e=json.load(sys.stdin)['result'].get('last_error_message',''); print(e if e else '')" 2>/dev/null)
    
    if [ -z "$url" ] || [ "$url" = "None" ]; then
        log "ERROR: $name webhook not set!"
        return 1
    fi
    
    if [ -n "$err" ] && [ "$err" != "None" ] && [ "$err" != "" ]; then
        log "WARN: $name webhook error: $err (pending: $pending)"
        return 1
    fi
    
    log "OK: $name webhook=$url pending=$pending"
    return 0
}

check_process() {
    local name=$1 pattern=$2
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        log "OK: $name process running"
        return 0
    else
        log "ERROR: $name process NOT running!"
        return 1
    fi
}

# Main checks
FAIL=0

check_process "smm-bot" "smm-bot/.venv/bin/python run.py" || FAIL=1
check_process "support-bot" "\.venv/bin/python -m app" || FAIL=1
check_webhook "SMM" "$SMM_TOKEN" || FAIL=1
check_webhook "Support" "$SUP_TOKEN" || FAIL=1

# Check webhook endpoint responsiveness
HTTP_SMM=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8081/telegram/webhook -d '{}' -H 'Content-Type: application/json' 2>/dev/null)
HTTP_SUP=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8780/telegram/webhook -d '{}' -H 'Content-Type: application/json' 2>/dev/null)

if [ "$HTTP_SMM" = "000" ]; then
    log "ERROR: smm-bot webhook endpoint not responding (HTTP $HTTP_SMM)"
    FAIL=1
else
    log "OK: smm-bot webhook endpoint HTTP $HTTP_SMM"
fi

if [ "$HTTP_SUP" = "000" ]; then
    log "ERROR: support-bot webhook endpoint not responding (HTTP $HTTP_SUP)"
    FAIL=1
else
    log "OK: support-bot webhook endpoint HTTP $HTTP_SUP"
fi

if [ $FAIL -eq 1 ]; then
    log "RECOVERY: restarting failed services..."
    supervisorctl restart smm-bot support-bot >> "$LOG" 2>&1
    sleep 10
    log "RECOVERY: done"
fi

# Rotate log if too big (>1MB)
if [ -f "$LOG" ]; then
    SIZE=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 1048576 ]; then
        mv "$LOG" "${LOG}.old"
    fi
fi

exit $FAIL
