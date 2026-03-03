# services/tax_engine.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


# ---- 2024 constants (Single) ----
STANDARD_DEDUCTION_SINGLE_2024 = 14600  # :contentReference[oaicite:1]{index=1}

# 2024 single filer tax brackets: (top_of_bracket, rate)
# :contentReference[oaicite:2]{index=2}
TAX_BRACKETS_SINGLE_2024 = [
    (11600, 0.10),
    (47150, 0.12),
    (100525, 0.22),
    (191950, 0.24),
    (243725, 0.32),
    (609350, 0.35),
    (float("inf"), 0.37),
]

SS_WAGE_BASE_2024 = 168600  # :contentReference[oaicite:3]{index=3}
# 12.4% SS + 2.9% Medicare :contentReference[oaicite:4]{index=4}
SE_TAX_RATE_TOTAL = 0.153
# net earnings factor :contentReference[oaicite:5]{index=5}
SE_EARNINGS_MULTIPLIER = 0.9235
ADD_MEDICARE_RATE = 0.009
ADD_MEDICARE_THRESHOLD_SINGLE = 200000  # :contentReference[oaicite:6]{index=6}


def _income_tax_from_brackets(taxable_income: float) -> float:
    if taxable_income <= 0:
        return 0.0

    tax = 0.0
    prev = 0.0
    for top, rate in TAX_BRACKETS_SINGLE_2024:
        amt = min(taxable_income, top) - prev
        if amt > 0:
            tax += amt * rate
        if taxable_income <= top:
            break
        prev = top
    return tax


def _self_employment_tax(net_profit: float) -> float:
    """
    SE tax computed on 92.35% of net profit (net earnings from self-employment).
    SS portion capped at wage base; Medicare portion uncapped; addl Medicare above threshold.
    """
    if net_profit <= 0:
        return 0.0

    # :contentReference[oaicite:7]{index=7}
    ne_se = net_profit * SE_EARNINGS_MULTIPLIER

    # Social Security (12.4%) up to wage base
    # :contentReference[oaicite:8]{index=8}
    ss_tax = min(ne_se, SS_WAGE_BASE_2024) * 0.124

    # Medicare (2.9%) on all net earnings
    medicare_tax = ne_se * 0.029

    # Additional Medicare (0.9%) above threshold
    addl = max(0.0, ne_se - ADD_MEDICARE_THRESHOLD_SINGLE) * \
        ADD_MEDICARE_RATE  # :contentReference[oaicite:9]{index=9}

    return ss_tax + medicare_tax + addl


def calculate_tax_estimate(
    income: float,
    expenses: List[Dict[str, Any]],
    filing_status: str = "single",
    home_office_sqft: Optional[float] = None,
    vehicle_business_use_percent: Optional[float] = None,
) -> Dict[str, Any]:
    """
    MVP deterministic estimate (federal, single, 2024):
    - Net profit = income - expenses
    - SE tax
    - SE tax deduction = 1/2 SE tax
    - QBI deduction = 20% of qualified business income (capped by taxable income before QBI)
    - Income tax using 2024 brackets
    """

    # Sum expenses + category totals
    deductions_by_category: Dict[str, float] = {}
    total_expenses = 0.0
    for e in (expenses or []):
        cat = str(e.get("category") or "general").lower()
        amt = float(e.get("amount") or 0.0)
        if amt < 0:
            amt = 0.0
        total_expenses += amt
        deductions_by_category[cat] = deductions_by_category.get(
            cat, 0.0) + amt

    total_income = float(income or 0.0)
    if total_income < 0:
        total_income = 0.0

    net_business_income = max(0.0, total_income - total_expenses)

    # SE tax + deduction
    se_tax = _self_employment_tax(net_business_income)
    se_tax_deduction = se_tax * 0.5

    # Taxable income before QBI:
    # net profit - half SE - standard deduction
    if filing_status != "single":
        # MVP: your app currently uses "single" everywhere; keep it strict
        filing_status = "single"

    taxable_before_qbi = net_business_income - se_tax_deduction - \
        STANDARD_DEDUCTION_SINGLE_2024  # :contentReference[oaicite:10]{index=10}
    taxable_before_qbi = max(0.0, taxable_before_qbi)

    # QBI: 20% of (net profit - half SE). Capped by taxable income before QBI (simplified MVP cap).
    qbi_base = max(0.0, net_business_income - se_tax_deduction)
    # basic cap concept :contentReference[oaicite:11]{index=11}
    qbi_deduction = min(0.20 * qbi_base, taxable_before_qbi)
    qbi_deduction = max(0.0, qbi_deduction)

    taxable_income = max(0.0, taxable_before_qbi - qbi_deduction)

    income_tax = _income_tax_from_brackets(taxable_income)
    total_tax = income_tax + se_tax

    return {
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        # MVP: treat all as allowed
        "allowed_expenses": round(total_expenses, 2),
        "net_business_income": round(net_business_income, 2),
        "se_tax_deduction": round(se_tax_deduction, 2),
        "qbi_deduction": round(qbi_deduction, 2),
        "taxable_income": round(taxable_income, 2),
        # ✅ key your UI reads
        "income_tax": round(income_tax, 2),
        "self_employment_tax": round(se_tax, 2),
        # ✅ key your UI reads
        "total_tax": round(total_tax, 2),
        "deductions_by_category": deductions_by_category,
    }
