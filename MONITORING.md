# 📊 Monitoring Setup Guide

## Uptime Robot (бесплатно)

### 1. Создать аккаунт
https://uptimerobot.com/signUp

### 2. Добавить монитор
- Type: HTTP(s)
- URL: `https://your-server.com/health` (если есть health endpoint)
- Monitoring Interval: 5 minutes
- Alert Contacts: ваш email/telegram

### 3. Настроить алерты
- Email при downtime
- Telegram через @uptimerobot_bot

---

## Telegram Alerts (простой вариант)

### Создать бота для алертов
```bash
# 1. Создать бота у @BotFather
# 2. Получить TOKEN
# 3. Получить свой CHAT_ID от @userinfobot

# 4. Добавить функцию в код
cat >> app/alerts.py << 'EOF'
import requests
import os

ALERT_BOT_TOKEN = os.getenv("ALERT_BOT_TOKEN")
ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID")

def send_alert(message: str, level: str = "warning"):
    emoji = "⚠️" if level == "warning" else "🔴"
    text = f"{emoji} <b>Support Bot Alert</b>\n\n{message}"
    
    requests.post(
        f"https://api.telegram.org/bot{ALERT_BOT_TOKEN}/sendMessage",
        json={"chat_id": ALERT_CHAT_ID, "text": text, "parse_mode": "HTML"}
    )
EOF

# 5. Добавить в .env
echo "ALERT_BOT_TOKEN=your_token" >> .env
echo "ALERT_CHAT_ID=your_chat_id" >> .env
```

### Использование
```python
from app.alerts import send_alert

# При критичной ошибке
try:
    await some_operation()
except Exception as e:
    send_alert(f"Database error: {e}", level="critical")
    raise
```

---

## Health Check Endpoint

### Добавить в supervisor
```bash
# Создать скрипт проверки
cat > /home/support-bot/scripts/health_check.sh << 'EOF'
#!/bin/bash
cd /home/support-bot
source .venv/bin/activate

python3 -c "
from app.health import health_check
import asyncio
import sys

result = asyncio.run(health_check())
if result['status'] != 'healthy':
    print(f'UNHEALTHY: {result}')
    sys.exit(1)
print('OK')
"
EOF

chmod +x /home/support-bot/scripts/health_check.sh

# Добавить в crontab для проверки каждые 5 минут
crontab -e
# */5 * * * * /home/support-bot/scripts/health_check.sh || echo "Health check failed" | mail -s "Support Bot Alert" your@email.com
```

---

## Sentry (для ошибок)

### 1. Создать аккаунт
https://sentry.io/signup/

### 2. Создать проект
- Platform: Python
- Скопировать DSN

### 3. Установить SDK
```bash
pip install sentry-sdk
```

### 4. Добавить в код
```python
# app/__main__.py
import sentry_sdk

sentry_sdk.init(
    dsn="your-dsn-here",
    traces_sample_rate=0.1,
    environment="production"
)
```

---

## Grafana + Prometheus (продвинутый вариант)

### 1. Установить Prometheus
```bash
docker run -d -p 9090:9090 \
  -v /home/support-bot/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

### 2. Добавить метрики в бота
```bash
pip install prometheus-client
```

```python
# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Метрики
tickets_created = Counter('tickets_created_total', 'Total tickets created')
tickets_closed = Counter('tickets_closed_total', 'Total tickets closed')
response_time = Histogram('response_time_seconds', 'Response time')
active_tickets = Gauge('active_tickets', 'Currently active tickets')

# Запустить metrics endpoint
start_http_server(8000)  # метрики на :8000/metrics
```

### 3. Настроить Grafana
```bash
docker run -d -p 3000:3000 grafana/grafana
# Открыть http://localhost:3000
# Добавить Prometheus data source
# Импортировать дашборд
```

---

## Простой мониторинг через cron

### Скрипт проверки
```bash
cat > /home/support-bot/scripts/monitor.sh << 'EOF'
#!/bin/bash

# Проверить процесс
if ! pgrep -f "python -m app" > /dev/null; then
    echo "❌ Bot is not running!"
    supervisorctl start support-bot
    # Отправить алерт
fi

# Проверить CPU
CPU=$(ps aux | grep "python -m app" | awk '{print $3}' | head -1)
if (( $(echo "$CPU > 80" | bc -l) )); then
    echo "⚠️ High CPU: $CPU%"
fi

# Проверить RAM
RAM=$(ps aux | grep "python -m app" | awk '{print $4}' | head -1)
if (( $(echo "$RAM > 80" | bc -l) )); then
    echo "⚠️ High RAM: $RAM%"
fi

# Проверить ошибки в логах
ERRORS=$(tail -100 /dev/shm/support-bot_err.log | grep -i "error\|exception" | wc -l)
if [ $ERRORS -gt 10 ]; then
    echo "⚠️ Many errors in logs: $ERRORS"
fi
EOF

chmod +x /home/support-bot/scripts/monitor.sh

# Добавить в crontab
crontab -e
# */5 * * * * /home/support-bot/scripts/monitor.sh
```

---

## Рекомендуемая стратегия

**Минимум (бесплатно):**
1. Uptime Robot для проверки доступности
2. Telegram алерты для критичных ошибок
3. Cron скрипт для базового мониторинга

**Рекомендуемый (для продакшена):**
1. Uptime Robot
2. Sentry для ошибок
3. Telegram алерты
4. Health check endpoint
5. Логирование в файлы с ротацией

**Продвинутый (для больших нагрузок):**
1. Prometheus + Grafana
2. Sentry
3. ELK Stack для логов
4. PagerDuty для алертов
5. Custom дашборды

---

## Метрики для отслеживания

**Технические:**
- Uptime (%)
- Response time (ms)
- CPU usage (%)
- RAM usage (MB)
- Error rate (errors/min)

**Бизнес:**
- Tickets created (count)
- Tickets closed (count)
- Average response time (min)
- CSAT score (1-5)
- Active tickets (count)

**Алерты:**
- Bot down > 5 min → critical
- CPU > 80% for 10 min → warning
- RAM > 80% → warning
- Error rate > 10/min → warning
- Active tickets > 200 → info
