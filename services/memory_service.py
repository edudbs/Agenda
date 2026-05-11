import json
import math
import os
import sqlite3
from typing import Dict, List

from google import genai

from config import (
    ENABLE_MEMORY_EMBEDDINGS,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
)


MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "agenda_memory.db")


def get_connection():
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_embedding_client():
    if not ENABLE_MEMORY_EMBEDDINGS:
        return None

    if not GEMINI_API_KEY:
        return None

    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None


def generate_embedding(text: str) -> List[float] | None:
    client = get_embedding_client()
    if not client:
        return None

    try:
        response = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=text,
        )
        return response.embeddings[0].values
    except Exception as e:
        print(f"Erro embedding: {e}")
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def init_memory_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                embedding TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
            """
        )

        columns = [row[1] for row in conn.execute("PRAGMA table_info(memories)")]
        if "embedding" not in columns:
            conn.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")

        conn.commit()


def add_memory(content: str) -> Dict:
    clean_content = content.strip()
    if not clean_content:
        return {"error": "Memória vazia."}

    embedding = generate_embedding(clean_content)

    init_memory_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO memories (content, embedding) VALUES (?, ?)",
            (
                clean_content,
                json.dumps(embedding) if embedding else None,
            ),
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


def semantic_search_memories(query: str, limit: int = 5) -> List[Dict]:
    if not ENABLE_MEMORY_EMBEDDINGS:
        return []

    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []

    init_memory_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content, embedding, created_at, updated_at
            FROM memories
            WHERE active = 1
            """
        ).fetchall()

    scored = []
    for row in rows:
        if not row["embedding"]:
            continue

        try:
            memory_embedding = json.loads(row["embedding"])
            similarity = cosine_similarity(query_embedding, memory_embedding)
            scored.append((similarity, dict(row)))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit] if item[0] > 0.70]


def keyword_search_memories(query: str, limit: int = 5) -> List[Dict]:
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


def search_memories(query: str, limit: int = 5) -> List[Dict]:
    semantic_results = semantic_search_memories(query, limit=limit)
    if semantic_results:
        return semantic_results

    return keyword_search_memories(query, limit=limit)


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
