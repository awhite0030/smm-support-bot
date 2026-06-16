"""Read-only access to ClerkStore shop database for support context."""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg
import aiohttp

logger = logging.getLogger(__name__)

DB_URL = os.getenv("SHOP_DB_URL", "")
ADMIN_API_BASE = os.getenv("SHOP_ADMIN_API", "http://127.0.0.1:8080/api/admin")
ADMIN_API_KEY = os.getenv("SHOP_ADMIN_KEY", "")
SUPPORT_DB_PATH = os.getenv("SUPPORT_DB_PATH", "")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> Optional[asyncpg.Pool]:
    global _pool
    db_url = DB_URL or os.getenv("SHOP_DB_URL", "")
    if not db_url:
        return None
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                db_url,
                min_size=2,
                max_size=10,
                command_timeout=10,
            )
        except Exception:
            return None
    return _pool


def fmt_money(amount, currency: str = "RUB") -> str:
    if amount is None:
        return "—"
    sym = {"RUB": "₽", "USD": "$", "EUR": "€"}.get(currency, currency)
    return f"{float(amount):.2f} {sym}"


def fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d.%m.%Y %H:%M")


async def fetch_user_summary(tg_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                """SELECT u.telegram_id, u.balance, u.referral_id, u.registration_date,
                          u.is_blocked, u.language, r.name AS role_name
                   FROM users u
                   LEFT JOIN roles r ON r.id = u.role_id
                   WHERE u.telegram_id = $1""",
                tg_id,
            )
            if not user:
                return None

            tipzy_stats = await conn.fetchrow(
                """SELECT COUNT(*) AS total,
                          COUNT(*) FILTER (WHERE status='completed') AS completed,
                          COUNT(*) FILTER (WHERE status IN ('pending','processing','in_progress')) AS pending,
                          COUNT(*) FILTER (WHERE status='failed') AS failed,
                          COUNT(*) FILTER (WHERE status='refunded') AS refunded,
                          COALESCE(SUM(price_paid), 0) AS spent_smm,
                          MAX(created_at) AS last_at
                   FROM tipzy_orders WHERE user_id = $1""",
                tg_id,
            )

            goods_stats = await conn.fetchrow(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(price), 0) AS spent_goods,
                          MAX(bought_datetime) AS last_at
                   FROM bought_goods WHERE buyer_id = $1""",
                tg_id,
            )

            payments_stats = await conn.fetchrow(
                """SELECT COUNT(*) FILTER (WHERE status='paid') AS paid_count,
                          COALESCE(SUM(amount) FILTER (WHERE status='paid'), 0) AS deposited
                   FROM payments WHERE user_id = $1""",
                tg_id,
            )

            last_orders = await conn.fetch(
                """SELECT id, link, quantity, price_paid, status, tipzy_status,
                          tipzy_remains, error_message, created_at
                   FROM tipzy_orders
                   WHERE user_id = $1
                   ORDER BY created_at DESC LIMIT 5""",
                tg_id,
            )

            last_goods = await conn.fetch(
                """SELECT unique_id, item_name, price, bought_datetime
                   FROM bought_goods
                   WHERE buyer_id = $1
                   ORDER BY bought_datetime DESC LIMIT 5""",
                tg_id,
            )

            last_payment = await conn.fetchrow(
                """SELECT amount, currency, provider, status, created_at
                   FROM payments
                   WHERE user_id = $1 AND status = 'paid'
                   ORDER BY created_at DESC LIMIT 1""",
                tg_id,
            )

            failed_orders = await conn.fetch(
                """SELECT id, link, quantity, price_paid, status, error_message, created_at
                   FROM tipzy_orders
                   WHERE user_id = $1 AND status IN ('failed','refunded','cancelled')
                   ORDER BY created_at DESC LIMIT 3""",
                tg_id,
            )

            reviews = await conn.fetch(
                """SELECT rating, text, item_name, created_at
                   FROM reviews
                   WHERE user_id = $1
                   ORDER BY created_at DESC LIMIT 3""",
                tg_id,
            )

            return {
                "user": dict(user),
                "tipzy_stats": dict(tipzy_stats) if tipzy_stats else {},
                "goods_stats": dict(goods_stats) if goods_stats else {},
                "payments_stats": dict(payments_stats) if payments_stats else {},
                "last_orders": [dict(r) for r in last_orders],
                "last_goods": [dict(r) for r in last_goods],
                "last_payment": dict(last_payment) if last_payment else None,
                "failed_orders": [dict(r) for r in failed_orders],
                "reviews": [dict(r) for r in reviews],
            }
    except Exception as e:
        import logging
        logging.exception(f"shop_db fetch failed: {e}")
        return None


_STATUS_EMOJI = {
    "completed": "✅", "pending": "⏳", "processing": "⚙️",
    "in_progress": "⚙️", "failed": "❌", "refunded": "↩️",
    "cancelled": "🚫", "paid": "💰",
}


async def render_shop_card(tg_id: int, use_cache: bool = True) -> Optional[str]:
    # Note: Redis caching disabled — was creating new connections per call.
    # Add proper shared Redis client if needed.
    _ = use_cache  # silenced
    data = await fetch_user_summary(tg_id)
    if not data:
        return None

    u = data["user"]
    ts = data["tipzy_stats"]
    gs = data["goods_stats"]
    ps = data["payments_stats"]
    pay = data["last_payment"]
    orders = data["last_orders"]
    goods = data["last_goods"]

    lines = [
        "🛒 <b>ClerkStore — карточка клиента</b>",
        "",
        f"💳 Баланс: <b>{fmt_money(u.get('balance'))}</b>",
        f"⬆️ Пополнено всего: <b>{fmt_money(ps.get('deposited'))}</b> "
        f"({ps.get('paid_count') or 0} платежей)",
    ]

    spent_total = float(ts.get("spent_smm") or 0) + float(gs.get("spent_goods") or 0)
    lines.append(f"⬇️ Потрачено всего: <b>{spent_total:.2f} ₽</b>")
    lines.append(f"📅 С нами с: <b>{fmt_dt(u.get('registration_date'))}</b>")
    lines.append(f"🌐 Язык: {u.get('language') or 'ru'}")
    if u.get("role_name"):
        lines.append(f"🎖 Роль: <b>{u['role_name']}</b>")
    if u.get("is_blocked"):
        lines.append("🚫 <b>Заблокирован в магазине</b>")
    if u.get("referral_id"):
        lines.append(f"👥 Приведён: <code>{u['referral_id']}</code>")

    smm_total = ts.get("total") or 0
    goods_total = gs.get("total") or 0
    if smm_total or goods_total:
        lines.append("")
        if smm_total:
            lines.append(
                f"📦 <b>SMM-заказы:</b> {smm_total} "
                f"(✅ {ts.get('completed') or 0}  "
                f"⏳ {ts.get('pending') or 0}  "
                f"❌ {ts.get('failed') or 0}  "
                f"↩️ {ts.get('refunded') or 0})"
            )
            lines.append(f"   Потрачено: <b>{fmt_money(ts.get('spent_smm'))}</b>")
            if ts.get("last_at"):
                lines.append(f"   Последний: {fmt_dt(ts.get('last_at'))}")
        if goods_total:
            lines.append(f"🛍 <b>Аккаунты/товары:</b> {goods_total} шт.")
            lines.append(f"   Потрачено: <b>{fmt_money(gs.get('spent_goods'))}</b>")
            if gs.get("last_at"):
                lines.append(f"   Последний: {fmt_dt(gs.get('last_at'))}")
    else:
        lines.append("")
        lines.append("📦 <i>Покупок пока нет</i>")

    if pay:
        lines.append("")
        lines.append(
            f"💰 Последний платёж: <b>{fmt_money(pay['amount'], pay['currency'])}</b> "
            f"({pay['provider']}, {fmt_dt(pay['created_at'])})"
        )

    if orders:
        lines.append("")
        lines.append("<b>Последние SMM-заказы:</b>")
        for o in orders:
            em = _STATUS_EMOJI.get(str(o["status"]), "•")
            tail = ""
            if o.get("tipzy_remains") is not None and o["status"] in ("processing", "in_progress"):
                tail = f"  осталось: {o['tipzy_remains']}"
            link = (o.get("link") or "")[:40]
            lines.append(
                f"{em} #{o['id']} × {o['quantity']} — "
                f"{fmt_money(o['price_paid'])} ({fmt_dt(o['created_at'])}){tail}"
            )
            if link:
                lines.append(f"    🔗 <code>{link}</code>")
            if o.get("error_message"):
                err = str(o["error_message"])[:80]
                lines.append(f"    ⚠️ <i>{err}</i>")

    if goods:
        lines.append("")
        lines.append("<b>Последние товары:</b>")
        for g in goods:
            lines.append(
                f"🛍 <code>{g['unique_id']}</code> {g['item_name']} — "
                f"{fmt_money(g['price'])} ({fmt_dt(g['bought_datetime'])})"
            )

    failed = data.get("failed_orders") or []
    if failed:
        lines.append("")
        lines.append("⚠️ <b>Проблемные заказы:</b>")
        for o in failed:
            em = _STATUS_EMOJI.get(str(o["status"]), "•")
            lines.append(
                f"{em} #{o['id']} — {o['status']} ({fmt_dt(o['created_at'])})"
            )
            if o.get("error_message"):
                err = str(o["error_message"])[:100]
                lines.append(f"    <i>{err}</i>")

    revs = data.get("reviews") or []
    if revs:
        lines.append("")
        lines.append("⭐ <b>Отзывы клиента:</b>")
        for r in revs:
            stars = "⭐" * int(r.get("rating") or 0)
            txt = (r.get("text") or "").strip()
            head = f"{stars} {r.get('item_name','')}"
            if txt:
                short = txt[:120].replace("\n", " ")
                head += f" — <i>{short}</i>"
            lines.append(head)

    return "\n".join(lines)


# ─── HTTP actions to shop admin API ──────────────────────────────────────

async def _admin_request(method: str, path: str, json_body: dict | None = None) -> dict:
    if not ADMIN_API_KEY:
        return {"ok": False, "error": "SHOP_ADMIN_KEY not configured"}
    url = ADMIN_API_BASE.rstrip("/") + path
    headers = {"X-Admin-Key": ADMIN_API_KEY}
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, url, json=json_body, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    return {"ok": False, "status": resp.status, "error": text[:300]}
                try:
                    return {"ok": True, "data": await resp.json()}
                except Exception:
                    return {"ok": True, "data": {"raw": text}}
    except Exception as e:
        logger.exception("admin api request failed")
        return {"ok": False, "error": str(e)}


async def block_user(tg_id: int) -> dict:
    """Toggle block status via shop API. Callers must check current state first."""
    return await _admin_request("POST", f"/users/{tg_id}/block", {})


async def topup_balance(tg_id: int, amount: float, comment: str = "support topup") -> dict:
    return await _admin_request(
        "POST", f"/users/{tg_id}/balance",
        {"amount": amount},
    )


async def refund_order(order_id: int) -> dict:
    return await _admin_request("POST", f"/orders/{order_id}/refund", {})


async def refresh_order(order_id: int) -> dict:
    return await _admin_request("POST", f"/orders/{order_id}/refresh", {})


async def render_order_card(uid: str) -> Optional[str]:
    """Lookup order by id (number) or unique_id (digits)."""
    pool = await get_pool()
    if pool is None:
        return None
    uid = uid.strip().lstrip("#")
    if not uid.isdigit():
        return None
    n = int(uid)
    try:
        async with pool.acquire() as conn:
            tipzy = await conn.fetchrow(
                """SELECT id, user_id, link, quantity, price_paid, status, tipzy_status,
                          tipzy_order_id, tipzy_start_count, tipzy_remains, tipzy_charge,
                          error_message, created_at, updated_at
                   FROM tipzy_orders WHERE id = $1""",
                n,
            )
            if tipzy:
                o = dict(tipzy)
                em = _STATUS_EMOJI.get(str(o["status"]), "•")
                lines = [
                    f"📦 <b>SMM-заказ #{o['id']}</b>",
                    "",
                    f"{em} Статус: <b>{o['status']}</b>",
                    f"👤 Клиент: <code>{o['user_id']}</code>",
                    f"🔗 Ссылка: <code>{(o.get('link') or '')[:80]}</code>",
                    f"🔢 Количество: <b>{o['quantity']}</b>",
                    f"💵 Сумма: <b>{fmt_money(o['price_paid'])}</b>",
                    f"📅 Создан: {fmt_dt(o['created_at'])}",
                    f"🔄 Обновлён: {fmt_dt(o['updated_at'])}",
                ]
                if o.get("tipzy_order_id"):
                    lines.append("")
                    lines.append("<b>Tipzy:</b>")
                    lines.append(f"  ID: <code>{o['tipzy_order_id']}</code>")
                    if o.get("tipzy_status"):
                        lines.append(f"  Статус: {o['tipzy_status']}")
                    if o.get("tipzy_start_count") is not None:
                        lines.append(f"  Старт: {o['tipzy_start_count']}")
                    if o.get("tipzy_remains") is not None:
                        lines.append(f"  Осталось: {o['tipzy_remains']}")
                    if o.get("tipzy_charge") is not None:
                        lines.append(f"  Charge: {o['tipzy_charge']}")
                if o.get("error_message"):
                    lines.append("")
                    lines.append(f"⚠️ <i>{o['error_message']}</i>")
                return "\n".join(lines)

            good = await conn.fetchrow(
                """SELECT unique_id, item_name, value, price, buyer_id, bought_datetime
                   FROM bought_goods WHERE unique_id = $1""",
                n,
            )
            if good:
                g = dict(good)
                value = (g.get("value") or "")
                if len(value) > 200:
                    value = value[:200] + "…"
                return (
                    f"🛍 <b>Товар <code>{g['unique_id']}</code></b>\n\n"
                    f"📦 {g['item_name']}\n"
                    f"👤 Покупатель: <code>{g['buyer_id']}</code>\n"
                    f"💵 Цена: <b>{fmt_money(g['price'])}</b>\n"
                    f"📅 Куплен: {fmt_dt(g['bought_datetime'])}\n\n"
                    f"<b>Содержимое:</b>\n<pre>{value}</pre>"
                )
            return None
    except Exception:
        return None


async def topup_user(tg_id: int, amount: float) -> Optional[dict]:
    return await _admin_post(f"/users/{tg_id}/balance/add", {"amount": float(amount)})


async def render_information_extras(tg_id: int) -> Optional[str]:
    """Compact additional info block for /information command in support topic."""
    summary = await fetch_user_summary(tg_id)

    out: list[str] = []

    if summary:
        u = summary["user"]
        ts = summary.get("tipzy_stats") or {}
        gs = summary.get("goods_stats") or {}
        ps = summary.get("payments_stats") or {}
        lp = summary.get("last_payment")
        last_orders = summary.get("last_orders") or []

        balance = u.get("balance") or 0
        deposited = ps.get("deposited") or 0
        paid_count = ps.get("paid_count") or 0
        spent_total = float(ts.get("spent_smm") or 0) + float(gs.get("spent_goods") or 0)

        shop_lines = ["", "", "📊 <b>Магазин</b>"]
        shop_lines.append(f"• Баланс: <b>{fmt_money(balance)}</b>")
        shop_lines.append(
            f"• Пополнений: {paid_count} на <b>{fmt_money(deposited)}</b>"
        )
        shop_lines.append(
            f"• Потрачено: <b>{fmt_money(spent_total)}</b>"
        )
        if ts.get("total"):
            shop_lines.append(
                f"• SMM-заказов: {ts.get('total', 0)} "
                f"(✅ {ts.get('completed', 0)}, ⏳ {ts.get('pending', 0)}, "
                f"❌ {ts.get('failed', 0)}, ↩️ {ts.get('refunded', 0)})"
            )
        if gs.get("total"):
            shop_lines.append(
                f"• Цифровых товаров: {gs.get('total', 0)} на {fmt_money(gs.get('spent_goods') or 0)}"
            )
        if last_orders:
            o = last_orders[0]
            emoji = _STATUS_EMOJI.get(o.get("status", ""), "•")
            shop_lines.append(
                f"• Последний заказ: {emoji} <code>{o['id']}</code> ({fmt_dt(o.get('created_at'))})"
            )
        if lp:
            shop_lines.append(
                f"• Последняя оплата: {fmt_money(lp.get('amount') or 0)} "
                f"через {lp.get('provider') or '—'} ({fmt_dt(lp.get('created_at'))})"
            )
        if u.get("referral_id"):
            shop_lines.append(f"• Реферал: <code>{u.get('referral_id')}</code>")
        if u.get("role_name"):
            shop_lines.append(f"• Роль: {u.get('role_name')}")
        if u.get("language"):
            shop_lines.append(f"• Язык: {u.get('language')}")

        out.append("\n".join(shop_lines))

    # Tickets section from local sqlite
    db_path = SUPPORT_DB_PATH
    try:
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_n,
                       SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed_n,
                       AVG(csat_rating) AS avg_csat,
                       MAX(last_msg_at) AS last_msg_at
                   FROM tickets WHERE tg_id = ?""",
                (tg_id,),
            )).fetchone()
            if row and (row["total"] or 0) > 0:
                t_lines = ["", "", "🎫 <b>Поддержка</b>"]
                t_lines.append(
                    f"• Тикетов: {row['total']} (открыто {row['open_n'] or 0}, закрыто {row['closed_n'] or 0})"
                )
                if row["avg_csat"] is not None:
                    t_lines.append(f"• Средний CSAT: ⭐ {round(float(row['avg_csat']), 2)}")
                if row["last_msg_at"]:
                    t_lines.append(f"• Последнее обращение: {row['last_msg_at']}")
                out.append("\n".join(t_lines))
    except Exception:
        pass

    if not out:
        return None
    return "\n".join(out)
