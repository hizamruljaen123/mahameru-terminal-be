import sqlite3
import json
import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    agent_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    tokens INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            """)
            conn.commit()

    def create_session(self, user_id: str, agent_id: str, session_id: Optional[str] = None) -> str:
        sid = session_id or str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, user_id, agent_id, metadata_json) VALUES (?, ?, ?, ?)",
                (sid, user_id, agent_id, json.dumps({"cumulative_tokens": 0}))
            )
            conn.commit()
        return sid

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row:
                res = dict(row)
                res["metadata"] = json.loads(res["metadata_json"])
                return res
        return None

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        # Simple token count approximation (4 chars = 1 token)
        tokens = len(content) // 4
        
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, tokens, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, tokens, json.dumps(metadata or {}))
            )
            
            # Update session cumulative tokens and updated_at
            session = self.get_session(session_id)
            if session:
                meta = session["metadata"]
                meta["cumulative_tokens"] = meta.get("cumulative_tokens", 0) + tokens
                
                conn.execute(
                    "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP, metadata_json = ? WHERE id = ?",
                    (json.dumps(meta), session_id)
                )
                
                # Check for compaction threshold (e.g. 32k tokens)
                if meta["cumulative_tokens"] > 32000:
                    logger.info(f"Session {session_id} exceeded token threshold. Compaction triggered.")
                    # compaction logic here
            
            conn.commit()

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit)
            )
            messages = []
            for row in rows:
                m = dict(row)
                m["metadata"] = json.loads(m["metadata_json"])
                messages.append(m)
            return list(reversed(messages))

    def update_metadata(self, session_id: str, key: str, value: Any):
        session = self.get_session(session_id)
        if session:
            meta = session["metadata"]
            meta[key] = value
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET metadata_json = ? WHERE id = ?",
                    (json.dumps(meta), session_id)
                )
                conn.commit()

# Global instance
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mahameru.db")
session_manager = SessionManager(DB_PATH)
