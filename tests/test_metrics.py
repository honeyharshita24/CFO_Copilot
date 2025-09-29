import math
import pandas as pd
from agent.tools import (
    FinanceData, revenue_vs_budget_usd, cash_runway_now,
    to_usd, month_str, latest_month, gross_margin_pct_trend,
    opex_breakdown_usd, ebitda_by_month, extract_month_from_text,
    parse_last_n_months, classify_intent
)

def test_to_usd_with_empty_dataframe():
    empty_df = pd.DataFrame(columns=["month", "currency", "amount"])
    fx_df = pd.DataFrame({
        "month": ["2025-06"],
        "currency": ["USD"],
        "rate_to_usd": [1.0]
    })
    result = to_usd(empty_df, fx_df)
    assert "usd" in result.columns
    assert len(result) == 0

def test_to_usd_with_data():
    df = pd.DataFrame({
        "month": ["2025-06", "2025-06"],
        "currency": ["USD", "EUR"],
        "amount": [1000, 1000]
    })
    fx_df = pd.DataFrame({
        "month": ["2025-06", "2025-06"],
        "currency": ["USD", "EUR"],
        "rate_to_usd": [1.0, 1.1]
    })
    result = to_usd(df, fx_df)
    assert round(result.loc[result["currency"] == "USD", "usd"].iloc[0], 2) == 1000.00
    assert round(result.loc[result["currency"] == "EUR", "usd"].iloc[0], 2) == 1100.00

def test_month_str_formats():
    assert month_str("2025-06") == "2025-06"
    assert month_str("June 2025") == "2025-06"
    assert month_str("2025-6") == "2025-06"
    assert month_str(pd.Timestamp("2025-06-15")) == "2025-06"
    assert month_str("invalid") == "invalid"  # fallback case

def test_latest_month():
    months = ["2025-01", "2025-06", "2025-03"]
    assert latest_month(months) == "2025-06"

def test_gross_margin_pct_trend():
    fin = FinanceData.from_dir("fixtures")
    months = ["2025-04", "2025-05", "2025-06"]
    result = gross_margin_pct_trend(fin, months)
    assert len(result) == 3
    assert all(m in result["month"].values for m in months)
    assert all(0 <= gm <= 1 for gm in result["gm_pct"])  # GM% should be between 0-100%

def test_gross_margin_pct_trend_empty():
    # Create empty DataFrames
    fin = FinanceData(
        actuals=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        budget=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        fx=pd.DataFrame(columns=["month", "currency", "rate_to_usd"]),
        cash=pd.DataFrame(columns=["month", "cash_usd"])
    )
    months = ["2025-04", "2025-05", "2025-06"]
    result = gross_margin_pct_trend(fin, months)
    assert len(result) == 3
    assert all(m in result["month"].values for m in months)
    assert all(pd.isna(gm) for gm in result["gm_pct"])  # Should be NaN when no data

def test_opex_breakdown_empty():
    # Test with empty data
    fin = FinanceData(
        actuals=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        budget=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        fx=pd.DataFrame(columns=["month", "currency", "rate_to_usd"]),
        cash=pd.DataFrame(columns=["month", "cash_usd"])
    )
    result = opex_breakdown_usd(fin, "2025-06")
    assert len(result) == 0
    assert "account_category" in result.columns
    assert "usd" in result.columns

def test_opex_breakdown_with_data():
    fin = FinanceData.from_dir("fixtures")
    result = opex_breakdown_usd(fin, "2025-06")
    # Check that we have some opex categories
    assert len(result) > 0
    assert all(c.startswith("Opex:") for c in result["account_category"])
    # Values should be sorted in descending order
    assert all(result["usd"].iloc[i] >= result["usd"].iloc[i+1] for i in range(len(result)-1))

def test_ebitda_by_month_with_data():
    fin = FinanceData.from_dir("fixtures")
    result = ebitda_by_month(fin)
    assert set(result.columns) == {"month", "EBITDA", "Opex_total", "Revenue", "COGS"}
    assert len(result) > 0
    # Basic sanity checks
    assert all(result["Revenue"] >= 0)  # Revenue should be positive
    assert all(result["EBITDA"] == result["Revenue"] - result["COGS"] - result["Opex_total"])

def test_ebitda_by_month_empty():
    fin = FinanceData(
        actuals=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        budget=pd.DataFrame(columns=["month", "account_category", "amount", "currency"]),
        fx=pd.DataFrame(columns=["month", "currency", "rate_to_usd"]),
        cash=pd.DataFrame(columns=["month", "cash_usd"])
    )
    result = ebitda_by_month(fin)
    assert set(result.columns) == {"month", "EBITDA", "Opex_total", "Revenue", "COGS"}
    assert len(result) == 0

def test_extract_month_from_text():
    assert extract_month_from_text("June 2025") == "2025-06"
    assert extract_month_from_text("jun 2025") == "2025-06"
    assert extract_month_from_text("2025-06") == "2025-06"
    assert extract_month_from_text("for June") == "XXXX-06"
    assert extract_month_from_text("no date here") == None

def test_parse_last_n_months():
    assert parse_last_n_months("last 3 months") == 3
    assert parse_last_n_months("last three months") == 3
    assert parse_last_n_months("show me last 6 months") == 6
    assert parse_last_n_months("last twelve months") == 12
    assert parse_last_n_months("not a time range") == None

def test_classify_intent():
    assert classify_intent("show revenue vs budget") == "revenue_vs_budget"
    assert classify_intent("what's our gross margin") == "gross_margin_trend"
    assert classify_intent("show opex breakdown") == "opex_breakdown"
    assert classify_intent("what's our cash runway") == "cash_runway"
    assert classify_intent("show ebitda trend") == "ebitda_trend"
    assert classify_intent("unknown command") == "help"

def test_revenue_vs_budget_june_2025():
    fin = FinanceData.from_dir("fixtures")
    rvb = revenue_vs_budget_usd(fin, "2025-06")
    assert round(rvb['actual_usd'], 2) == 1014896.00
    assert round(rvb['budget_usd'], 2) == 1072687.68
    assert round(rvb['variance_usd'], 2) == -57791.68

def test_cash_runway_latest_profitable_means_inf_runway():
    fin = FinanceData.from_dir("fixtures")
    cr = cash_runway_now(fin)
    assert cr['avg_net_burn_usd'] == 0.0
    assert math.isinf(cr['runway_months'])