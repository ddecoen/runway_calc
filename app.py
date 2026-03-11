"""
Company Runway Calculator – Flask Application

Calculates gross and net runway (in months) based on liquid assets,
revenue, and operating costs submitted through a single-page form.
"""

from datetime import datetime, timedelta
from flask import Flask, render_template, request

app = Flask(__name__)


def _parse_float(value, default=0.0):
    """Safely parse a form value to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value):
    """Parse an ISO-format date string (YYYY-MM-DD) or return None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def calculate_runway(inputs):
    """
    Perform all runway calculations and return a results dict.

    Parameters
    ----------
    inputs : dict
        Parsed form values (floats + balance_sheet_date as a date object).

    Returns
    -------
    dict  – keys: total_liquid_assets, gross_monthly_burn, net_monthly_burn,
            cash_flow_positive, gross_runway_months, net_runway_months,
            runway_end_date
    """
    total_liquid_assets = (
        inputs["cash_and_equivalents"] + inputs["short_term_investments"]
    )

    gross_monthly_burn = (
        inputs["monthly_cogs"]
        + inputs["monthly_operating_expenses"]
        + inputs["monthly_other_expenses"]
    )

    net_monthly_burn = gross_monthly_burn - inputs["monthly_revenue"]

    # --- Derived metrics ---------------------------------------------------
    cash_flow_positive = net_monthly_burn <= 0

    gross_runway_months = (
        round(total_liquid_assets / gross_monthly_burn, 1)
        if gross_monthly_burn > 0
        else None
    )

    net_runway_months = (
        round(total_liquid_assets / net_monthly_burn, 1)
        if net_monthly_burn > 0
        else None
    )

    # Estimate the calendar date when cash runs out
    # (use ~30.44 days/month for a reasonable approximation)
    runway_end_date = None
    if net_runway_months is not None and inputs["balance_sheet_date"] is not None:
        delta_days = int(net_runway_months * 30.4375)
        runway_end_date = inputs["balance_sheet_date"] + timedelta(days=delta_days)

    return {
        "total_liquid_assets": round(total_liquid_assets, 2),
        "gross_monthly_burn": round(gross_monthly_burn, 2),
        "net_monthly_burn": round(net_monthly_burn, 2),
        "is_cash_flow_positive": cash_flow_positive,
        "gross_runway_months": gross_runway_months,
        "net_runway_months": net_runway_months,
        "runway_end_date": runway_end_date,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    """Render the calculator form and, on POST, the results."""
    inputs = {}
    results = None

    if request.method == "POST":
        # ---- Collect & parse form data ------------------------------------
        inputs = {
            "balance_sheet_date": _parse_date(
                request.form.get("balance_sheet_date")
            ),
            "cash_and_equivalents": _parse_float(
                request.form.get("cash_and_equivalents")
            ),
            "short_term_investments": _parse_float(
                request.form.get("short_term_investments")
            ),
            "accounts_receivable": _parse_float(
                request.form.get("accounts_receivable")
            ),
            "monthly_revenue": _parse_float(
                request.form.get("monthly_revenue")
            ),
            "monthly_cogs": _parse_float(
                request.form.get("monthly_cogs")
            ),
            "monthly_operating_expenses": _parse_float(
                request.form.get("monthly_operating_expenses")
            ),
            "monthly_other_expenses": _parse_float(
                request.form.get("monthly_other_expenses"), default=0.0
            ),
        }

        # ---- Run calculations ---------------------------------------------
        results = calculate_runway(inputs)

    # Build raw form_data from the request so the template can repopulate fields
    form_data = {k: v for k, v in request.form.items()} if request.method == "POST" else None
    return render_template("index.html", form_data=form_data, results=results, error=None)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
