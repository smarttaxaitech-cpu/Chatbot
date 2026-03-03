import re
from typing import Dict, Tuple


def tag_question(text: str) -> Dict[str, str]:
    t = (text or "").lower()

    # -------- CATEGORY TAGGING --------
    if any(k in t for k in ["1099", "1099-nec", "w-9", "contractor"]):
        category = "contractors"

    elif any(k in t for k in ["schedule c", "form 1040", "form 1065", "tax form"]):
        category = "forms"

    elif any(k in t for k in [
        "estimated tax",
        "estimated taxes",
        "quarterly",
        "quarterly estimated"
    ]):
        category = "quarterly_tax"

    elif any(k in t for k in ["w-2 vs 1099", "income reporting", "report income"]):
        category = "income_reporting"

    elif any(k in t for k in ["mileage", "gas", "car", "vehicle", "uber", "lyft"]):
        category = "vehicle"

    elif any(k in t for k in ["home office", "rent", "sqft", "utilities"]):
        category = "home_office"

    elif any(k in t for k in ["meal", "meals", "lunch", "dinner", "coffee"]):
        category = "meals"

    elif any(k in t for k in ["hotel", "flight", "airfare", "conference", "travel"]):
        category = "travel"

    elif any(k in t for k in ["laptop", "computer", "camera", "equipment", "phone", "monitor"]):
        category = "equipment"

    elif any(k in t for k in ["software", "subscription", "adobe", "saas", "hosting"]):
        category = "software"

    else:
        category = "general"

    # -------- SPENDING TIMING --------
    before = any(k in t for k in [
        "thinking of", "planning to", "before i buy",
        "should i buy", "can i buy", "about to purchase"
    ])

    after = any(k in t for k in [
        "i bought", "i purchased", "i paid",
        "already paid", "last month", "yesterday",
        "spent", "charged"
    ])

    if before and not after:
        timing = "before_spending"
    elif after and not before:
        timing = "after_spending"
    else:
        timing = "unclear"

    return {"category_tag": category, "spending_timing": timing}


def needs_clarification(message: str) -> bool:
    if not message:
        return False

    m = message.lower().strip()

    # If very short and contains vague pronoun
    if len(m.split()) <= 6 and re.search(r"\b(it|this|that)\b", m):
        return True

    # Direct vague phrases
    vague_phrases = [
        "is it deductible",
        "can i deduct it",
        "can i deduct this",
        "can i deduct that",
        "is this deductible",
        "is that deductible",
    ]

    if any(p in m for p in vague_phrases):
        return True

    return False


def build_clarifying_question(text: str) -> str:
    t = (text or "").lower()

    if any(x in t for x in ["laptop", "phone", "camera", "equipment"]):
        return "Quick question: is it used 100% for business, or mixed business + personal use?"
    if any(x in t for x in ["car", "vehicle", "gas", "mileage", "uber", "lyft"]):
        return "Quick question: is this for business travel (client/work trips) or regular commuting from home to a main workplace?"
    if any(x in t for x in ["rent", "home office", "utilities"]):
        return "Quick question: do you use a specific area of your home exclusively and regularly for business?"
    if any(x in t for x in ["meal", "meals", "coffee"]):
        return "Quick question: was this meal with a current/potential business contact, and were you (or an employee) present?"

    return "Quick question: is this expense strictly for business, or mixed business + personal use?"
