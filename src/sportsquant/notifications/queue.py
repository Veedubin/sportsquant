"""Alert queue using SQLite for persistence and rate limiting."""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from sportsquant.notifications.config import NotificationConfig
from sportsquant.notifications.models import Alert, AlertType


class AlertQueue:
    """SQLite-based alert queue with rate limiting."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize alert queue."""
        self.config = config or NotificationConfig.from_env()
        self._lock = Lock()
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure database and tables exist."""
        db_path = Path(self.config.queue_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.config.queue_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data TEXT NOT NULL,
                sent INTEGER DEFAULT 0,
                sent_at TEXT,
                send_attempts INTEGER DEFAULT 0,
                last_error TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                window_start INTEGER PRIMARY KEY,
                alert_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(self.config.queue_db_path)

    def enqueue(self, alert: Alert) -> bool:
        """Add alert to queue if within rate limits."""
        with self._lock:
            # Check rate limits
            if not self._check_rate_limit():
                return False

            # Store alert
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO alerts (id, alert_type, created_at, data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        alert.id,
                        alert.alert_type.value,
                        alert.created_at.isoformat(),
                        json.dumps(alert.to_dict()),
                    ),
                )
                conn.commit()
                return True
            except Exception as e:
                print(f"Queue enqueue error: {e}")
                return False
            finally:
                conn.close()

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        minute_key = int(now // 60) * 60
        hour_key = int(now // 3600) * 3600

        conn = self._get_connection()
        cursor = conn.cursor()

        # Check minute limit
        cursor.execute(
            "SELECT alert_count FROM rate_limits WHERE window_start = ?",
            (minute_key,),
        )
        row = cursor.fetchone()
        minute_count = row[0] if row else 0

        if minute_count >= self.config.max_alerts_per_minute:
            conn.close()
            return False

        # Check hour limit
        cursor.execute(
            "SELECT alert_count FROM rate_limits WHERE window_start = ?",
            (hour_key,),
        )
        row = cursor.fetchone()
        hour_count = row[0] if row else 0

        if hour_count >= self.config.max_alerts_per_hour:
            conn.close()
            return False

        # Increment counters
        cursor.execute(
            """
            INSERT INTO rate_limits (window_start, alert_count)
            VALUES (?, 1)
            ON CONFLICT(window_start) DO UPDATE SET alert_count = alert_count + 1
            """,
            (minute_key,),
        )
        if minute_key != hour_key:
            cursor.execute(
                """
                INSERT INTO rate_limits (window_start, alert_count)
                VALUES (?, 1)
                ON CONFLICT(window_start) DO UPDATE SET alert_count = alert_count + 1
                """,
                (hour_key,),
            )

        conn.commit()
        conn.close()
        return True

    def dequeue(self, alert_type: Optional[AlertType] = None, limit: int = 10) -> list[Alert]:
        """Get unsent alerts from queue."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT data FROM alerts WHERE sent = 0"
        params: list = []

        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type.value)

        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        alerts = []
        for row in rows:
            data = json.loads(row[0])
            alert = self._dict_to_alert(data)
            if alert:
                alerts.append(alert)

        return alerts

    def mark_sent(self, alert_id: str) -> None:
        """Mark alert as sent."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE alerts SET sent = 1, sent_at = ? WHERE id = ?
            """,
            (datetime.now().isoformat(), alert_id),
        )
        conn.commit()
        conn.close()

    def mark_failed(self, alert_id: str, error: str) -> None:
        """Mark alert send as failed."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE alerts
            SET send_attempts = send_attempts + 1, last_error = ?
            WHERE id = ?
            """,
            (error, alert_id),
        )
        conn.commit()
        conn.close()

    def get_stats(self) -> dict:
        """Get queue statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM alerts WHERE sent = 0")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM alerts WHERE sent = 1")
        sent = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM alerts WHERE send_attempts >= 3")
        failed = cursor.fetchone()[0]

        conn.close()

        return {
            "pending": pending,
            "sent": sent,
            "failed": failed,
        }

    @staticmethod
    def _dict_to_alert(data: dict) -> Optional[Alert]:
        """Convert dictionary back to Alert object."""
        from sportsquant.notifications.models import (
            EVAlert,
            LineMovementAlert,
            InjuryAlert,
            SummaryAlert,
        )

        alert_type = data.get("alert_type")

        if alert_type == AlertType.EV.value:
            return EVAlert(
                id=data["id"],
                player_name=data.get("player_name", ""),
                stat_type=data.get("stat_type", ""),
                line=data.get("line", 0.0),
                edge=data.get("edge", 0.0),
                confidence=data.get("confidence", 0.0),
                recommended_side=data.get("recommended_side", ""),
                market_prob=data.get("market_prob", 0.0),
                fair_prob=data.get("fair_prob", 0.0),
                payout_multiplier=data.get("payout_multiplier", 1.0),
                stake=data.get("stake"),
                message=data.get("message", ""),
                site=data.get("site", ""),
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        elif alert_type == AlertType.LINE_MOVEMENT.value:
            return LineMovementAlert(
                id=data["id"],
                player_name=data.get("player_name", ""),
                stat_type=data.get("stat_type", ""),
                previous_line=data.get("previous_line", 0.0),
                new_line=data.get("new_line", 0.0),
                market_source=data.get("market_source", ""),
                message=data.get("message", ""),
                site=data.get("site", ""),
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        elif alert_type == AlertType.INJURY.value:
            return InjuryAlert(
                id=data["id"],
                player_name=data.get("player_name", ""),
                team=data.get("team", ""),
                player_status=data.get("player_status", ""),
                affected_props=data.get("affected_props", []),
                impact=data.get("impact", ""),
                message=data.get("message", ""),
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        elif alert_type == AlertType.SUMMARY.value:
            return SummaryAlert(
                id=data["id"],
                total_opportunities=data.get("total_opportunities", 0),
                top_plays=data.get("top_plays", []),
                ev_breakdown=data.get("ev_breakdown", {}),
                sport=data.get("sport", "NBA"),
                message=data.get("message", ""),
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        else:
            return None
