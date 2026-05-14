import aiosqlite
import json
import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class HistoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        """Initialize the database schema asynchronously."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            
            # Unified Sessions Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    agent_id TEXT,
                    title TEXT,
                    model TEXT,
                    mode TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT
                )
            """)
            
            # Unified Messages Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    tool_calls_json TEXT,
                    tokens INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)
            await db.commit()
            logger.info(f"[HistoryService] Database initialized at {self.db_path}")

    async def create_session(self, user_id: str, agent_id: str, title: str, model: str, mode: str, session_id: Optional[str] = None) -> str:
        sid = session_id or str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, user_id, agent_id, title, model, mode, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, user_id, agent_id, title, model, mode, json.dumps({"cumulative_tokens": 0}))
            )
            await db.commit()
        return sid

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    res = dict(row)
                    res["session_id"] = res["id"]
                    res["metadata"] = json.loads(res["metadata_json"]) if res.get("metadata_json") else {}
                    return res
        return None

    async def get_all_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM sessions ORDER BY updated_at DESC"
            params = ()
            if user_id:
                query = "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC"
                params = (user_id,)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                sessions = []
                for row in rows:
                    s = dict(row)
                    s["session_id"] = s["id"]
                    sessions.append(s)
                return sessions

    async def delete_session(self, session_id: str):
        try:
            logger.info(f"[HistoryService] Deleting session {session_id}")
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                await db.commit()
            logger.info(f"[HistoryService] Successfully deleted session {session_id}")
        except Exception as e:
            logger.error(f"[HistoryService] Error deleting session {session_id}: {e}")
            raise

    async def rename_session(self, session_id: str, new_title: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_title, session_id)
            )
            await db.commit()

    async def add_message(self, session_id: str, role: str, content: str, tool_calls: Optional[List[Dict]] = None, metadata: Optional[Dict[str, Any]] = None, model: Optional[str] = None):
        # Approximation: 4 chars = 1 token
        tokens = len(content) // 4
        
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Insert message
            await db.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls_json, tokens, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, tokens, json.dumps(metadata or {}))
            )
            
            # 2. Update session metadata and timestamp
            session = await self.get_session(session_id)
            if session:
                meta_json = session.get("metadata_json")
                meta = json.loads(meta_json) if meta_json else {}
                meta["cumulative_tokens"] = meta.get("cumulative_tokens", 0) + tokens
                
                update_sql = "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP, metadata_json = ? WHERE id = ?"
                params = [json.dumps(meta), session_id]
                
                # Update model if provided and not set
                if model and not session.get("model"):
                    update_sql = "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP, metadata_json = ?, model = ? WHERE id = ?"
                    params = [json.dumps(meta), model, session_id]
                
                await db.execute(update_sql, tuple(params))
            else:
                # Auto-create session if missing (fallback)
                await db.execute(
                    "INSERT INTO sessions (id, user_id, title, mode, model, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, "user", content[:50] + "..." if role == "user" else "New Chat", "analytics", model, json.dumps({"cumulative_tokens": tokens}))
                )
            
            await db.commit()

    async def get_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT *, created_at as timestamp FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
                (session_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                messages = []
                for row in rows:
                    msg = dict(row)
                    if msg.get("tool_calls_json"):
                        msg["tool_calls"] = json.loads(msg["tool_calls_json"])
                    if msg.get("metadata_json"):
                        msg["metadata"] = json.loads(msg["metadata_json"])
                    messages.append(msg)
                return messages

# Global Instance
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "mahameru_unified.db")
history_service = HistoryService(DB_PATH)
