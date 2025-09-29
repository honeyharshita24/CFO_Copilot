# Mini CFO Copilot

An AI-powered Streamlit app that answers simple finance questions directly from structured CSVs (actuals, budget, fx, cash). It interprets the question, runs the right data functions, and returns concise, board-ready answers with charts.

## Quick Start

```bash
# 1) Create & activate a virtual env (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Run the Streamlit app
streamlit run app.py
```

The app loads the sample CSVs from `fixtures/` by default. You can replace them with your own files as long as they keep the same columns.

## Data Files (in `fixtures/`)

- `actuals.csv` — monthly actuals by entity & account_category (Revenue, COGS, Opex:*), with a currency column
- `budget.csv` — monthly budget by entity & account_category, with a currency column
- `fx.csv` — exchange rate to USD for each month & currency (`rate_to_usd`)
- `cash.csv` — consolidated monthly cash balances in USD (`cash_usd`)

All files include a `month` column formatted `YYYY-MM`.

## Sample Questions

- “What was June 2025 revenue vs budget in USD?”
- “Show Gross Margin % trend for the last 3 months.”
- “Break down Opex by category for June 2025.”
- “What is our cash runway right now?”

## Extra Credit: Export PDF

Click **Export PDF** in the sidebar to generate a two-page PDF with:
- Revenue vs Budget (latest month)
- Opex breakdown (latest month)
- Cash trend (last 6 months)

The PDF is generated locally with `reportlab` and embedded PNG charts.

## Tests

Run a tiny test suite:

```bash
pytest -q
```

## Project Structure

```
.
├── app.py
├── agent/
│   ├── planner.py
│   └── tools.py
├── fixtures/
│   ├── actuals.csv
│   ├── budget.csv
│   ├── cash.csv
│   └── fx.csv
├── tests/
│   └── test_metrics.py
├── requirements.txt
└── README.md
```

## Notes

- This is a minimal, end‑to‑end demo scoped for a 2–3 hour build.
- Intent classification is keyword + pattern based for simplicity.
- All values are auto-converted to USD via the provided monthly FX rates.