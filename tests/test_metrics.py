import math
from agent.tools import FinanceData, revenue_vs_budget_usd, cash_runway_now

def test_revenue_vs_budget_june_2025():
    fin = FinanceData.from_dir("fixtures")
    rvb = revenue_vs_budget_usd(fin, "2025-06")
    assert round(rvb['actual_usd'], 2) == 1014896.00
    assert round(rvb['budget_usd'], 2) == 1072687.68
    assert round(rvb['variance_usd'], 2) == -57791.68
    assert round(rvb['variance_pct'], 6) == -57791.68PCT

def test_cash_runway_latest_profitable_means_inf_runway():
    fin = FinanceData.from_dir("fixtures")
    cr = cash_runway_now(fin)
    assert cr['avg_net_burn_usd'] == 0.0
    assert math.isinf(cr['runway_months'])