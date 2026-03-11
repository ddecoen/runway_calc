"""
Simple SQLite persistence layer for saving runway reports.

Stores reports in data/reports.db relative to this file's directory.
"""

import json
import os
import sqlite3
import datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_db_path():
    """Return the absolute path to data/reports.db."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "data", "reports.db")


def _serialize_for_db(results):
    """Convert a results dict to a JSON string.

    datetime.date and datetime.datetime objects are converted to ISO-format
    strings so the dict is JSON-serialisable.
    """

    def _default(obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(results, default=_default)


def _deserialize_from_db(json_str):
    """Convert a JSON string back to a results dict.

    Keys ``balance_sheet_date`` and ``runway_end_date`` are converted from
    ISO-format strings back to :class:`datetime.date` objects.
    """
    data = json.loads(json_str)

    date_keys = ("balance_sheet_date", "runway_end_date")
    for key in date_keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            try:
                data[key] = datetime.date.fromisoformat(value)
            except ValueError:
                pass  # leave as string if it doesn't parse

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db():
    """Create the ``data/`` directory and the ``reports`` table if needed."""
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """\
            CREATE TABLE IF NOT EXISTS reports (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter_label        TEXT NOT NULL UNIQUE,
                balance_sheet_date   TEXT,
                balance_sheet_date_str TEXT,
                results_json         TEXT NOT NULL,
                created_at           TEXT NOT NULL DEFAULT (datetime('now'))
            );"""
        )
        conn.commit()
    finally:
        conn.close()


def save_report(results_dict):
    """Persist a runway report (upsert keyed on *quarter_label*).

    Parameters
    ----------
    results_dict : dict
        The same results dict passed to the template.  Must contain at least
        ``quarter_used``.

    Returns
    -------
    int
        The ``id`` of the inserted / updated row.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        quarter_label = results_dict.get("quarter_used", "")

        # Normalise balance_sheet_date to an ISO string for the indexed column.
        bs_date = results_dict.get("balance_sheet_date")
        if isinstance(bs_date, (datetime.date, datetime.datetime)):
            bs_date_iso = bs_date.isoformat()
        elif isinstance(bs_date, str):
            bs_date_iso = bs_date
        else:
            bs_date_iso = None

        bs_date_str = results_dict.get("balance_sheet_date_str")
        results_json = _serialize_for_db(results_dict)

        cursor = conn.execute(
            """\
            INSERT INTO reports (quarter_label, balance_sheet_date,
                                 balance_sheet_date_str, results_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(quarter_label) DO UPDATE SET
                balance_sheet_date     = excluded.balance_sheet_date,
                balance_sheet_date_str = excluded.balance_sheet_date_str,
                results_json           = excluded.results_json,
                created_at             = datetime('now');""",
            (quarter_label, bs_date_iso, bs_date_str, results_json),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_all_reports():
    """Return a lightweight list of every saved report.

    Returns
    -------
    list[dict]
        Each dict contains ``id``, ``quarter_label``, ``balance_sheet_date``,
        and ``created_at``.  Ordered by *balance_sheet_date* descending
        (most recent quarter first).
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """\
            SELECT id, quarter_label, balance_sheet_date, created_at, results_json
            FROM reports
            ORDER BY balance_sheet_date DESC;"""
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Extract key metrics from results_json for the listing
            try:
                data = json.loads(d.pop("results_json", "{}"))
                d["net_runway_months"] = data.get("net_runway_months")
                d["is_cash_flow_positive"] = data.get("is_cash_flow_positive", False)
            except (json.JSONDecodeError, TypeError):
                d["net_runway_months"] = None
                d["is_cash_flow_positive"] = False
            results.append(d)
        return results
    finally:
        conn.close()


def get_report(report_id):
    """Fetch a single report and return the full deserialised results dict.

    Parameters
    ----------
    report_id : int

    Returns
    -------
    dict or None
        The results dict (with date objects restored), or ``None`` if the
        *report_id* does not exist.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT results_json FROM reports WHERE id = ?;",
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return _deserialize_from_db(row["results_json"])
    finally:
        conn.close()


def delete_report(report_id):
    """Delete a report by id.

    Returns
    -------
    bool
        ``True`` if a row was deleted, ``False`` if the id was not found.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM reports WHERE id = ?;",
            (report_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
