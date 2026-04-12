import json
import uuid
import os
from datetime import datetime
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func
from typing import Dict, Optional, Set
from pydantic import BaseModel

from app.db.session import get_db
from app.core.security import get_current_user
from app.core.notifications import send_push_to_user

# 🚨 Import our new centralized Zoho Email Engine
from app.core.email import _send_api_email, send_admin_new_chat_alert

from app.domains.users.models import User
from app.domains.chat.models import ChatMessage, SupportTicket

router = APIRouter(prefix="/chat", tags=["Live Chat & Support"])

# ─────────────────────────────────────────────
# Connection Manager
# ─────────────────────────────────────────────

class ConnectionManager:
    """
    Manages WebSocket connections for both users and admins.
    Handles typing indicators, read receipts, and online presence.
    """

    def __init__(self):
        self.user_connections: Dict[str, WebSocket] = {}
        self.admin_connections: Dict[str, WebSocket] = {}
        self._notified_sessions: Set[str] = set()

    # ── Connect / Disconnect ──────────────────────────────────

    async def connect_user(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.user_connections[user_id] = websocket
        print(f"[WS] ✅ User {user_id} connected. Online: {len(self.user_connections)}")

    async def connect_admin(self, websocket: WebSocket, admin_id: str):
        await websocket.accept()
        self.admin_connections[admin_id] = websocket
        print(f"[WS Admin] ✅ Admin {admin_id} connected. Online: {len(self.admin_connections)}")

    def disconnect_user(self, user_id: str):
        self.user_connections.pop(user_id, None)
        self._notified_sessions.discard(user_id)

    def disconnect_admin(self, admin_id: str):
        self.admin_connections.pop(admin_id, None)

    # ── Send Helpers ──────────────────────────────────────────

    async def send_to_user(self, payload: dict, user_id: str):
        ws = self.user_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(payload)
            except Exception as e:
                print(f"[WS] Failed to send to user {user_id}: {e}")
                self.disconnect_user(user_id)

    async def broadcast_to_admins(self, payload: dict):
        dead = []
        for admin_id, ws in self.admin_connections.items():
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(admin_id)
        for admin_id in dead:
            self.disconnect_admin(admin_id)

    # ── Presence & Dedup ─────────────────────────────────────

    def is_user_online(self, user_id: str) -> bool:
        return user_id in self.user_connections

    def should_notify_admin(self, user_id: str) -> bool:
        """Returns True only the first time a user sends a message per session."""
        if user_id not in self._notified_sessions:
            self._notified_sessions.add(user_id)
            return True
        return False

    @property
    def online_user_ids(self) -> list:
        return list(self.user_connections.keys())


manager = ConnectionManager()


# ─────────────────────────────────────────────
# 1. User WebSocket  /ws/chat/{user_id}
# ─────────────────────────────────────────────

@router.websocket("/ws/chat/{user_id}")
async def websocket_user_endpoint(websocket: WebSocket, user_id: str):
    print(f"\n[WS] 🔵 User {user_id} connecting...")
    await manager.connect_user(websocket, user_id)

    await manager.broadcast_to_admins({
        "type": "user_online",
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat(),
    })

    try:
        while True:
            raw = await websocket.receive_text()

            if raw == "ping":
                await websocket.send_text("pong")
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "message", "content": raw}

            msg_type = payload.get("type", "message")

            if msg_type == "typing":
                await manager.broadcast_to_admins({
                    "type": "typing",
                    "user_id": user_id,
                    "is_typing": payload.get("is_typing", True),
                })
                continue

            if msg_type == "message":
                content = payload.get("content", "").strip()
                if not content:
                    continue

                print(f"[WS] 📩 {user_id}: {content[:80]}")

                async for db in get_db():
                    try:
                        user_row = (await db.execute(
                            select(User).where(User.id == uuid.UUID(user_id))
                        )).scalar_one_or_none()

                        new_msg = ChatMessage(
                            user_id=uuid.UUID(user_id),
                            sender_type="user",
                            content=content,
                        )
                        db.add(new_msg)
                        await db.commit()
                        await db.refresh(new_msg)

                        msg_data = {
                            "type": "message",
                            "id": str(new_msg.id),
                            "sender_type": "user",
                            "content": content,
                            "created_at": new_msg.created_at.isoformat(),
                            "status": "delivered",
                        }

                        await manager.send_to_user(msg_data, user_id)

                        await manager.broadcast_to_admins({
                            **msg_data,
                            "user_id": user_id,
                            "user_email": user_row.email if user_row else "unknown",
                            "user_name": (user_row.full_name or user_row.email) if user_row else "Unknown",
                        })

                        # 🚨 ZOHO TRIGGER: Notify admin if it's the first message in this session
                        if user_row and manager.should_notify_admin(user_id):
                            try:
                                send_admin_new_chat_alert(user_row.email, content)
                            except Exception as e:
                                print(f"[WS] Zoho Email notify failed: {e}")

                    except Exception as e:
                        print(f"[WS DB Error] {e}")
                        await manager.send_to_user(
                            {"type": "error", "message": "Message could not be saved. Please try again."},
                            user_id,
                        )
                    finally:
                        break

    except WebSocketDisconnect:
        print(f"[WS] 🔴 User {user_id} disconnected.")
        manager.disconnect_user(user_id)
        await manager.broadcast_to_admins({
            "type": "user_offline",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        print(f"[WS] ❌ Unexpected error for {user_id}: {e}")
        manager.disconnect_user(user_id)


# ─────────────────────────────────────────────
# 2. Admin WebSocket  /ws/admin/{admin_id}
# ─────────────────────────────────────────────

@router.websocket("/ws/admin/{admin_id}")
async def websocket_admin_endpoint(websocket: WebSocket, admin_id: str):
    print(f"\n[WS Admin] 🔵 Admin {admin_id} connecting...")
    await manager.connect_admin(websocket, admin_id)

    try:
        while True:
            raw = await websocket.receive_text()

            if raw == "ping":
                await websocket.send_text("pong")
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = payload.get("type")

            if msg_type == "message":
                target_user_id = payload.get("user_id", "").strip()
                content = payload.get("content", "").strip()
                if not target_user_id or not content:
                    continue

                async for db in get_db():
                    try:
                        new_msg = ChatMessage(
                            user_id=uuid.UUID(target_user_id),
                            sender_type="admin",
                            content=content,
                        )
                        db.add(new_msg)
                        await db.commit()
                        await db.refresh(new_msg)

                        msg_data = {
                            "type": "message",
                            "id": str(new_msg.id),
                            "sender_type": "admin",
                            "content": content,
                            "created_at": new_msg.created_at.isoformat(),
                        }

                        await manager.send_to_user(msg_data, target_user_id)

                        await websocket.send_json({
                            **msg_data,
                            "user_id": target_user_id,
                            "delivered_live": manager.is_user_online(target_user_id),
                        })

                        if not manager.is_user_online(target_user_id):
                            user_row = (await db.execute(
                                select(User).where(User.id == uuid.UUID(target_user_id))
                            )).scalar_one_or_none()
                            if user_row:
                                try:
                                    await send_push_to_user(user_row, "Support Reply", content, db)
                                except Exception as e:
                                    print(f"[WS Admin] Push notify failed: {e}")

                    except Exception as e:
                        print(f"[WS Admin DB Error] {e}")
                    finally:
                        break

            elif msg_type == "typing":
                target_user_id = payload.get("user_id", "")
                if target_user_id:
                    await manager.send_to_user({
                        "type": "typing",
                        "is_typing": payload.get("is_typing", True),
                    }, target_user_id)

            elif msg_type == "mark_read":
                target_user_id = payload.get("user_id", "")
                if not target_user_id:
                    continue
                async for db in get_db():
                    try:
                        await db.execute(
                            update(ChatMessage)
                            .where(
                                ChatMessage.user_id == uuid.UUID(target_user_id),
                                ChatMessage.sender_type == "user",
                            )
                            .values(is_read=True)
                        )
                        await db.commit()
                        await manager.send_to_user(
                            {"type": "read_receipt", "all_read": True},
                            target_user_id,
                        )
                    except Exception as e:
                        print(f"[WS Admin mark-read error] {e}")
                    finally:
                        break

    except WebSocketDisconnect:
        print(f"[WS Admin] 🔴 Admin {admin_id} disconnected.")
        manager.disconnect_admin(admin_id)
    except Exception as e:
        print(f"[WS Admin] ❌ Error: {e}")
        manager.disconnect_admin(admin_id)


# ─────────────────────────────────────────────
# 3. Chat History (Paginated)
# ─────────────────────────────────────────────

@router.get("/history")
async def get_chat_history(
    user_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_id = current_user.id
    if user_id and current_user.role in ["admin", "superadmin"]:
        target_id = uuid.UUID(user_id)

    offset = (page - 1) * limit
    messages = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == target_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )).scalars().all()

    total = await db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.user_id == target_id)
    )

    return {
        "messages": [
            {
                "id": str(m.id),
                "sender_type": m.sender_type,
                "content": m.content,
                "is_read": m.is_read,
                "created_at": m.created_at.isoformat(),
                "status": "read" if m.is_read else "delivered",
            }
            for m in messages
        ],
        "total": total,
        "page": page,
        "has_more": (offset + limit) < total,
    }


# ─────────────────────────────────────────────
# 4. Admin REST Reply (push fallback)
# ─────────────────────────────────────────────

class AdminReplyRequest(BaseModel):
    user_id: str
    content: str

@router.post("/admin-reply")
async def admin_reply(
    payload: AdminReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_msg = ChatMessage(
        user_id=uuid.UUID(payload.user_id),
        sender_type="admin",
        content=payload.content,
    )
    db.add(new_msg)
    await db.commit()
    await db.refresh(new_msg)

    msg_data = {
        "type": "message",
        "id": str(new_msg.id),
        "sender_type": "admin",
        "content": payload.content,
        "created_at": new_msg.created_at.isoformat(),
    }

    await manager.send_to_user(msg_data, payload.user_id)

    if not manager.is_user_online(payload.user_id):
        user_row = (await db.execute(
            select(User).where(User.id == uuid.UUID(payload.user_id))
        )).scalar_one_or_none()
        if user_row:
            try:
                await send_push_to_user(user_row, "Support Reply", payload.content, db)
            except Exception:
                pass

    return {
        "status": "success",
        "id": str(new_msg.id),
        "delivered_live": manager.is_user_online(payload.user_id),
    }


# ─────────────────────────────────────────────
# 5. Admin Dashboard — Chat List
# ─────────────────────────────────────────────

@router.get("/admin/all-chats")
async def admin_get_all_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    rows = (await db.execute(
        select(
            ChatMessage.user_id,
            func.count(ChatMessage.id)
            .filter(ChatMessage.sender_type == "user", ChatMessage.is_read == False)
            .label("unread_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
        )
        .group_by(ChatMessage.user_id)
        .order_by(desc("last_message_at"))
    )).all()

    user_ids = [r.user_id for r in rows]
    users = {
        u.id: u
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }

    result = []
    for row in rows:
        u = users.get(row.user_id)
        if not u:
            continue
        last = await db.scalar(
            select(ChatMessage)
            .where(ChatMessage.user_id == row.user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        result.append({
            "user_id": str(row.user_id),
            "email": u.email,
            "full_name": u.full_name or "Anonymous",
            "unread_count": row.unread_count,
            "last_message": last.content[:80] if last else "",
            "last_message_sender": last.sender_type if last else None,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "is_online": manager.is_user_online(str(row.user_id)),
        })
    return result


# ─────────────────────────────────────────────
# 6. Mark All Read (REST)
# ─────────────────────────────────────────────

@router.post("/admin/mark-read/{user_id}")
async def admin_mark_read(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.user_id == uuid.UUID(user_id),
            ChatMessage.sender_type == "user",
        )
        .values(is_read=True)
    )
    await db.commit()

    await manager.send_to_user({"type": "read_receipt", "all_read": True}, user_id)
    return {"status": "ok"}


# ─────────────────────────────────────────────
# 7. Online Presence
# ─────────────────────────────────────────────

@router.get("/admin/online-users")
async def get_online_users(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"online_user_ids": manager.online_user_ids}


# ─────────────────────────────────────────────
# 8. Support Ticketing, Broadcast & Zoho Email
# ─────────────────────────────────────────────

# --- Schemas ---
class TicketCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    subject: str
    message: str
    attachment_url: Optional[str] = None

class BroadcastRequest(BaseModel):
    target_user_id: str  # "all", "custom", or a specific user's UUID
    custom_email: Optional[str] = None
    subject: str
    message: str

# --- Routes ---
@router.post("/support/ticket")
async def create_support_ticket(
    payload: TicketCreate, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Save to Database
    ticket = SupportTicket(
        user_id=current_user.id,
        provided_name=payload.name or current_user.full_name,
        provided_email=payload.email or current_user.email,
        subject=payload.subject,
        message=payload.message,
        attachment_url=payload.attachment_url,
        status="open"
    )
    db.add(ticket)
    await db.commit()
    
    # 2. 🚨 Alert the Admin via Zoho (Runs securely in the background)
    admin_body = f"<strong>New Message From:</strong> {payload.name} ({payload.email})<br><br><strong>Subject:</strong> {payload.subject}<br><br><strong>Message:</strong><br>{payload.message}"
    admin_alert_email = os.getenv("ADMIN_ALERT_EMAIL", "admin@dunexmarkets.com")
    
    background_tasks.add_task(
        _send_zoho_email, 
        admin_alert_email, 
        f"New Support Message: {payload.subject}", 
        admin_body, 
        "Support Alert"
    )
    
    # 3. 🚨 Warm, Simple Auto-Reply to the User via Zoho
    user_body = f"""
    <h3 style="color: #ffffff; font-size: 20px; margin-bottom: 15px;">We received your message!</h3>
    Hello {payload.name},<br><br>
    Thank you for reaching out to us. We have successfully received your message regarding <strong>"{payload.subject}"</strong>.<br><br>
    Our support team is looking into it right now, and we will reply to you here via email very soon. You do not need to do anything else at this time.<br><br>
    Warm regards,<br>
    <strong>The Dunex Support Team</strong>
    """
    
    background_tasks.add_task(
        _send_zoho_email, 
        payload.email or current_user.email, 
        "We received your message - Dunex Support", 
        user_body, 
        "Support Auto-Reply"
    )
    
    return {"status": "success"}

@router.get("/admin/support/users")
async def admin_get_users_for_dropdown(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in ["admin", "superadmin"]: raise HTTPException(status_code=403)
    users = (await db.execute(select(User.id, User.email, User.full_name))).all()
    return [{"id": str(u.id), "email": u.email, "name": u.full_name} for u in users]

@router.get("/admin/support/tickets")
async def admin_get_tickets(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in ["admin", "superadmin"]: raise HTTPException(status_code=403)
    result = await db.execute(select(SupportTicket).order_by(desc(SupportTicket.created_at)))
    return [{"id": str(t.id), "user_email": t.provided_email, "name": t.provided_name, "subject": t.subject, "message": t.message, "status": t.status, "attachment": t.attachment_url, "created_at": t.created_at.isoformat()} for t in result.scalars().all()]


@router.post("/admin/support/broadcast")
async def admin_broadcast_message(
    payload: BroadcastRequest, background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if current_user.role not in ["admin", "superadmin"]: raise HTTPException(status_code=403)

    formatted_message = payload.message.replace('\n', '<br>')

    if payload.target_user_id == "all":
        users = (await db.execute(select(User.email).where(User.is_active == True))).scalars().all()
        for email in set(users):
            # 🚨 Fixed: _send_api_email
            background_tasks.add_task(_send_api_email, email, payload.subject, formatted_message, "Admin Broadcast") 
        return {"status": "success", "recipients": len(set(users))}
        
    elif payload.target_user_id == "custom":
        if not payload.custom_email:
            raise HTTPException(status_code=400, detail="Custom email is required")
        # 🚨 Fixed: _send_api_email
        background_tasks.add_task(_send_api_email, payload.custom_email, payload.subject, formatted_message, "Admin Broadcast") 
        return {"status": "success", "recipients": 1}
        
    else:
        try:
            user_uuid = uuid.UUID(payload.target_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid target ID.")
            
        user = (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
        if user:
            # 🚨 Fixed: _send_api_email (This was line 626!)
            background_tasks.add_task(_send_api_email, user.email, payload.subject, formatted_message, "Admin Broadcast") 
            return {"status": "success", "recipients": 1}
            
        raise HTTPException(status_code=404, detail="User not found")
