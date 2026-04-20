from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import get_connection


def list_nodes(enabled_only: bool = False) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if enabled_only:
        cursor.execute("SELECT * FROM nodes WHERE enabled = 1 ORDER BY id ASC")
    else:
        cursor.execute("SELECT * FROM nodes ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def upsert_node(mesh_id: str, name: str | None = None, node_type: str = "CLI") -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO nodes(mesh_id, name, node_type, enabled)
        VALUES(?, ?, ?, 1)
        ON CONFLICT(mesh_id) DO UPDATE SET
            name = COALESCE(excluded.name, nodes.name),
            node_type = excluded.node_type
        """,
        (mesh_id, name, node_type),
    )
    conn.commit()
    cursor.execute("SELECT * FROM nodes WHERE mesh_id = ?", (mesh_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return row


def update_node(node_id: int, name: str | None, enabled: bool) -> dict[str, Any] | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE nodes SET name = ?, enabled = ? WHERE id = ?",
        (name, 1 if enabled else 0, node_id),
    )
    conn.commit()
    cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_node(node_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM measurements WHERE node_id = ?", (node_id,))
    cursor.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def insert_measurement(
    node_id: int,
    temperature_external_c: float | None,
    temperature_internal_c: float | None,
    battery_v: float | None,
    battery_pct: float | None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO measurements(
            node_id, temperature_external_c, temperature_internal_c, battery_v, battery_pct, measured_at
        )
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            temperature_external_c,
            temperature_internal_c,
            battery_v,
            battery_pct,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def latest_measurements() -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT n.id AS node_id, n.mesh_id, n.node_type, COALESCE(n.name, n.mesh_id) AS label,
               m.temperature_external_c, m.temperature_internal_c, m.battery_v, m.battery_pct, m.measured_at
        FROM nodes n
        LEFT JOIN measurements m ON m.id = (
            SELECT m2.id FROM measurements m2
            WHERE m2.node_id = n.id
            ORDER BY m2.measured_at DESC
            LIMIT 1
        )
        WHERE n.enabled = 1
        ORDER BY n.id ASC
        """
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def series_for_node(node_id: int, start_iso: str) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT measured_at, temperature_external_c, temperature_internal_c, battery_v, battery_pct
        FROM measurements
        WHERE node_id = ? AND measured_at >= ?
        ORDER BY measured_at ASC
        """,
        (node_id, start_iso),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def series_for_export(node_id: int, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT measured_at, temperature_external_c, temperature_internal_c, battery_v, battery_pct
        FROM measurements
        WHERE node_id = ? AND measured_at BETWEEN ? AND ?
        ORDER BY measured_at ASC
        """,
        (node_id, start_iso, end_iso),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_setting(key: str, default: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()
