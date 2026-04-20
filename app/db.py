from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "opencompost.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mesh_id TEXT UNIQUE NOT NULL,
            name TEXT,
            node_type TEXT NOT NULL DEFAULT 'CLI',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL,
            temperature_external_c REAL,
            temperature_internal_c REAL,
            battery_v REAL,
            battery_pct REAL,
            measured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('poll_interval_seconds', '60')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('repeater_login_node', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('repeater_password', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('gauge_temp_min', '-10')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('gauge_temp_max', '120')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_host', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_port', '1883')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_topic', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_username', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_password', '')
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('mqtt_enabled', '0')
        """
    )
    conn.commit()
    conn.close()
