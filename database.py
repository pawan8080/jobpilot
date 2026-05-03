"""SQLite database for JobPilot - tracks the job application pipeline."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = "jobpilot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    source_url TEXT,
    description TEXT NOT NULL,
    fit_score INTEGER,
    fit_reasoning TEXT,
    matching_skills TEXT,        -- JSON list
    missing_skills TEXT,         -- JSON list
    cover_letter TEXT,
    resume_bullets TEXT,         -- JSON list
    screening_answers TEXT,      -- JSON dict
    outreach_message TEXT,
    status TEXT NOT NULL DEFAULT 'new',  -- new, applied, interviewing, rejected, offer, ghosted
    notes TEXT,
    added_date TEXT NOT NULL,
    applied_date TEXT,
    last_status_update TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_added_date ON jobs(added_date);
CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score);
"""

VALID_STATUSES = ["new", "applied", "interviewing", "rejected", "offer", "ghosted"]


@contextmanager
def get_conn():
    """Context manager for SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database schema."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def insert_job(data: dict) -> int:
    """Insert a new job. Returns the new job's ID."""
    data["added_date"] = data.get("added_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["status"] = data.get("status", "new")
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    sql = f"INSERT INTO jobs ({cols}) VALUES ({placeholders})"
    with get_conn() as conn:
        cursor = conn.execute(sql, data)
        return cursor.lastrowid


def update_job(job_id: int, **fields) -> None:
    """Update specific fields on a job."""
    if not fields:
        return
    fields["last_status_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = job_id
    sql = f"UPDATE jobs SET {set_clause} WHERE id = :id"
    with get_conn() as conn:
        conn.execute(sql, fields)


def update_status(job_id: int, new_status: str) -> None:
    """Change a job's status. Sets applied_date if moving to 'applied'."""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    fields = {"status": new_status}
    if new_status == "applied":
        fields["applied_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_job(job_id, **fields)


def delete_job(job_id: int) -> None:
    """Delete a job permanently."""
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def get_job(job_id: int) -> dict | None:
    """Fetch a single job by ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(status: str | None = None, order_by: str = "added_date DESC") -> list[dict]:
    """List jobs, optionally filtered by status."""
    sql = "SELECT * FROM jobs"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += f" ORDER BY {order_by}"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_metrics() -> dict:
    """Compute dashboard metrics."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

        by_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
            ).fetchall()
        }

        applied_today = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE applied_date LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]

        added_today = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE added_date LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]

        avg_fit_applied_row = conn.execute(
            "SELECT AVG(fit_score) FROM jobs WHERE status != 'new' AND fit_score IS NOT NULL"
        ).fetchone()
        avg_fit_applied = avg_fit_applied_row[0] if avg_fit_applied_row[0] else 0

        applied = by_status.get("applied", 0) + by_status.get("interviewing", 0) \
                  + by_status.get("rejected", 0) + by_status.get("offer", 0) \
                  + by_status.get("ghosted", 0)
        responses = by_status.get("interviewing", 0) + by_status.get("offer", 0) \
                    + by_status.get("rejected", 0)
        response_rate = (responses / applied * 100) if applied > 0 else 0

    return {
        "total_jobs": total,
        "by_status": by_status,
        "applied_today": applied_today,
        "added_today": added_today,
        "avg_fit_score_applied": round(avg_fit_applied, 1) if avg_fit_applied else 0,
        "response_rate": round(response_rate, 1),
    }
