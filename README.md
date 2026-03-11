# Company Runway Calculator

A web application that calculates how long a company can sustain operations based on its current cash position and monthly burn rate. Upload your **NetSuite Balance Sheet** and **Income Statement** exports directly — the app parses the reports and computes runway automatically.

---

## How It Works

1. **Export** a quarterly Balance Sheet and Income Statement from NetSuite as `.csv` or `.xlsx`
2. **Upload** both files into the calculator
3. **Review** extracted financials and runway analysis instantly

The app extracts key line items from standard NetSuite report formats:

| From Balance Sheet | From Income Statement (last quarter ÷ 3) |
|---|---|
| Cash & Cash Equivalents (`Total - 11000`) | Revenue (`Total - Income`) |
| Accounts Receivable (`Total Accounts Receivable`) | COGS (`Total - Cost Of Sales`) |
| | Operating Expenses (`Total - 60000`) |
| | Other Income / Expense |

---

## Features

- **NetSuite file upload** — Supports `.csv` and `.xlsx` exports directly from NetSuite
- **Auto-parsing** — Extracts cash, revenue, COGS, operating expenses, and other income/expenses from standard NetSuite report formats
- **Quarterly → Monthly** — Divides income statement figures by 3 for monthly burn rate
- **Runway projection** — Gross runway (ignoring revenue) and net runway (after revenue offset)
- **Visual indicators** — Color-coded results:
  - 🟢 **Green** (12+ months) — Healthy runway
  - 🟡 **Yellow** (6–12 months) — Caution
  - 🔴 **Red** (< 6 months) — Critical
- **Runway gauge** — Visual bar chart scaled to 24 months
- **Extracted data review** — See exactly which values were pulled from your reports

---

## Installation & Usage

### Prerequisites

- Python 3.9+

### Steps

```bash
git clone https://github.com/ddecoen/runway_calc.git
cd runway_calc
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 in your browser.

### Updating to the Latest Version

If you've already cloned the repo and want to pull the latest changes:

```bash
cd runway_calc
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
```

Then restart the app with `python app.py`.

---

## Key Financial Terms

| Term | Definition |
|---|---|
| **Liquid Assets** | Cash and cash equivalents that fund operations (bank balances, money-market funds, short-term investments). |
| **Gross Burn Rate** | Total monthly cash outflows (COGS + OpEx + Other Expenses) before revenue. |
| **Net Burn Rate** | Monthly cash consumption after revenue and other income: `Gross Burn − Revenue − Other Income`. |
| **Runway** | Months of remaining operations: `Liquid Assets ÷ Net Burn Rate`. |

---

## Project Structure

```
runway_calc/
├── app.py                 # Flask application
├── netsuite_parser.py     # NetSuite CSV/XLSX report parser
├── requirements.txt       # Python dependencies
├── README.md
├── templates/
│   └── index.html         # UI template
└── tests/
    ├── test_balance_sheet.csv
    └── test_income_statement.csv
```

---

## NetSuite Export Format

### Balance Sheet
- Column A: account labels (hierarchical with indentation)
- Column B: amounts
- Row 4: date line (e.g., "End of Dec 2025")

### Income Statement
- Column A: account labels
- Columns B+: quarterly amounts (Q1 2025, Q2 2025, ...) + Total
- The **last quarterly column** (before Total) is used automatically

---

## License

MIT
