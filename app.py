from datetime import timedelta

from flask import Flask, render_template, request

from netsuite_parser import parse_balance_sheet, parse_income_statement

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

ALLOWED_EXTENSIONS = {"csv", "xlsx"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
            inc_data = parse_income_statement(inc_file, inc_file.filename)

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
            }

        except Exception as exc:
            error = str(exc)

    return render_template(
        "index.html",
        error=error,
        bs_data=bs_data,
        inc_data=inc_data,
        results=results,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
