"""Support API exposed to the admin panel.

Backed by tickets storage on powabase (support schema, shared shop DB).
Bind to 127.0.0.1; the admin app proxies these calls and injects X-Admin-Key.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, field_validator
from app.db import tickets as ticket_db
from .security import SecurityMiddleware, init_security, PII_Filter
from app.bot.utils.shop_db import get_pool as get_shop_pool

log = logging.getLogger(__name__)


def _admin_key() -> str:
    return os.getenv("SHOP_ADMIN_KEY", "") or os.getenv("ADMIN_API_KEY", "")


def _group_id() -> int:
    return int(os.getenv("SUPPORT_GROUP_ID", "0") or 0)


def _topic_url(topic_id: int | None) -> str | None:
    if not topic_id or not _group_id():
        return None
    gid = str(_group_id()).removeprefix("-100")
    return f"https://t.me/c/{gid}/{topic_id}"



class TemplateCreate(BaseModel):
    slug: str
    title: str
    text: str = ""
    display_order: int = 0

    @field_validator("slug", "title")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class TemplateUpdate(BaseModel):
    slug: str | None = None
    title: str | None = None
    text: str | None = None
    display_order: int | None = None
    active: bool | None = None


app = FastAPI(title="Support API", docs_url=None, redoc_url=None)
app.add_middleware(SecurityMiddleware)


def _auth(key: str | None) -> None:
    actual = _admin_key()
    if not actual or not key or not hmac.compare_digest(key, actual):
        raise HTTPException(401, "unauthorized")


@app.get("/health")
async def health(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> dict:
    """Health check — requires admin key to prevent enumeration."""
    _auth(x_admin_key)
    return {"ok": True}


@app.get("/api/support/stats")
async def stats(
    days: int = Query(30, ge=1, le=365),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    s = await ticket_db.stats()
    # Map to fields the admin UI expects
    return {
        "open_n": s.get("open", 0),
        "closed_n": s.get("closed_today", 0),
        "avg_response_sec": s.get("avg_response_sec"),
        "avg_csat": s.get("avg_csat"),
    }


@app.get("/api/support/tickets")
async def list_tickets(
    status: str | None = Query(None, pattern="^(open|waiting_user|closed)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    res = await ticket_db.list_tickets(status=status, limit=limit, offset=offset)
    for r in res.get("items", []):
        r["tg_id"] = r.get("user_id")
        r["topic_url"] = _topic_url(r.get("topic_id"))
    return res


@app.get("/api/support/tickets/{tid}")
async def get_ticket(
    tid: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    pool = await get_shop_pool()
    if pool is None:
        raise HTTPException(503, "db_unavailable")
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM support.tickets WHERE id=$1", tid)
    if not row:
        raise HTTPException(404, "not_found")
    d = dict(row)
    for k in ("created_at", "closed_at", "updated_at", "last_user_msg_at", "last_admin_msg_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    d["tg_id"] = d.get("user_id")
    d["topic_url"] = _topic_url(d.get("topic_id"))
    return d


@app.post("/api/support/tickets/{tid}/close")
async def close_ticket_endpoint(
    tid: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    topic_id = await ticket_db.close_ticket_by_id(tid)
    if topic_id is None:
        # already closed or not found
        return {"ok": True, "already_closed": True}
    return {"ok": True, "topic_id": topic_id}


@app.get("/api/support/users/{tg_id}/tickets")
async def user_tickets(
    tg_id: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    pool = await get_shop_pool()
    if pool is None:
        return {"open_count": 0, "items": []}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, user_id, topic_id, category, status, created_at, closed_at "
            "FROM support.tickets WHERE user_id=$1 ORDER BY id DESC LIMIT 20",
            tg_id,
        )
    items: list[dict[str, Any]] = []
    open_count = 0
    for r in rows:
        d = dict(r)
        d["tg_id"] = d.get("user_id")
        d["topic_url"] = _topic_url(d.get("topic_id"))
        for k in ("created_at", "closed_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        if d.get("status") != "closed":
            open_count += 1
        items.append(d)
    return {"open_count": open_count, "items": items}

# ─── FAQ Management ─────────────────────────────────────────────────────────

@app.get("/api/support/faq")
async def get_all_faq(x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    """List all FAQ items (admin view)."""
    _auth(x_admin_key)
    return await ticket_db.list_all_faq()

@app.post("/api/support/faq")
async def create_faq_item(
    slug: str,
    question: str,
    answer: str,
    display_order: int = 0,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key")
):
    """Create a new FAQ item."""
    _auth(x_admin_key)
    # Sanitize HTML to prevent XSS (bleach strips all dangerous tags/attrs)
    import bleach
    question = bleach.clean(question, tags=[], strip=True)
    answer = bleach.clean(answer, tags=[], strip=True)
    faq_id = await ticket_db.create_faq(slug, question, answer, display_order)
    return {"id": faq_id}

@app.patch("/api/support/faq/{faq_id}")
async def update_faq_item(
    faq_id: int,
    question: str = None,
    answer: str = None,
    display_order: int = None,
    active: bool = None,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key")
):
    """Update FAQ item."""
    _auth(x_admin_key)
    # Sanitize HTML to prevent XSS
    import bleach
    if question:
        question = bleach.clean(question, tags=[], strip=True)
    if answer:
        answer = bleach.clean(answer, tags=[], strip=True)
    ok = await ticket_db.update_faq(faq_id, question, answer, display_order, active)
    return {"ok": ok}

@app.delete("/api/support/faq/{faq_id}")
async def delete_faq_item(faq_id: int, x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    """Delete FAQ item."""
    _auth(x_admin_key)
    ok = await ticket_db.delete_faq(faq_id)
    return {"ok": ok}


@app.get("/api/support/stats/extended")
async def stats_extended_endpoint(
    days: int = Query(14, ge=1, le=365),
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    return await ticket_db.stats_extended(days)


# ──────────────────────────────────────────────────────────────
#  Templates CRUD
# ──────────────────────────────────────────────────────────────
@app.get("/api/support/templates")
async def templates_list_endpoint(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> list:
    _auth(x_admin_key)
    return await ticket_db.list_templates(only_active=False)


@app.post("/api/support/templates")
async def templates_create_endpoint(
    body: TemplateCreate,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    import bleach
    text = bleach.clean(body.text, tags=[], strip=True) if body.text else ""
    tpl_id = await ticket_db.create_template(
        body.slug, body.title, text, body.display_order
    )
    return {"id": tpl_id}


@app.patch("/api/support/templates/{tpl_id}")
async def templates_update_endpoint(
    tpl_id: int,
    body: TemplateUpdate,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    import bleach
    update_data = body.model_dump(exclude_none=True)
    if "text" in update_data and update_data["text"]:
        update_data["text"] = bleach.clean(update_data["text"], tags=[], strip=True)
    ok = await ticket_db.update_template(tpl_id, **update_data)
    return {"ok": ok}
    return {"ok": ok}


@app.delete("/api/support/templates/{tpl_id}")
async def templates_delete_endpoint(
    tpl_id: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    _auth(x_admin_key)
    ok = await ticket_db.delete_template(tpl_id)
    return {"ok": ok}


# ── Telegram webhook endpoint ──────────────────────────────────────────
# Stores dp/bot references set by __main__.py on startup
_webhook_dp = None
_webhook_bot = None


def set_webhook_handler(dp, bot):
    global _webhook_dp, _webhook_bot
    _webhook_dp = dp
    _webhook_bot = bot


@app.post("/telegram/webhook")
async def telegram_webhook(request):
    """Receive Telegram updates via webhook instead of polling."""
    from aiogram.types import Update

    if _webhook_dp is None or _webhook_bot is None:
        log.error("Webhook handler not initialized")
        from starlette.responses import Response
        return Response(status_code=503)

    body = await request.body()
    try:
        update = Update.model_validate_json(body)
        await _webhook_dp.feed_update(bot=_webhook_bot, update=update)
    except Exception as e:
        log.error(f"Webhook update error: {e}")
    from starlette.responses import Response
    return Response(status_code=200)
