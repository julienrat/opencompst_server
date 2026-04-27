from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "opencompost.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # Optimisations pour carte SD (Raspberry Pi)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -2000")  # 2MB de cache en RAM
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
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migration simple pour ajouter la colonne sort_order si elle n'existe pas
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        # La colonne existe déjà
        pass

    try:
        cursor.execute("ALTER TABLE measurements ADD COLUMN signal_rssi INTEGER")
    except sqlite3.OperationalError:
        pass

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL,
            temperature_external_c REAL,
            temperature_internal_c REAL,
            battery_v REAL,
            battery_pct REAL,
            signal_rssi INTEGER,
            measured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        )
        """
    )
    # Index pour accélérer les requêtes latest_measurements et l'historique
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_measurements_node_date ON measurements (node_id, measured_at DESC)"
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
