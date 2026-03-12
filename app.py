from datetime import timedelta
from io import BytesIO
import json

from flask import Flask, redirect, render_template, request, send_file, session, url_for

from netsuite_parser import parse_balance_sheet, parse_income_statement, date_to_quarter_label
from report_export import generate_excel, generate_pdf
from db import init_db, save_report, get_all_reports, get_report, delete_report

app = Flask(__name__)
app.secret_key = "runway-calc-session-key"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

init_db()

ALLOWED_EXTENSIONS = {"csv", "xlsx"}

ADJUSTMENT_CATEGORIES = {
    "balance_sheet": [
        ("fundraising", "Fundraising / Equity Raise"),
        ("debt_proceeds", "Debt / Loan Proceeds"),
        ("asset_sale", "One-time Asset Sale"),
        ("bs_other", "Other Balance Sheet Adjustment"),
    ],
    "revenue": [
        ("multi_year_deal", "Multi-year / Prepaid Contract"),
        ("onetime_revenue", "One-time Project / Services Revenue"),
        ("rev_other", "Other Revenue Adjustment"),
    ],
    "expense": [
        ("severance", "Severance / Restructuring"),
        ("legal_settlement", "One-time Legal Settlement"),
        ("onetime_bonus", "One-time Bonus / Retention Payment"),
        ("exp_other", "Other Expense Adjustment"),
    ],
}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _calc_runway(total_liquid_assets, monthly_revenue, monthly_cogs, monthly_opex,
                 monthly_other_expense, monthly_other_income, balance_sheet_date):
    """Compute runway metrics from monthly figures. Returns a dict."""
    gross_monthly_burn = monthly_cogs + monthly_opex + monthly_other_expense
    net_monthly_burn = gross_monthly_burn - monthly_revenue - monthly_other_income
    is_cash_flow_positive = net_monthly_burn <= 0
    gross_runway_months = None
    net_runway_months = None
    runway_end_date = None
    if gross_monthly_burn > 0:
        gross_runway_months = total_liquid_assets / gross_monthly_burn
    if not is_cash_flow_positive and net_monthly_burn > 0:
        net_runway_months = total_liquid_assets / net_monthly_burn
        if balance_sheet_date:
            runway_end_date = balance_sheet_date + timedelta(days=net_runway_months * 30.4375)
    return {
        "total_liquid_assets": total_liquid_assets,
        "monthly_revenue": monthly_revenue,
        "monthly_cogs": monthly_cogs,
        "monthly_opex": monthly_opex,
        "monthly_other_expense": monthly_other_expense,
        "monthly_other_income": monthly_other_income,
        "gross_monthly_burn": gross_monthly_burn,
        "net_monthly_burn": net_monthly_burn,
        "is_cash_flow_positive": is_cash_flow_positive,
        "gross_runway_months": gross_runway_months,
        "net_runway_months": net_runway_months,
        "runway_end_date": runway_end_date,
    }


def _serialize_results(results):
    """Convert results dict to JSON-serializable form for session storage."""
    import datetime
    def _convert(obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(item) for item in obj]
        return obj
    return _convert(results)

def _deserialize_results(data):
    """Restore date objects from session-stored results."""
    import datetime
    results = dict(data) if isinstance(data, dict) else {}
    for key in ("balance_sheet_date", "runway_end_date"):
        if results.get(key) and isinstance(results[key], str):
            try:
                results[key] = datetime.date.fromisoformat(results[key])
            except (ValueError, TypeError):
                pass
    # Also deserialize dates in the adjusted sub-dict
    if isinstance(results.get("adjusted"), dict):
        adj = results["adjusted"]
        for key in ("runway_end_date",):
            if adj.get(key) and isinstance(adj[key], str):
                try:
                    adj[key] = datetime.date.fromisoformat(adj[key])
                except (ValueError, TypeError):
                    pass
    return results


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    bs_data = None
    inc_data = None
    results = None

    if request.method == "POST":
        try:
            # ----------------------------------------------------------
            # 1. Accept the two file uploads
            # ----------------------------------------------------------
            bs_file = request.files.get("balance_sheet")
            inc_file = request.files.get("income_statement")

            # ----------------------------------------------------------
            # 2. Validate presence and allowed extensions
            # ----------------------------------------------------------
            if not bs_file or bs_file.filename == "":
                raise ValueError("Balance Sheet file is required.")
            if not inc_file or inc_file.filename == "":
                raise ValueError("Income Statement file is required.")

            if not _allowed_file(bs_file.filename):
                raise ValueError(
                    "Balance Sheet must be a .csv or .xlsx file."
                )
            if not _allowed_file(inc_file.filename):
                raise ValueError(
                    "Income Statement must be a .csv or .xlsx file."
                )

            # ----------------------------------------------------------
            # 3. Parse uploaded files via netsuite_parser helpers
            # ----------------------------------------------------------
            bs_data = parse_balance_sheet(bs_file, bs_file.filename)

            # Derive target quarter from balance sheet date
            target_quarter = date_to_quarter_label(bs_data["balance_sheet_date"])

            inc_data = parse_income_statement(inc_file, inc_file.filename, target_quarter=target_quarter)

            # ----------------------------------------------------------
            # 4. Build runway-calculation inputs from parsed data
            # ----------------------------------------------------------
            total_liquid_assets = bs_data["cash_and_equivalents"]
            monthly_revenue = inc_data["monthly_revenue"]
            monthly_cogs = inc_data["monthly_cogs"]
            monthly_opex = inc_data["monthly_opex"]
            monthly_other_expense = inc_data["monthly_other_expense"]
            monthly_other_income = inc_data["monthly_other_income"]

            # ----------------------------------------------------------
            # 5. Calculate runway metrics
            # ----------------------------------------------------------
            gross_monthly_burn = monthly_cogs + monthly_opex + monthly_other_expense
            net_monthly_burn = gross_monthly_burn - monthly_revenue - monthly_other_income

            is_cash_flow_positive = net_monthly_burn <= 0
            gross_runway_months = None
            net_runway_months = None
            runway_end_date = None

            if gross_monthly_burn > 0:
                gross_runway_months = total_liquid_assets / gross_monthly_burn

            if not is_cash_flow_positive and net_monthly_burn > 0:
                net_runway_months = total_liquid_assets / net_monthly_burn
                runway_end_date = bs_data["balance_sheet_date"] + timedelta(
                    days=net_runway_months * 30.4375
                )

            # ----------------------------------------------------------
            # 6. Assemble results dict for the template
            # ----------------------------------------------------------
            results = {
                "balance_sheet_date": bs_data["balance_sheet_date"],
                "balance_sheet_date_str": bs_data["balance_sheet_date_str"],
                "cash_and_equivalents": bs_data["cash_and_equivalents"],
                "total_liquid_assets": total_liquid_assets,
                "accounts_receivable": bs_data["accounts_receivable"],
                "quarterly_revenue": inc_data["quarterly_revenue"],
                "quarterly_cogs": inc_data["quarterly_cogs"],
                "quarterly_opex": inc_data["quarterly_opex"],
                "quarterly_other_expense": inc_data["quarterly_other_expense"],
                "quarterly_other_income": inc_data["quarterly_other_income"],
                "quarter_used": inc_data["quarter_used"],
                "monthly_revenue": monthly_revenue,
                "monthly_cogs": monthly_cogs,
                "monthly_opex": monthly_opex,
                "monthly_other_expense": monthly_other_expense,
                "monthly_other_income": monthly_other_income,
                "gross_monthly_burn": gross_monthly_burn,
                "net_monthly_burn": net_monthly_burn,
                "is_cash_flow_positive": is_cash_flow_positive,
                "gross_runway_months": gross_runway_months,
                "net_runway_months": net_runway_months,
                "runway_end_date": runway_end_date,
                "adjustments": [],
                "adjusted": None,
            }

            # Store results in session for download routes
            session["last_results"] = _serialize_results(results)

            save_report(results)

        except Exception as exc:
            error = str(exc)

    saved_reports = get_all_reports()

    return render_template(
        "index.html",
        error=error,
        bs_data=bs_data,
        inc_data=inc_data,
        results=results,
        saved_reports=saved_reports,
        adjustment_categories=ADJUSTMENT_CATEGORIES,
    )


@app.route("/adjust", methods=["POST"])
def adjust():
    """Apply one-off adjustments to the most recent calculation."""
    error = None
    results = None

    try:
        # Load unadjusted results from session
        data = session.get("last_results")
        if not data:
            return redirect(url_for("index"))
        results = _deserialize_results(data)

        # Parse adjustment form data
        adjustments = []

        # Balance sheet adjustments
        i = 0
        while True:
            cat = request.form.get(f"bs_cat_{i}")
            if cat is None:
                break
            desc = request.form.get(f"bs_desc_{i}", "").strip()
            amt_str = request.form.get(f"bs_amt_{i}", "0")
            try:
                amt = float(amt_str)
            except (ValueError, TypeError):
                amt = 0.0
            if amt > 0:
                adjustments.append({
                    "type": "balance_sheet",
                    "category": cat,
                    "description": desc,
                    "amount": amt,
                })
            i += 1

        # Revenue adjustments
        i = 0
        while True:
            cat = request.form.get(f"rev_cat_{i}")
            if cat is None:
                break
            desc = request.form.get(f"rev_desc_{i}", "").strip()
            amt_str = request.form.get(f"rev_amt_{i}", "0")
            try:
                amt = float(amt_str)
            except (ValueError, TypeError):
                amt = 0.0
            if amt > 0:
                adjustments.append({
                    "type": "revenue",
                    "category": cat,
                    "description": desc,
                    "amount": amt,
                })
            i += 1

        # Expense adjustments
        i = 0
        while True:
            cat = request.form.get(f"exp_cat_{i}")
            if cat is None:
                break
            desc = request.form.get(f"exp_desc_{i}", "").strip()
            amt_str = request.form.get(f"exp_amt_{i}", "0")
            try:
                amt = float(amt_str)
            except (ValueError, TypeError):
                amt = 0.0
            if amt > 0:
                adjustments.append({
                    "type": "expense",
                    "category": cat,
                    "description": desc,
                    "amount": amt,
                })
            i += 1

        results["adjustments"] = adjustments

        if adjustments:
            # Calculate adjusted values
            bs_adj_total = sum(a["amount"] for a in adjustments if a["type"] == "balance_sheet")
            rev_adj_total = sum(a["amount"] for a in adjustments if a["type"] == "revenue")
            exp_adj_total = sum(a["amount"] for a in adjustments if a["type"] == "expense")

            adj_liquid = results["total_liquid_assets"] - bs_adj_total
            # Revenue adjustments reduce quarterly revenue, so reduce monthly by adj/3
            adj_monthly_revenue = results["monthly_revenue"] - (rev_adj_total / 3)
            # Expense adjustments reduce quarterly opex, so reduce monthly by adj/3
            adj_monthly_opex = results["monthly_opex"] - (exp_adj_total / 3)

            adjusted = _calc_runway(
                total_liquid_assets=adj_liquid,
                monthly_revenue=adj_monthly_revenue,
                monthly_cogs=results["monthly_cogs"],
                monthly_opex=adj_monthly_opex,
                monthly_other_expense=results["monthly_other_expense"],
                monthly_other_income=results["monthly_other_income"],
                balance_sheet_date=results.get("balance_sheet_date"),
            )
            results["adjusted"] = adjusted
        else:
            results["adjusted"] = None

        # Update session and save
        session["last_results"] = _serialize_results(results)
        save_report(results)

    except Exception as exc:
        error = str(exc)

    saved_reports = get_all_reports()
    return render_template(
        "index.html",
        error=error,
        bs_data=None,
        inc_data=None,
        results=results,
        saved_reports=saved_reports,
        adjustment_categories=ADJUSTMENT_CATEGORIES,
    )


@app.route("/report/<int:report_id>")
def view_report(report_id):
    results = get_report(report_id)
    if not results:
        return "Report not found.", 404
    session["last_results"] = _serialize_results(results)
    saved_reports = get_all_reports()
    return render_template(
        "index.html",
        error=None,
        bs_data=None,
        inc_data=None,
        results=results,
        saved_reports=saved_reports,
        viewing_saved=True,
        adjustment_categories=ADJUSTMENT_CATEGORIES,
    )


@app.route("/report/<int:report_id>/delete", methods=["POST"])
def delete_report_route(report_id):
    delete_report(report_id)
    return redirect(url_for("index"))


@app.route("/download/excel")
@app.route("/download/excel/<int:report_id>")
def download_excel(report_id=None):
    if report_id:
        results = get_report(report_id)
        if not results:
            return "Report not found.", 404
    else:
        data = session.get("last_results")
        if not data:
            return "No report data available. Please run a calculation first.", 400
        results = _deserialize_results(data)
    buf = generate_excel(results)
    quarter = results.get("quarter_used", "report")
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"runway_{quarter.replace(' ', '_')}.xlsx",
    )

@app.route("/download/pdf")
@app.route("/download/pdf/<int:report_id>")
def download_pdf(report_id=None):
    if report_id:
        results = get_report(report_id)
        if not results:
            return "Report not found.", 404
    else:
        data = session.get("last_results")
        if not data:
            return "No report data available. Please run a calculation first.", 400
        results = _deserialize_results(data)
    buf = generate_pdf(results)
    quarter = results.get("quarter_used", "report")
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"runway_{quarter.replace(' ', '_')}.pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
