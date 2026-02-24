from typing import List, Optional, Literal, Dict
from pydantic import BaseModel
from datetime import date

IncomeType = Literal["1099", "w2", "gig", "interest", "dividends", "other"]


class Period(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None


class IncomeSource(BaseModel):
    type: IncomeType = "other"
    description: Optional[str] = None
    amount: float = 0.0


class ExpenseItem(BaseModel):
    category: str
    amount: float = 0.0
    description: Optional[str] = None


class CalcAssumptions(BaseModel):
    assumed_marginal_rate: Optional[float] = None


class CalcEstimateRequest(BaseModel):
    conversation_id: Optional[str] = None
    income_sources: List[IncomeSource] = []
    expenses: List[ExpenseItem] = []
    assumptions: CalcAssumptions = CalcAssumptions()


class DeductionByCategory(BaseModel):
    category: str
    amount: float


class CalcEstimateResponse(BaseModel):
    total_income: float
    total_expenses: float
    net_business_income: float
    self_employment_tax: float
    income_tax_estimate: float
    total_estimated_tax: float
    assumed_marginal_rate: float
    deductions_by_category: List[DeductionByCategory]
    steps: List[str]
    assumptions_used: List[str]
    disclaimer: str


def _round2(x: float) -> float:
    return float(f"{x:.2f}")


def estimate_tax(req: CalcEstimateRequest) -> CalcEstimateResponse:
    # --- Split income types ---
    total_1099_income = sum(
        i.amount for i in req.income_sources if i.type in ["1099", "gig"])
    total_other_income = sum(
        i.amount for i in req.income_sources if i.type not in ["1099", "gig"])

    total_income = total_1099_income + total_other_income
    total_expenses = sum(e.amount for e in req.expenses)

    net_business_income = max(0.0, total_1099_income - total_expenses)

    # --- Self-employment tax (15.3%) ---
    # --- Self-employment tax (IRS method) ---
    # --- Self-employment tax (IRS method) ---
    SE_TAX_RATE = 0.153
    SE_TAX_BASE_FACTOR = 0.9235  # IRS rule: SE tax applies to 92.35% of net earnings

    se_tax_base = net_business_income * SE_TAX_BASE_FACTOR
    self_employment_tax = se_tax_base * SE_TAX_RATE

    # Half deductible
    deductible_half_se = self_employment_tax / 2

    # --- Income tax ---
    rate = 0.22
    assumptions_used: List[str] = []

    if req.assumptions and req.assumptions.assumed_marginal_rate is not None:
        rate = req.assumptions.assumed_marginal_rate
        assumptions_used.append(
            f"Used provided marginal rate: {int(rate*100)}%")
    else:
        assumptions_used.append("Assumed marginal income tax rate: 22%")

    adjusted_taxable_income = (
        net_business_income
        - deductible_half_se
        + total_other_income
    )

    income_tax_estimate = adjusted_taxable_income * rate
    total_estimated_tax = income_tax_estimate + self_employment_tax

    # --- Category grouping ---
    by_cat: Dict[str, float] = {}
    for e in req.expenses:
        cat = (e.category or "other").lower()
        by_cat[cat] = by_cat.get(cat, 0.0) + float(e.amount)

    deductions_by_category = [
        DeductionByCategory(category=k, amount=_round2(v))
        for k, v in sorted(by_cat.items())
    ]

    steps = [
        f"1099/Gig income = {total_1099_income:,.2f}",
        f"Other income = {total_other_income:,.2f}",
        f"Total expenses = {total_expenses:,.2f}",
        f"Net business income = {total_1099_income:,.2f} − {total_expenses:,.2f} = {net_business_income:,.2f}",
        f"Self-employment tax (15.3%) = {net_business_income:,.2f} × 15.3% = {self_employment_tax:,.2f}",
        f"Half of SE tax deductible = {deductible_half_se:,.2f}",
        f"Adjusted taxable income = {adjusted_taxable_income:,.2f}",
        f"Income tax ({int(rate*100)}%) = {income_tax_estimate:,.2f}",
        f"Total estimated tax = Income tax + SE tax = {total_estimated_tax:,.2f}",
    ]

    return CalcEstimateResponse(
        total_income=_round2(total_income),
        total_expenses=_round2(total_expenses),
        net_business_income=_round2(net_business_income),
        self_employment_tax=_round2(self_employment_tax),
        income_tax_estimate=_round2(income_tax_estimate),
        total_estimated_tax=_round2(total_estimated_tax),
        assumed_marginal_rate=_round2(rate),
        deductions_by_category=deductions_by_category,
        steps=steps,
        assumptions_used=assumptions_used,
        disclaimer="This provides general tax information, not personalized tax advice.",
    )
