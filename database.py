"""
Module: database.py
Description: SQLite persistent storage layer for SBMC Lead Automation Engine.
Stores and retrieves qualified leads, preserving state across server restarts.
Adheres to AGENTS.md: Infrastructure Layer separation, strictly typed contracts.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, Generator, List, Optional

DB_FILE: str = "leads.db"


@contextmanager
def get_db_connection(db_path: str = DB_FILE) -> Generator[sqlite3.Connection, None, None]:
    """Context manager ensuring thread-safe database connections with dict row factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = DB_FILE) -> None:
    """Initializes the SQLite schema if it does not already exist."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                company TEXT NOT NULL,
                budget REAL NOT NULL,
                industry TEXT NOT NULL,
                source TEXT NOT NULL,
                tier TEXT NOT NULL,
                score INTEGER NOT NULL,
                qualification_notes TEXT,
                email_draft TEXT,
                alert_dispatched INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def save_or_update_lead(lead_data: Dict[str, Any], db_path: str = DB_FILE) -> None:
    """Inserts or updates a lead record in the SQLite database."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        raw_ts = lead_data.get("processed_at") or lead_data.get("created_at") or datetime.now(timezone.utc)
        created_at_str = raw_ts.isoformat() if isinstance(raw_ts, datetime) else str(raw_ts)

        cursor.execute(
            """
            INSERT INTO leads (
                lead_id, name, email, company, budget, industry, source,
                tier, score, qualification_notes, email_draft, alert_dispatched, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
                name=excluded.name,
                email=excluded.email,
                company=excluded.company,
                budget=excluded.budget,
                industry=excluded.industry,
                source=excluded.source,
                tier=excluded.tier,
                score=excluded.score,
                qualification_notes=excluded.qualification_notes,
                email_draft=excluded.email_draft,
                alert_dispatched=excluded.alert_dispatched;
            """,
            (
                lead_data["lead_id"],
                lead_data["name"],
                lead_data["email"],
                lead_data["company"],
                float(lead_data["budget"]),
                lead_data.get("industry", "General"),
                lead_data.get("source", "Direct"),
                lead_data.get("tier", "STANDARD"),
                int(lead_data.get("score", 0)),
                lead_data.get("qualification_notes", ""),
                lead_data.get("email_draft", ""),
                1 if lead_data.get("alert_dispatched") else 0,
                created_at_str,
            ),
        )
        conn.commit()


def get_all_stored_leads(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieves all stored leads ordered by created_at descending."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads ORDER BY created_at DESC;")
        rows = cursor.fetchall()
        return [
            {
                "lead_id": row["lead_id"],
                "name": row["name"],
                "email": row["email"],
                "company": row["company"],
                "budget": float(row["budget"]),
                "industry": row["industry"],
                "source": row["source"],
                "tier": row["tier"],
                "score": int(row["score"]),
                "qualification_notes": row["qualification_notes"],
                "email_draft": row["email_draft"],
                "alert_dispatched": bool(row["alert_dispatched"]),
                "processed_at": row["created_at"],
            }
            for row in rows
        ]


def seed_baseline_leads(initial_items: List[Dict[str, Any]], db_path: str = DB_FILE) -> None:
    """Seeds default sample leads if database is currently empty."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM leads;")
        count = cursor.fetchone()["count"]
        if count == 0:
            for item in initial_items:
                save_or_update_lead(item, db_path=db_path)
