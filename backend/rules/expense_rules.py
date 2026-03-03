from typing import List, Tuple, Dict


def apply_deduction_rules(
    RULES: dict,
    expenses: List[dict],
    home_office_sqft: int | None = None,
    vehicle_business_use_percent: float | None = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Applies IRS deduction rules deterministically.
    Returns:
        total_allowed_expenses,
        breakdown_by_category
    """

    deduction_rules = RULES.get("deduction_rules", {})

    total_allowed = 0.0
    breakdown = {}

    for item in expenses:
        category = item.get("category")
        amount = float(item.get("amount", 0))

        if amount <= 0 and category != "home_office_simplified":
            continue

        # If category not in rules → ignore or treat as 0
        if category not in deduction_rules:
            continue

        rule = deduction_rules[category]

        allowed_amount = 0.0

        # 🔹 Percentage-based deductions (meals, software, etc.)
        if "deductible_percent" in rule:
            allowed_amount = amount * rule["deductible_percent"]

        # 🔹 Home office simplified method
        elif category == "home_office_simplified":
            if home_office_sqft:
                max_sqft = rule["max_sqft"]
                rate = rule["rate_per_sqft"]
                allowed_sqft = min(home_office_sqft, max_sqft)
                allowed_amount = allowed_sqft * rate

        # 🔹 Vehicle business use
        elif category == "vehicle":
            if vehicle_business_use_percent:
                allowed_amount = amount * vehicle_business_use_percent

        # Add to totals
        total_allowed += allowed_amount
        breakdown[category] = round(allowed_amount, 2)

    return round(total_allowed, 2), breakdown
