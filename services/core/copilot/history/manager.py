import sqlite3
import json
import uuid
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "copilot_history.db")

class HistoryManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    model TEXT,
                    mode TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    tool_calls TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_session(self, session_id: str, title: str, model: str, mode: str) -> str:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, model, mode) VALUES (?, ?, ?, ?)",
                (session_id, title, model, mode)
            )
            conn.commit()
        return session_id

    def update_session_timestamp(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()

    def rename_session(self, session_id: str, new_title: str):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET title = ? WHERE session_id = ?",
                (new_title, session_id)
            )
            conn.commit()

    def delete_session(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def add_message(self, session_id: str, role: str, content: str, tool_calls: Optional[List[Dict]] = None):
        with self._get_connection() as conn:
            # Auto-create session if it doesn't exist (fallback)
            cursor = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
            if not cursor.fetchone():
                self.create_session(session_id, content[:50] + "..." if role == "user" else "New Chat", "default", "analytics")
            
            conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
                (session_id, role, content, json.dumps(tool_calls) if tool_calls else None)
            )
            conn.commit()
        self.update_session_timestamp(session_id)

    def get_sessions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            )
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                m = dict(row)
                if m["tool_calls"]:
                    m["tool_calls"] = json.loads(m["tool_calls"])
                messages.append(m)
            return messages

# Global instance
history_manager = HistoryManager()
