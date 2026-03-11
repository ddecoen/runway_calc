# Company Runway Calculator

A web application that calculates how long a company can sustain operations based on its current cash position and monthly burn rate as of a specific balance sheet date.

Built with **Flask** and vanilla JavaScript, this tool helps founders, CFOs, and financial analysts quickly assess a company's financial runway with clear visual feedback.

---

## Screenshot

> ![Company Runway Calculator](screenshot.png)
> *Screenshot placeholder – replace with an actual capture of the running application.*

---

## Features

- **Balance Sheet Date Input** — Specify the exact date of the financial snapshot for accurate, time-anchored projections.
- **Burn Rate Calculation** — Enter monthly revenue and expenses to compute both gross and net burn rates automatically.
- **Runway Projection** — Calculates the number of months of remaining runway and the estimated cash-out date.
- **Visual Status Indicators** — Color-coded results provide at-a-glance health assessment:
  - 🟢 **Green** (18+ months) — Healthy runway
  - 🟡 **Yellow** (12–18 months) — Caution; begin planning
  - 🟠 **Orange** (6–12 months) — Elevated risk; act soon
  - 🔴 **Red** (< 6 months) — Critical; immediate action required

---

## Installation & Usage

### Prerequisites

- Python 3.9 or higher

### Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd runway_calc
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

4. **Open in your browser**
   ```
   http://localhost:5000
   ```

---

## Key Financial Terms

| Term | Definition |
|---|---|
| **Liquid Assets** | Cash and cash-equivalent holdings that can be quickly converted to fund operations (e.g., bank balances, money-market funds). |
| **Gross Burn Rate** | Total monthly operating expenses before accounting for any incoming revenue. |
| **Net Burn Rate** | Monthly cash consumption after revenue is subtracted from expenses (*Expenses − Revenue*). This reflects the actual rate at which cash reserves are depleted. |
| **Runway** | The estimated number of months a company can continue operating before its liquid assets are fully exhausted, calculated as *Liquid Assets ÷ Net Burn Rate*. |

---

## Project Structure

```
runway_calc/
├── app.py                 # Flask application entry point
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
├── templates/
│   └── index.html         # Main UI template
└── static/
    ├── css/
    │   └── style.css      # Application styles
    └── js/
        └── main.js        # Client-side logic
```

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
