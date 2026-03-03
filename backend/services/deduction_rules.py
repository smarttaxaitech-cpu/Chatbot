# services/deduction_rules.py

from typing import Dict, Optional

MEALS_DEDUCTIBLE_PERCENT = 0.50  # 50% rule (post-2022 standard rule)
HOME_OFFICE_SIMPLIFIED_RATE = 5  # $5 per sqft (simplified method)
MAX_HOME_OFFICE_SQFT = 300       # IRS cap


def evaluate_deductibility(category: str, amount: float, business_use_percent: Optional[float] = None) -> Dict:
    """
    Deterministic MVP deductibility engine.
    Returns structured result.
    """

    category = (category or "").lower()
    amount = float(amount or 0)

    if category == "equipment":
        if business_use_percent is None:
            return {
                "deductible": "depends",
                "rule": "Equipment is deductible based on business-use percentage.",
                "estimated_deduction": None,
                "confidence": "medium"
            }

        deduction = amount * (business_use_percent / 100)
        return {
            "deductible": "partially",
            "rule": "Business equipment is deductible proportional to business use.",
            "estimated_deduction": round(deduction, 2),
            "confidence": "high"
        }

    if category == "software":
        if business_use_percent is None:
            business_use_percent = 100

        deduction = amount * (business_use_percent / 100)
        return {
            "deductible": "fully" if business_use_percent == 100 else "partially",
            "rule": "Software subscriptions used for business are deductible.",
            "estimated_deduction": round(deduction, 2),
            "confidence": "high"
        }

    if category == "meals":
        deduction = amount * MEALS_DEDUCTIBLE_PERCENT
        return {
            "deductible": "partially",
            "rule": "Business meals are generally 50% deductible.",
            "estimated_deduction": round(deduction, 2),
            "confidence": "high"
        }

    if category == "home_office":
        return {
            "deductible": "depends",
            "rule": "Home office must be used exclusively and regularly for business.",
            "estimated_deduction": None,
            "confidence": "medium"
        }

    if category == "vehicle":
        return {
            "deductible": "depends",
            "rule": "Vehicle expenses deductible for business use only (not commuting).",
            "estimated_deduction": None,
            "confidence": "medium"
        }

    if category == "travel":
        return {
            "deductible": "fully",
            "rule": "Ordinary and necessary business travel expenses are deductible.",
            "estimated_deduction": round(amount, 2),
            "confidence": "high"
        }

    return {
        "deductible": "unknown",
        "rule": "Category not clearly classified.",
        "estimated_deduction": None,
        "confidence": "low"
    }
