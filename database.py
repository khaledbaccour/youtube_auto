"""SQLite data layer for youtube_auto pipeline."""

import sqlite3
from datetime import datetime, timezone

from config import DB_PATH


def get_connection():
    """Return a Connection with Row factory and WAL mode."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_db():
    """Add columns that may not exist in older databases."""
    conn = get_connection()
    migrations = [
        ("videos", "description", "TEXT"),
        ("videos", "tags", "TEXT"),
        ("videos", "thumbnail_path", "TEXT"),
        ("scores", "virality_score", "REAL"),
        ("scores", "hook_pillar_score", "REAL"),
        ("scores", "click_pillar_score", "REAL"),
        ("scores", "retention_pillar_score", "REAL"),
        ("scores", "engagement_pillar_score", "REAL"),
        ("scores", "algorithm_pillar_score", "REAL"),
        ("scores", "thumbnail_score", "REAL"),
        ("scores", "title_score", "REAL"),
        ("scores", "description_score", "REAL"),
        ("scores", "image_quality_score", "REAL"),
        ("scores", "topic_score", "REAL"),
        ("scores", "workflow_score", "REAL"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            topic TEXT,
            topic_category TEXT,
            script_pattern TEXT,
            hook_style TEXT,
            published_at TEXT,
            video_file_path TEXT,
            youtube_video_id TEXT,
            status TEXT DEFAULT 'draft',
            description TEXT,
            tags TEXT,
            thumbnail_path TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id),
            date TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            watch_time_minutes REAL DEFAULT 0,
            avg_view_duration_seconds REAL DEFAULT 0,
            ctr REAL DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            subs_gained INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            retention_30s REAL DEFAULT 0,
            retention_60s REAL DEFAULT 0,
            retention_end REAL DEFAULT 0,
            traffic_source_search REAL DEFAULT 0,
            traffic_source_suggested REAL DEFAULT 0,
            traffic_source_browse REAL DEFAULT 0,
            UNIQUE(video_id, date)
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id),
            hook_score REAL,
            content_score REAL,
            visual_score REAL,
            retention_score REAL,
            overall_score REAL,
            virality_score REAL,
            hook_pillar_score REAL,
            click_pillar_score REAL,
            retention_pillar_score REAL,
            engagement_pillar_score REAL,
            algorithm_pillar_score REAL,
            thumbnail_score REAL,
            title_score REAL,
            description_score REAL,
            image_quality_score REAL,
            topic_score REAL,
            workflow_score REAL,
            notes TEXT,
            scored_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id),
            variable_tested TEXT,
            variant_value TEXT,
            control_value TEXT,
            result_metric TEXT,
            result_value REAL,
            control_result REAL,
            winner TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insight_text TEXT NOT NULL,
            insight_type TEXT,
            confidence REAL,
            evidence TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            applied_to_claude_md INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS topic_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_category TEXT UNIQUE NOT NULL,
            avg_views REAL DEFAULT 0,
            avg_retention REAL DEFAULT 0,
            avg_ctr REAL DEFAULT 0,
            sample_size INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    _migrate_db()


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------

def insert_video(title, topic, topic_category, script_pattern, hook_style, video_file_path,
                  description=None, tags=None, thumbnail_path=None):
    """Insert a new video record and return its id."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO videos (title, topic, topic_category, script_pattern, hook_style,
           video_file_path, description, tags, thumbnail_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, topic, topic_category, script_pattern, hook_style, video_file_path,
         description, tags, thumbnail_path),
    )
    vid = cur.lastrowid
    conn.commit()
    conn.close()
    return vid


def get_video(video_id):
    """Return a single video as a dict, or None."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_video_youtube_id(video_id, youtube_video_id):
    conn = get_connection()
    conn.execute(
        "UPDATE videos SET youtube_video_id = ? WHERE id = ?",
        (youtube_video_id, video_id),
    )
    conn.commit()
    conn.close()


def update_video_status(video_id, status):
    conn = get_connection()
    conn.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
    conn.commit()
    conn.close()


def get_recent_videos(limit=20):
    """Return the most recent videos as a list of dicts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def insert_analytics(video_id, date, metrics_dict):
    """Upsert analytics for a video on a given date."""
    cols = [
        "views", "watch_time_minutes", "avg_view_duration_seconds", "ctr",
        "likes", "comments", "subs_gained", "impressions",
        "retention_30s", "retention_60s", "retention_end",
        "traffic_source_search", "traffic_source_suggested", "traffic_source_browse",
    ]
    values = [metrics_dict.get(c, 0) for c in cols]

    placeholders = ", ".join(f"{c} = excluded.{c}" for c in cols)
    col_names = ", ".join(cols)
    qs = ", ".join(["?"] * (2 + len(cols)))

    sql = f"""
        INSERT INTO analytics (video_id, date, {col_names})
        VALUES ({qs})
        ON CONFLICT(video_id, date) DO UPDATE SET {placeholders}
    """
    conn = get_connection()
    conn.execute(sql, [video_id, date] + values)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

def insert_score(video_id, scores_dict):
    cols = [
        "hook_score", "content_score", "visual_score", "retention_score",
        "overall_score", "virality_score",
        "hook_pillar_score", "click_pillar_score", "retention_pillar_score",
        "engagement_pillar_score", "algorithm_pillar_score",
        "thumbnail_score", "title_score", "description_score",
        "image_quality_score", "topic_score", "workflow_score",
        "notes",
    ]
    values = [scores_dict.get(c) for c in cols]
    col_names = ", ".join(cols)
    placeholders = ", ".join(["?"] * (1 + len(cols)))

    conn = get_connection()
    conn.execute(
        f"INSERT INTO scores (video_id, {col_names}) VALUES ({placeholders})",
        [video_id] + values,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# A/B Tests
# ---------------------------------------------------------------------------

def insert_ab_test(video_id, variable, variant, control, metric, result, control_result, winner):
    conn = get_connection()
    conn.execute(
        """INSERT INTO ab_tests (video_id, variable_tested, variant_value, control_value,
           result_metric, result_value, control_result, winner)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (video_id, variable, variant, control, metric, result, control_result, winner),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def insert_insight(text, insight_type, confidence, evidence):
    conn = get_connection()
    conn.execute(
        """INSERT INTO insights (insight_text, insight_type, confidence, evidence)
           VALUES (?, ?, ?, ?)""",
        (text, insight_type, confidence, evidence),
    )
    conn.commit()
    conn.close()


def get_unapplied_insights():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM insights WHERE applied_to_claude_md = 0 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_insight_applied(insight_id):
    conn = get_connection()
    conn.execute(
        "UPDATE insights SET applied_to_claude_md = 1 WHERE id = ?", (insight_id,)
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Topic Performance
# ---------------------------------------------------------------------------

def update_topic_performance(category, views, retention, ctr, sample_size):
    """Upsert topic performance stats."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO topic_performance (topic_category, avg_views, avg_retention, avg_ctr, sample_size, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(topic_category) DO UPDATE SET
               avg_views = excluded.avg_views,
               avg_retention = excluded.avg_retention,
               avg_ctr = excluded.avg_ctr,
               sample_size = excluded.sample_size,
               updated_at = excluded.updated_at""",
        (category, views, retention, ctr, sample_size),
    )
    conn.commit()
    conn.close()


def get_top_performing_topics(limit=5):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM topic_performance ORDER BY avg_views DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Aggregated Summary
# ---------------------------------------------------------------------------

def get_performance_summary():
    """Return aggregated stats across all videos."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT a.video_id) AS videos_with_data,
            COALESCE(SUM(a.views), 0) AS total_views,
            COALESCE(AVG(a.views), 0) AS avg_views,
            COALESCE(AVG(a.avg_view_duration_seconds), 0) AS avg_duration,
            COALESCE(AVG(a.ctr), 0) AS avg_ctr,
            COALESCE(AVG(a.retention_30s), 0) AS avg_retention_30s,
            COALESCE(AVG(a.retention_60s), 0) AS avg_retention_60s,
            COALESCE(AVG(a.retention_end), 0) AS avg_retention_end
        FROM analytics a
        JOIN (
            SELECT video_id, MAX(date) AS max_date
            FROM analytics
            GROUP BY video_id
        ) latest ON a.video_id = latest.video_id AND a.date = latest.max_date
    """).fetchone()
    conn.close()
    return dict(row) if row else {}
