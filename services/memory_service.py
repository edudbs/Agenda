import os
import sqlite3
from typing import Dict, List


MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "agenda_memory.db")


def get_connection():
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
            """
        )
        conn.commit()


def add_memory(content: str) -> Dict:
    clean_content = content.strip()
    if not clean_content:
        return {"error": "Memória vazia."}

    init_memory_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO memories (content) VALUES (?)",
            (clean_content,),
        )
        conn.commit()
        return {"created": True, "memory_id": cursor.lastrowid, "content": clean_content}


def list_memories(limit: int = 20) -> List[Dict]:
    init_memory_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content, created_at, updated_at
            FROM memories
            WHERE active = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def search_memories(query: str, limit: int = 5) -> List[Dict]:
    init_memory_db()
    words = [word.strip().lower() for word in query.split() if len(word.strip()) >= 4]

    if not words:
        return list_memories(limit=limit)

    clauses = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
    params = [f"%{word}%" for word in words]
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, content, created_at, updated_at
            FROM memories
            WHERE active = 1 AND ({clauses})
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


def extract_explicit_memory(message: str) -> str | None:
    text = message.strip()
    lowered = text.lower()

    prefixes = [
        "lembre que ",
        "lembra que ",
        "memorize que ",
        "guarde que ",
        "salve que ",
    ]

    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()

    return None


def build_memory_context(query: str) -> str:
    memories = search_memories(query)
    if not memories:
        return ""

    lines = ["Memórias relevantes do usuário:"]
    for memory in memories:
        lines.append(f"- {memory['content']}")

    return "\n".join(lines)
