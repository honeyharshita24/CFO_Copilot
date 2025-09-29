from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dateutil import parser as dateparser
import matplotlib.pyplot as plt

# -----------------------------
# Data Loading & Utilities
# -----------------------------

@dataclass
class FinanceData:
    actuals: pd.DataFrame
    budget: pd.DataFrame
    fx: pd.DataFrame
    cash: pd.DataFrame

    @classmethod
    def from_dir(cls, path: str = "fixtures") -> "FinanceData":
        actuals = pd.read_csv(f"{path}/actuals.csv")
        budget  = pd.read_csv(f"{path}/budget.csv")
        fx      = pd.read_csv(f"{path}/fx.csv")
        cash    = pd.read_csv(f"{path}/cash.csv")

        # Normalize types
        for df in (actuals, budget, fx, cash):
            df["month"] = df["month"].astype(str)

        return cls(actuals=actuals, budget=budget, fx=fx, cash=cash)

def to_usd(df: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """Attach USD amounts using FX by month + currency."""
    if df.empty:
        out = df.copy()
        out["usd"] = 0.0
        return out
    merged = df.merge(fx, how="left", on=["month", "currency"])
    merged["usd"] = merged["amount"] * merged["rate_to_usd"]
    return merged

def month_str(dt_like: str | pd.Timestamp) -> str:
    """Return YYYY-MM."""
    if isinstance(dt_like, pd.Timestamp):
        return dt_like.strftime("%Y-%m")
    s = str(dt_like)
    # accept YYYY-MM or any parseable date
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s
    try:
        d = dateparser.parse(s)
        return f"{d.year:04d}-{d.month:02d}"
    except Exception:
        return s  # fallback

def latest_month(all_months: List[str]) -> str:
    return sorted(all_months)[-1]

# -----------------------------
# Metrics
# -----------------------------

def revenue_vs_budget_usd(fin: FinanceData, month: str) -> Dict[str, float]:
    m = month_str(month)
    a = fin.actuals[(fin.actuals["month"] == m) & (fin.actuals["account_category"] == "Revenue")].copy()
    b = fin.budget[(fin.budget["month"] == m) & (fin.budget["account_category"] == "Revenue")].copy()
    a_usd = to_usd(a, fin.fx)["usd"].sum()
    b_usd = to_usd(b, fin.fx)["usd"].sum()
    return {
        "month": m,
        "actual_usd": float(a_usd),
        "budget_usd": float(b_usd),
        "variance_usd": float(a_usd - b_usd),
        "variance_pct": float(((a_usd - b_usd) / b_usd) if b_usd else np.nan),
    }

def gross_margin_pct_trend(fin: FinanceData, months: List[str]) -> pd.DataFrame:
    a = to_usd(fin.actuals[fin.actuals["month"].isin(months)], fin.fx)
    pt = (
        a.pivot_table(index="month", columns="account_category", values="usd", aggfunc="sum")
        .fillna(0.0)
    )
    rev = pt.get("Revenue", 0.0)
    cogs = pt.get("COGS", 0.0)
    gm_pct = (rev - cogs) / rev.replace(0, np.nan)
    out = pd.DataFrame({"month": gm_pct.index, "gm_pct": gm_pct.values})
    out = out.sort_values("month")
    return out

def opex_breakdown_usd(fin: FinanceData, month: str) -> pd.DataFrame:
    m = month_str(month)
    a = fin.actuals[(fin.actuals["month"] == m) & (fin.actuals["account_category"].str.startswith("Opex:"))].copy()
    if a.empty:
        return pd.DataFrame({"account_category": [], "usd": []})
    usd = to_usd(a, fin.fx)
    out = usd.groupby("account_category")["usd"].sum().sort_values(ascending=False).reset_index()
    return out

def ebitda_by_month(fin: FinanceData) -> pd.DataFrame:
    a = to_usd(fin.actuals, fin.fx)
    pt = (
        a.pivot_table(index="month", columns="account_category", values="usd", aggfunc="sum")
        .fillna(0.0)
    )
    opex_cols = [c for c in pt.columns if str(c).startswith("Opex:")]
    pt["Opex_total"] = pt[opex_cols].sum(axis=1)
    pt["EBITDA"] = pt.get("Revenue", 0.0) - pt.get("COGS", 0.0) - pt["Opex_total"]
    pt = pt[["EBITDA", "Opex_total", "Revenue", "COGS"]].reset_index()
    pt = pt.sort_values("month")
    return pt

def cash_runway_now(fin: FinanceData) -> Dict[str, float | str]:
    latest = latest_month(list(fin.cash["month"].unique()))
    cash_row = fin.cash[fin.cash["month"] == latest]["cash_usd"]
    cash_usd = float(cash_row.iloc[0]) if not cash_row.empty else np.nan

    e = ebitda_by_month(fin).set_index("month")
    last3 = sorted(fin.actuals["month"].unique())[-3:]
    e3 = e.loc[last3, "EBITDA"]
    net_burn = np.maximum(0.0, -e3.values)  # only count burn (loss)
    avg_burn = float(np.mean(net_burn))

    if avg_burn == 0:
        runway = np.inf
        runway_text = "Profitable over the last 3 months (no net burn). Runway: N/A"
    else:
        months = cash_usd / avg_burn
        runway = float(months)
        runway_text = f"~{months:.1f} months of runway"

    return {
        "as_of": latest,
        "cash_usd": cash_usd,
        "avg_net_burn_usd": avg_burn,
        "runway_months": runway,
        "note": runway_text,
    }

# -----------------------------
# Parsing / Intent
# -----------------------------

INTENTS = {
    "revenue_vs_budget": ["revenue vs budget", "revenue versus budget", "revenue budget"],
    "gross_margin_trend": ["gross margin", "gm%", "gm %", "gross margin %", "gross margin pct"],
    "opex_breakdown": ["opex", "operating expenses", "opex breakdown"],
    "cash_runway": ["cash runway", "runway"],
    "ebitda_trend": ["ebitda"],
}

MONTH_NAME_TO_NUM = {m.lower(): i for i, m in enumerate(["", "January","February","March","April","May","June","July","August","September","October","November","December"])}

def extract_month_from_text(text: str) -> Optional[str]:
    text_l = text.lower()

    # Try "June 2025" / "Jun 2025" / "2025-06"
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+([12][0-9]{3})", text_l)
    if m:
        mon_txt, year = m.group(1), m.group(2)
        mon_idx = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].index(mon_txt) + 1
        return f"{int(year):04d}-{mon_idx:02d}"

    # "YYYY-MM"
    m2 = re.search(r"([12][0-9]{3})-(0[1-9]|1[0-2])", text_l)
    if m2:
        return m2.group(0)

    # "for June" (assume latest year present in data)
    m3 = re.search(r"for\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", text_l)
    if m3:
        mon_txt = m3.group(1)
        mon_idx = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].index(mon_txt) + 1
        # year will be filled by caller if needed
        return f"XXXX-{mon_idx:02d}"

    return None

def parse_last_n_months(text: str) -> Optional[int]:
    m = re.search(r"last\s+(\d+)\s+months?", text.lower())
    if m:
        return int(m.group(1))
    m2 = re.search(r"last\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?", text.lower())
    if m2:
        mapping = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12}
        return mapping[m2.group(1)]
    return None

def classify_intent(text: str) -> str:
    t = text.lower().strip()
    # direct keywords
    if "cash runway" in t or re.search(r"\brunway\b", t):
        return "cash_runway"
    if "revenue" in t and ("vs" in t or "versus" in t or "budget" in t):
        return "revenue_vs_budget"
    if "gross margin" in t or "gm%" in t or "gm %" in t:
        return "gross_margin_trend"
    if "opex" in t or "operating expenses" in t:
        return "opex_breakdown"
    if "ebitda" in t:
        return "ebitda_trend"
    # fallback
    return "help"

# -----------------------------
# Charting
# -----------------------------

def plot_revenue_vs_budget_bar(actual_usd: float, budget_usd: float, title: str = "Revenue vs Budget"):
    fig, ax = plt.subplots(figsize=(5,3))
    ax.bar(["Actual", "Budget"], [actual_usd, budget_usd])
    ax.set_ylabel("USD")
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    return fig

def plot_gm_trend_line(df: pd.DataFrame, title: str = "Gross Margin %"):
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(df["month"], df["gm_pct"] * 100, marker='o')
    ax.set_ylabel("GM %")
    ax.set_title(title)
    ax.set_ylim(0, 100)
    ax.grid(True, linestyle='--', alpha=0.3)
    for x, y in zip(df["month"], df["gm_pct"]*100):
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(0,6), ha='center', fontsize=8)
    return fig

def plot_opex_breakdown_bar(df: pd.DataFrame, title: str = "Opex Breakdown"):
    fig, ax = plt.subplots(figsize=(6,3))
    ax.bar(df["account_category"], df["usd"])
    ax.set_ylabel("USD")
    ax.set_title(title)
    ax.tick_params(axis='x', rotation=20)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    return fig

def plot_cash_trend(fin: FinanceData, months: int = 6, title: str = "Cash Trend"):
    last = sorted(fin.cash["month"].unique())[-months:]
    d = fin.cash[fin.cash["month"].isin(last)].copy()
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(d["month"], d["cash_usd"], marker='o')
    ax.set_ylabel("USD")
    ax.set_title(title)
    ax.grid(True, linestyle='--', alpha=0.3)
    return fig

# -----------------------------
# Orchestration
# -----------------------------

def respond(text: str, fin: FinanceData) -> tuple[str, plt.Figure | None]:
    intent = classify_intent(text)
    t = text.strip()
    fig = None

    if intent == "revenue_vs_budget":
        # month: try to extract, else use latest
        m = extract_month_from_text(t)
        if m is None or m.startswith("XXXX"):
            # default to latest; if 'XXXX-06' (for June w/o year), fill latest year
            if m and m.startswith("XXXX") and len(m) == 7:
                mon = m.split("-")[1]
                # find latest month in data that matches that month number
                months = sorted(fin.actuals["month"].unique())
                candidates = [x for x in months if x.endswith(f"-{mon}")]
                m = candidates[-1] if candidates else months[-1]
            else:
                m = latest_month(list(fin.actuals["month"].unique()))
        rvb = revenue_vs_budget_usd(fin, m)
        msg = (
            f"Revenue vs Budget for {rvb['month']}:\n"
            f"• Actual: ${rvb['actual_usd']:,.0f}\n"
            f"• Budget: ${rvb['budget_usd']:,.0f}\n"
            f"• Variance: ${rvb['variance_usd']:,.0f} ({rvb['variance_pct']*100:.1f}%)"
        )
        fig = plot_revenue_vs_budget_bar(rvb['actual_usd'], rvb['budget_usd'], title=f"Revenue vs Budget — {rvb['month']}")
        return msg, fig

    if intent == "gross_margin_trend":
        n = parse_last_n_months(t) or 3
        months = sorted(fin.actuals["month"].unique())[-n:]
        df = gross_margin_pct_trend(fin, months)
        msg_lines = [f"Gross Margin % (last {n} months):"]
        for _, row in df.iterrows():
            msg_lines.append(f"• {row['month']}: {row['gm_pct']*100:.1f}%")
        fig = plot_gm_trend_line(df, title=f"Gross Margin % — last {n} months")
        return "\n".join(msg_lines), fig

    if intent == "opex_breakdown":
        m = extract_month_from_text(t)
        if m is None or m.startswith("XXXX"):
            if m and m.startswith("XXXX") and len(m) == 7:
                mon = m.split("-")[1]
                months = sorted(fin.actuals["month"].unique())
                candidates = [x for x in months if x.endswith(f"-{mon}")]
                m = candidates[-1] if candidates else months[-1]
            else:
                m = latest_month(list(fin.actuals["month"].unique()))
        df = opex_breakdown_usd(fin, m)
        if df.empty:
            return f"No Opex data for {m}.", None
        msg = [f"Opex breakdown — {m}:"]
        for _, r in df.iterrows():
            msg.append(f"• {r['account_category'].split(':',1)[1]}: ${r['usd']:,.0f}")
        fig = plot_opex_breakdown_bar(df, title=f"Opex Breakdown — {m}")
        return "\n".join(msg), fig

    if intent == "cash_runway":
        cr = cash_runway_now(fin)
        runway_disp = '∞' if np.isinf(cr['runway_months']) else f"{cr['runway_months']:.1f} months"
        msg = (
            f"Cash runway as of {cr['as_of']}:\n"
            f"• Cash: ${cr['cash_usd']:,.0f}\n"
            f"• Avg net burn (last 3 mo): ${cr['avg_net_burn_usd']:,.0f}\n"
            f"• Runway: {runway_disp}\n"
            f"{cr['note']}"
        )
        fig = plot_cash_trend(fin, months=6, title="Cash Trend — last 6 months")
        return msg, fig

    if intent == "ebitda_trend":
        e = ebitda_by_month(fin)
        last6 = e.tail(6)
        msg = ["EBITDA (last 6 months):"]
        for _, r in last6.iterrows():
            msg.append(f"• {r['month']}: ${r['EBITDA']:,.0f}")
        # quick line chart
        fig, ax = plt.subplots(figsize=(6,3))
        ax.plot(last6["month"], last6["EBITDA"], marker='o')
        ax.set_title("EBITDA — last 6 months")
        ax.set_ylabel("USD")
        ax.grid(True, linestyle='--', alpha=0.3)
        return "\n".join(msg), fig

    # Help / default
    help_txt = (
        "I can answer questions like:\n"
        "• What was June 2025 revenue vs budget in USD?\n"
        "• Show Gross Margin % trend for the last 3 months.\n"
        "• Break down Opex by category for June 2025.\n"
        "• What is our cash runway right now?\n\n"
        "Try including a month (e.g., 'June 2025') or a relative window (e.g., 'last 3 months')."
    )
    return help_txt, None
