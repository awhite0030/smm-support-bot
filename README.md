<div align="center">

<pre>
  ____  __  __ __  __   ____                              _
 / ___||  \/  |  \/  | / ___| _   _ _ __  _ __   ___  _ __| |_
 \___ \| |\/| | |\/| | \___ \| | | | '_ \| '_ \ / _ \| '__| __|
  ___) | |  | | |  | |  ___) | |_| | |_) | |_) | (_) | |  | |_
 |____/|_|  |_|_|  |_| |____/ \__,_| .__/| .__/ \___/|_|   \__|
                                   |_|   |_|
   Support Bot  ·  topics  ·  anti-spam  ·  SLA
</pre>

<br/>

<p>
  <strong>SMM Support Bot</strong> turns private Telegram messages into managed
  support topics — with anti-spam, Redis state, SLA jobs, and shop admin API hooks.
</p>

<p>
  <a href="#-why-smm-support-bot">Why</a> ·&nbsp;
  <a href="#-features">Features</a> ·&nbsp;
  <a href="#-architecture">Architecture</a> ·&nbsp;
  <a href="#-quick-start">Quick start</a> ·&nbsp;
  <a href="#-configuration">Config</a>
</p>

<p>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/awhite0030/smm-support-bot?style=for-the-badge&color=blue" alt="License"/></a>
  &nbsp;<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  &nbsp;<img src="https://img.shields.io/badge/aiogram-3-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="aiogram"/>
  &nbsp;<img src="https://img.shields.io/badge/Redis-state-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/>
  &nbsp;<img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
  &nbsp;<img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge" alt="PRs welcome"/>
</p>

<p>
  <img src="https://img.shields.io/github/stars/awhite0030/smm-support-bot?style=social" alt="Stars"/>
  &nbsp;<img src="https://img.shields.io/github/forks/awhite0030/smm-support-bot?style=social" alt="Forks"/>
  &nbsp;<img src="https://img.shields.io/github/last-commit/awhite0030/smm-support-bot?style=social" alt="Last commit"/>
</p>

</div>

---

## ✨ Why SMM Support Bot?

> *Commerce bots sell. Support bots keep the customers. This one bridges both.*

| Pain | What the bot does |
| --- | --- |
| Support buried in DMs | Creates / reuses a **topic per user** in a group |
| Spam floods operators | Anti-spam + throttling middleware |
| Lost conversation state | Redis-backed tickets, topics, rate limits |
| Missed SLAs | Background SLA job for stale tickets |
| Detached from shop | Optional admin API integration (`SHOP_ADMIN_KEY`) |

Fits Telegram shops, internal helpdesks, and “store bot + support bot” pairs.

---

## 🧩 Features

<table>
  <thead>
    <tr>
      <th align="left">Area</th>
      <th align="left">What you get</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Topics</strong></td>
      <td>Dedicated Telegram forum topics per user conversation</td>
    </tr>
    <tr>
      <td><strong>Bridge</strong></td>
      <td>Two-way relay between user DM and operator topic</td>
    </tr>
    <tr>
      <td><strong>Anti-spam</strong></td>
      <td>Throttling / rate limits to protect the support group</td>
    </tr>
    <tr>
      <td><strong>Redis state</strong></td>
      <td>Tickets, topic maps, and runtime limits in Redis</td>
    </tr>
    <tr>
      <td><strong>SLA jobs</strong></td>
      <td>Background control of open tickets and escalations</td>
    </tr>
    <tr>
      <td><strong>Media</strong></td>
      <td>Albums and attachments via middleware</td>
    </tr>
    <tr>
      <td><strong>Health</strong></td>
      <td>Healthcheck endpoint and scripts for uptime probes</td>
    </tr>
    <tr>
      <td><strong>Shop API</strong></td>
      <td>Hooks to external admin API of the commerce bot</td>
    </tr>
    <tr>
      <td><strong>Observability</strong></td>
      <td>Structured logging for production diagnostics</td>
    </tr>
  </tbody>
</table>

---

## 🏗 Architecture

```text
Telegram user (DM)
        │
        ▼
  Support bot
   ├─ anti-spam / throttling
   ├─ private handlers
   ├─ group topic handlers
   ├─ Redis state
   ├─ SLA background job
   └─ shop admin API
        │
        ▼
Telegram support group (topics)
```

### Layout

```text
app/
  __main__.py              # entrypoint
  config.py                # env config
  bot/handlers/private     # user DMs
  bot/handlers/group       # operator topics
  bot/middlewares          # Redis, throttle, albums
  bot/utils                # topics, texts, rate limits
  jobs/sla.py              # SLA background work
  health.py                # healthcheck
tests/
```

---

## ⚡ Quick start

```bash
git clone https://github.com/awhite0030/smm-support-bot.git
cd smm-support-bot

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill BOT_TOKEN, group id, Redis
python -m app
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

---

## ⚙ Configuration

Create `.env` from `.env.example`. Core variables:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `BOT_DEV_ID` | Admin / developer Telegram ID |
| `BOT_GROUP_ID` | Support group ID with topics enabled |
| `BOT_EMOJI_ID` | Emoji ID for created topics |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Redis connection |
| `SHOP_ADMIN_KEY` / `ADMIN_API_KEY` | Optional shop admin API auth |

---

## 🧪 Stack

`Python 3.10+` · `aiogram 3` · `Redis` · `Docker Compose` · `pytest` · structured logging

---

## 📊 Stats

<p>
  <img src="https://img.shields.io/github/languages/top/awhite0030/smm-support-bot?style=flat-square" alt="Top language"/>
  &nbsp;<img src="https://img.shields.io/github/repo-size/awhite0030/smm-support-bot?style=flat-square" alt="Repo size"/>
  &nbsp;<img src="https://img.shields.io/github/last-commit/awhite0030/smm-support-bot?style=flat-square" alt="Last commit"/>
  &nbsp;<img src="https://img.shields.io/github/issues/awhite0030/smm-support-bot?style=flat-square" alt="Issues"/>
</p>

---

## 📄 License

[MIT](LICENSE) © 2026 A. White.

<sub>Every DM deserves a topic. Every ticket deserves an SLA.</sub>
