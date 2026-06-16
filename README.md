# SMM Support Bot

Telegram-бот для поддержки пользователей: обращения из личных сообщений превращаются в управляемые топики в Telegram-группе, проходят антиспам, SLA-контроль, маршрутизацию и интеграцию с административным API магазина.

## Русская версия

### Назначение

`SMM Support Bot` закрывает типовой процесс поддержки для Telegram commerce-проектов: пользователь пишет боту, бот создает или находит связанный support-topic, пересылает сообщения оператору, сохраняет состояние в Redis, применяет rate limit и помогает команде не терять обращения.

Проект подходит как основа для:

- клиентской поддержки Telegram-магазина;
- внутреннего helpdesk-бота;
- связки "бот магазина + отдельный бот поддержки";
- модерации входящих обращений с антиспамом и SLA.

### Основные возможности

- Создание отдельных Telegram topics под обращения пользователей.
- Двусторонняя пересылка сообщений между пользователем и операторским топиком.
- Антиспам и throttling для защиты от повторяющихся сообщений.
- Redis-backed состояние обращений, топиков и rate limits.
- SLA job для контроля обращений и автоматизации регламентных действий.
- Поддержка альбомов и вложений через middleware.
- Healthcheck endpoint и отдельные healthcheck scripts.
- Интеграция с внешним admin API магазина через `SHOP_ADMIN_KEY` / `ADMIN_API_KEY`.
- Structured logging для продакшен-диагностики.
- Docker Compose конфигурация для бота и Redis.

### Архитектура

```text
Telegram user
    |
    v
Support bot
    |
    +-- anti-spam / throttling
    +-- private handlers
    +-- group topic handlers
    +-- Redis state
    +-- SLA background job
    +-- shop admin API integration
    |
    v
Telegram support group topics
```

Ключевые директории:

- `app/__main__.py` - точка запуска приложения.
- `app/config.py` - загрузка конфигурации из переменных окружения.
- `app/bot/handlers/private` - обработчики личных сообщений пользователей.
- `app/bot/handlers/group` - обработчики сообщений операторов в топиках.
- `app/bot/middlewares` - Redis, throttling, albums и служебные middleware.
- `app/bot/utils` - создание топиков, тексты, rate limits, интеграция с магазином.
- `app/jobs/sla.py` - фоновые SLA-задачи.
- `app/health.py` - healthcheck.
- `tests` - базовые и интеграционные проверки.

### Технологии

- Python 3.10+
- aiogram 3
- Redis
- Docker / Docker Compose
- pytest
- structured logging

### Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

Для Docker:

```bash
cp .env.example .env
docker compose up --build
```

### Переменные окружения

Создайте `.env` на основе `.env.example`.

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | Токен Telegram-бота из BotFather. |
| `BOT_DEV_ID` | Telegram ID администратора или разработчика. |
| `BOT_GROUP_ID` | ID support-группы с включенными topics. |
| `BOT_EMOJI_ID` | Emoji ID для создаваемых топиков. |
| `REDIS_HOST` | Хост Redis. |
| `REDIS_PORT` | Порт Redis. |
| `REDIS_DB` | Номер Redis DB. |
| `REDIS_PASSWORD` | Пароль Redis, если используется. |
| `SHOP_ADMIN_KEY` | Ключ доступа к admin API магазина. |
| `ADMIN_API_KEY` | Альтернативное имя ключа admin API. |
| `SHOP_API_BASE_URL` | Базовый URL API магазина. |
| `LOG_LEVEL` | Уровень логирования. |

### Безопасность

- Реальные `.env`, токены, ключи, логи, базы, дампы и backup-файлы не должны попадать в Git.
- Все секреты передаются только через переменные окружения.
- `SHOP_ADMIN_KEY` / `ADMIN_API_KEY` должен быть отдельным сервисным ключом с минимально нужными правами.
- Support-группа должна быть закрытой, а бот должен иметь только необходимые Telegram-права.
- Redis рекомендуется закрывать сетевыми правилами и паролем, если он доступен вне localhost/Docker network.

### Тестирование

```bash
pip install -r requirements-dev.txt
pytest
```

Для smoke-проверки:

```bash
python healthcheck.py
./healthcheck.sh
```

### Production checklist

- Создать отдельного Telegram-бота для поддержки.
- Включить topics в support-группе.
- Выдать боту права на управление topics.
- Заполнить `.env` реальными значениями на сервере.
- Проверить Redis connectivity.
- Проверить healthcheck.
- Настроить логирование и ротацию логов на уровне инфраструктуры.
- Не публиковать `.env`, production logs, Redis dumps и клиентские выгрузки.

## English version

### Purpose

`SMM Support Bot` is a Telegram support workflow for commerce and SMM automation projects. A user writes to the bot, the bot creates or reuses a Telegram support topic, routes messages to operators, keeps state in Redis, applies anti-spam rules, and supports SLA automation.

It can be used as:

- a customer support bot for a Telegram shop;
- an internal helpdesk bot;
- a bridge between a shop bot and a support team;
- an anti-spam and SLA-aware intake layer for user requests.

### Features

- Dedicated Telegram topics for user requests.
- Two-way forwarding between private user chats and operator topics.
- Anti-spam and throttling middleware.
- Redis-backed request, topic, and rate-limit state.
- SLA background job for operational control.
- Album and attachment handling.
- Healthcheck endpoint and scripts.
- Integration with an external shop admin API through `SHOP_ADMIN_KEY` / `ADMIN_API_KEY`.
- Structured logging for production diagnostics.
- Docker Compose setup for the bot and Redis.

### Architecture

```text
Telegram user
    |
    v
Support bot
    |
    +-- anti-spam / throttling
    +-- private handlers
    +-- group topic handlers
    +-- Redis state
    +-- SLA background job
    +-- shop admin API integration
    |
    v
Telegram support group topics
```

Important directories:

- `app/__main__.py` - application entry point.
- `app/config.py` - environment configuration.
- `app/bot/handlers/private` - private chat handlers.
- `app/bot/handlers/group` - operator topic handlers.
- `app/bot/middlewares` - Redis, throttling, album, and service middleware.
- `app/bot/utils` - topic creation, texts, rate limits, and shop integration.
- `app/jobs/sla.py` - SLA background jobs.
- `app/health.py` - healthcheck logic.
- `tests` - basic and integration tests.

### Stack

- Python 3.10+
- aiogram 3
- Redis
- Docker / Docker Compose
- pytest
- structured logging

### Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

Docker:

```bash
cp .env.example .env
docker compose up --build
```

### Environment

Create `.env` from `.env.example`.

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from BotFather. |
| `BOT_DEV_ID` | Telegram admin/developer ID. |
| `BOT_GROUP_ID` | Support group ID with topics enabled. |
| `BOT_EMOJI_ID` | Emoji ID used for created topics. |
| `REDIS_HOST` | Redis host. |
| `REDIS_PORT` | Redis port. |
| `REDIS_DB` | Redis DB number. |
| `REDIS_PASSWORD` | Redis password, if enabled. |
| `SHOP_ADMIN_KEY` | Service key for shop admin API access. |
| `ADMIN_API_KEY` | Alternative admin API key variable. |
| `SHOP_API_BASE_URL` | Shop API base URL. |
| `LOG_LEVEL` | Logging level. |

### Security

- Never commit real `.env` files, tokens, keys, logs, databases, dumps, backups, or customer exports.
- Runtime secrets must be passed through environment variables only.
- Use a separate service key with minimal permissions for shop admin API calls.
- Keep the support group private and give the bot only the required Telegram permissions.
- Protect Redis with network rules and a password when it is reachable outside localhost or a private Docker network.

### Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Smoke checks:

```bash
python healthcheck.py
./healthcheck.sh
```

### Production checklist

- Create a dedicated Telegram support bot.
- Enable topics in the support group.
- Grant the bot topic management permissions.
- Fill `.env` on the server with real values.
- Verify Redis connectivity.
- Verify healthchecks.
- Configure log rotation at the infrastructure level.
- Keep `.env`, production logs, Redis dumps, and customer exports out of Git.
