"""
netsuite_parser.py
==================
Parses NetSuite Balance Sheet and Income Statement exports (.csv or .xlsx).

Uses openpyxl for .xlsx and the csv stdlib module for .csv.
pandas is NOT used anywhere in this module.
"""

import csv
import calendar
import datetime
import io
import os
import re

import openpyxl


# ---------------------------------------------------------------------------
# Currency parsing
# ---------------------------------------------------------------------------

def parse_currency(value):
    """Convert a NetSuite currency string to a float.

    Examples
    --------
    >>> parse_currency("$1,236,330.48")
    1236330.48
    >>> parse_currency("($4,983.77)")
    -4983.77
    >>> parse_currency("$0.00")
    0.0
    >>> parse_currency("")
    0.0
    >>> parse_currency(None)
    0.0
    >>> parse_currency(42.5)
    42.5
    """
    if value is None:
        return 0.0

    # Already numeric — return as-is.
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text == "" or text == "-":
        return 0.0

    # Detect negative: parentheses like "($4,983.77)" or leading minus.
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
        text = text[1:]

    # Strip dollar sign, commas, whitespace.
    text = text.replace("$", "").replace(",", "").strip()

    if text == "" or text == "-":
        return 0.0

    try:
        amount = float(text)
    except ValueError:
        return 0.0

    return -amount if negative else amount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_rows(file_obj, filename):
    """Return a list-of-lists (rows × columns) from a .csv or .xlsx file.

    Parameters
    ----------
    file_obj : file-like object (binary mode for xlsx, text or binary for csv)
    filename : str – used only to determine the format from the extension.

    Returns
    -------
    list[list]  – each inner list is one row; cell values are strings or None.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".xlsx":
        # openpyxl needs a binary stream.
        if isinstance(file_obj, (str, bytes)):
            raise TypeError("file_obj must be a file-like object, not str/bytes")
        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = []
        for row in ws.iter_rows():
            rows.append([cell.value for cell in row])
        wb.close()
        return rows

    # Default: treat as CSV.
    # Ensure we have a text stream.
    if hasattr(file_obj, "mode") and "b" in getattr(file_obj, "mode", ""):
        file_obj = io.TextIOWrapper(file_obj, encoding="utf-8-sig")
    elif isinstance(file_obj, (bytes, io.RawIOBase, io.BufferedIOBase)):
        if isinstance(file_obj, bytes):
            file_obj = io.StringIO(file_obj.decode("utf-8-sig"))
        else:
            file_obj = io.TextIOWrapper(file_obj, encoding="utf-8-sig")

    reader = csv.reader(file_obj)
    return [row for row in reader]


_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_month_year(text):
    """Parse a NetSuite date header into a :class:`datetime.date`.

    Handles strings like ``"End of Dec 2025"`` → ``date(2025, 12, 31)``
    and ``"End of Mar 2026"`` → ``date(2026, 3, 31)``.

    Returns *None* if the text cannot be parsed.
    """
    if not text:
        return None

    text = str(text).strip()
    # Try to find a month abbreviation and a four-digit year.
    m = re.search(
        r"(?:end\s+of\s+)?(\w{3,})\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None

    month_str = m.group(1)[:3].lower()
    year = int(m.group(2))

    month = _MONTH_ABBR.get(month_str)
    if month is None:
        return None

    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last_day)


def date_to_quarter_label(d):
    """Convert a :class:`datetime.date` to a quarter label like ``'Q4 2025'``.

    Returns *None* if *d* is None.
    """
    if d is None:
        return None
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def _safe_str(val):
    """Return a stripped string for *val*, or '' if None."""
    if val is None:
        return ""
    return str(val).strip()


def _find_first_match(rows, target, col=0):
    """Return the first row whose column *col* (stripped, lowered) contains *target* (lowered).

    Returns ``(row_index, row)`` or ``(None, None)``.
    """
    target_lower = target.lower()
    for idx, row in enumerate(rows):
        if col < len(row):
            label = _safe_str(row[col]).lower()
            if target_lower in label:
                return idx, row
    return None, None


def _find_last_exact(rows, target, col=0):
    """Return the LAST row whose column *col* stripped equals *target* (case-insensitive).

    Returns ``(row_index, row)`` or ``(None, None)``.
    """
    target_lower = target.strip().lower()
    found_idx, found_row = None, None
    for idx, row in enumerate(rows):
        if col < len(row):
            label = _safe_str(row[col]).lower()
            if label == target_lower:
                found_idx, found_row = idx, row
    return found_idx, found_row


# ---------------------------------------------------------------------------
# Balance Sheet parser
# ---------------------------------------------------------------------------

def parse_balance_sheet(file_obj, filename):
    """Parse a NetSuite Balance Sheet export.

    Parameters
    ----------
    file_obj : file-like object (binary for .xlsx, text or binary for .csv)
    filename : str – original filename, used to detect extension.

    Returns
    -------
    dict with keys:
        balance_sheet_date      : datetime.date or None
        balance_sheet_date_str  : str  (raw text from the spreadsheet)
        cash_and_equivalents    : float
        accounts_receivable     : float
        raw_rows                : list of (label, amount) tuples
    """
    rows = _read_rows(file_obj, filename)

    # --- Date from row 4 (0-indexed row 3) ---
    date_str = ""
    balance_sheet_date = None
    # Search rows 0-9 for the date line (resilient to slight layout shifts).
    for r in rows[:10]:
        cell_text = _safe_str(r[0]) if r else ""
        if re.search(r"end\s+of", cell_text, re.IGNORECASE):
            date_str = cell_text
            balance_sheet_date = _parse_month_year(cell_text)
            break

    # --- Build raw_rows (label, amount) from the data area ---
    raw_rows = []
    for row in rows:
        if len(row) >= 2:
            label = _safe_str(row[0])
            if label:
                raw_rows.append((label, parse_currency(row[1])))

    # --- Extract key values ---
    # Cash and cash equivalents
    cash = 0.0
    idx, row = _find_first_match(rows, "total - 11000 - cash and cash equivalents")
    if idx is not None and len(row) >= 2:
        cash = parse_currency(row[1])
    else:
        # Fallback: "Total Bank"
        idx, row = _find_first_match(rows, "total bank")
        if idx is not None and len(row) >= 2:
            cash = parse_currency(row[1])

    # Accounts Receivable
    ar = 0.0
    idx, row = _find_first_match(rows, "total accounts receivable")
    if idx is not None and len(row) >= 2:
        ar = parse_currency(row[1])

    return {
        "balance_sheet_date": balance_sheet_date,
        "balance_sheet_date_str": date_str,
        "cash_and_equivalents": cash,
        "accounts_receivable": ar,
        "raw_rows": raw_rows,
    }


# ---------------------------------------------------------------------------
# Income Statement parser
# ---------------------------------------------------------------------------

def parse_income_statement(file_obj, filename, target_quarter=None):
    """Parse a NetSuite Income Statement export.

    Parameters
    ----------
    file_obj : file-like object
    filename : str – original filename, used to detect extension.

    Returns
    -------
    dict with keys:
        quarter_used            : str   (e.g. "Q1 2026")
        quarterly_revenue       : float
        quarterly_cogs          : float
        quarterly_opex          : float
        quarterly_other_expense : float
        quarterly_other_income  : float
        quarterly_net_income    : float
        monthly_revenue         : float  (quarterly / 3)
        monthly_cogs            : float  (quarterly / 3)
        monthly_opex            : float  (quarterly / 3)
        monthly_other_expense   : float  (quarterly / 3)
        monthly_other_income    : float  (quarterly / 3)
        raw_rows                : list of (label, amount) tuples
    """
    rows = _read_rows(file_obj, filename)

    # --- Detect header row and the last quarterly column ----
    # Row 7 (0-indexed 6) typically has headers.
    # We search the first 12 rows for a row containing "Financial Row" and
    # at least one "Q…" header.
    header_row_idx = None
    headers = []
    for idx in range(min(12, len(rows))):
        row = rows[idx]
        first_cell = _safe_str(row[0]).lower() if row else ""
        if "financial row" in first_cell:
            header_row_idx = idx
            headers = [_safe_str(c) for c in row]
            break

    # Determine which column is the last quarterly column (not "Total").
    # Headers look like: ["Financial Row", "Q1 2025", "Q2 2025", ..., "Total"]
    quarter_col = None
    quarter_label = ""

    # --- NEW: try to match the caller-requested quarter first ---
    if target_quarter and headers:
        tq = target_quarter.strip().lower()
        for ci, h in enumerate(headers):
            if h.strip().lower() == tq:
                quarter_col = ci
                quarter_label = headers[ci]
                break

    if quarter_col is None and headers:
        # Walk backwards from the last header to find the last Qn column.
        for ci in range(len(headers) - 1, 0, -1):
            h = headers[ci].lower()
            if h == "total" or h == "" or h == "amount":
                continue
            # Accept anything that looks like a quarter label (Q1 2025, etc.)
            if re.match(r"q[1-4]\s+\d{4}", h, re.IGNORECASE):
                quarter_col = ci
                quarter_label = headers[ci]
                break
        # If no Qn header found, use the second-to-last non-empty column.
        if quarter_col is None:
            for ci in range(len(headers) - 1, 0, -1):
                h = headers[ci].lower()
                if h == "total" or h == "":
                    continue
                quarter_col = ci
                quarter_label = headers[ci]
                break

    # Fallback: if we still have nothing, use column B (index 1).
    if quarter_col is None:
        quarter_col = 1
        quarter_label = "Unknown"

    # --- Helper to pull the value from the chosen quarter column ---
    def _val(row):
        if row is None:
            return 0.0
        if quarter_col < len(row):
            return parse_currency(row[quarter_col])
        return 0.0

    # --- Build raw_rows (label, amount_in_chosen_quarter) ---
    raw_rows = []
    for row in rows:
        if row and len(row) > quarter_col:
            label = _safe_str(row[0])
            if label:
                raw_rows.append((label, parse_currency(row[quarter_col])))

    # --- Extract key values ---

    # Revenue: "Total - Income" or "Total - 40000 - Revenue"
    revenue = 0.0
    idx, row = _find_first_match(rows, "total - 40000 - revenue")
    if idx is not None:
        revenue = _val(row)
    else:
        idx, row = _find_first_match(rows, "total - income")
        if idx is not None:
            revenue = _val(row)

    # COGS: "Total - Cost Of Sales"
    cogs = 0.0
    idx, row = _find_first_match(rows, "total - cost of sales")
    if idx is not None:
        cogs = _val(row)

    # Opex: "Total - 60000 - Operating expenses"
    opex = 0.0
    idx, row = _find_first_match(rows, "total - 60000 - operating expenses")
    if idx is not None:
        opex = _val(row)

    # Other Expense: "Total - Other Expense"
    other_expense = 0.0
    idx, row = _find_first_match(rows, "total - other expense")
    if idx is not None:
        other_expense = _val(row)

    # Other Income: "Total - Other Income" or "Total Other Income"
    other_income = 0.0
    idx, row = _find_first_match(rows, "total - other income")
    if idx is not None:
        other_income = _val(row)
    else:
        idx, row = _find_first_match(rows, "total other income")
        if idx is not None:
            other_income = _val(row)

    # Net Income: last row whose stripped label is exactly "Net Income"
    net_income = 0.0
    idx, row = _find_last_exact(rows, "net income")
    if idx is not None:
        net_income = _val(row)

    return {
        "quarter_used": quarter_label,
        "quarterly_revenue": revenue,
        "quarterly_cogs": cogs,
        "quarterly_opex": opex,
        "quarterly_other_expense": other_expense,
        "quarterly_other_income": other_income,
        "quarterly_net_income": net_income,
        "monthly_revenue": round(revenue / 3, 2),
        "monthly_cogs": round(cogs / 3, 2),
        "monthly_opex": round(opex / 3, 2),
        "monthly_other_expense": round(other_expense / 3, 2),
        "monthly_other_income": round(other_income / 3, 2),
        "raw_rows": raw_rows,
    }
