from app.models import MerchantAlias
from sqlalchemy.orm import Session


def normalize_merchant(db: Session, household_id, raw_text: str):
    """
    Check if merchant has a learned alias.
    """

    alias = db.query(MerchantAlias).filter(
        MerchantAlias.household_id == household_id,
        MerchantAlias.raw_text == raw_text
    ).first()

    if alias:
        return alias.normalized_name, alias.default_category, 0.95

    return raw_text, None, 0.5


def classify_transaction(db: Session, household_id, parsed: dict):
    """
    Adaptive household classification engine.
    """

    if parsed["type"] != "transaction":
        return parsed

    raw_merchant = parsed.get("merchant_raw")
    description = parsed.get("metadata", {}).get("source", "")

    # 1️⃣ Normalize merchant
    merchant, learned_category, confidence = normalize_merchant(
        db, household_id, raw_merchant
    )

    # 2️⃣ If household already taught us category
    if learned_category:
        category = learned_category
        subcategory = None
        confidence = 0.95

    else:
        # 3️⃣ Rule-based fallback logic

        merchant_upper = (merchant or "").upper()

        # SAVINGS
        if parsed["transaction_type"] == "savings":
            category = "Savings"
            subcategory = "Transfer to Savings"
            confidence = 0.9

        # INTERNAL TRANSFER
        elif parsed["transaction_type"] == "transfer":
            category = "Internal"
            subcategory = "Family Transfer"
            confidence = 0.8

        # CREDIT CARD PAYMENT
        elif parsed["transaction_type"] == "payment":
            category = "Internal"
            subcategory = "Credit Card Payment"
            confidence = 0.9

        # RESTAURANTS
        elif "PEDIDOSYA" in merchant_upper:
            category = "Lifestyle"
            subcategory = "Restaurant"
            confidence = 0.85

        # UTILITIES
        elif "ELECTRICAS" in merchant_upper:
            category = "Needs"
            subcategory = "Utilities"
            confidence = 0.85

        # CASH ADVANCE
        elif "EFECTIVO" in merchant_upper:
            category = "Lifestyle"
            subcategory = "Cash Advance"
            confidence = 0.7

        # DEFAULT EXPENSE
        elif parsed["transaction_type"] == "expense":
            category = "Needs"
            subcategory = "General Expense"
            confidence = 0.6

        else:
            category = "Uncategorized"
            subcategory = None
            confidence = 0.5

    parsed["merchant_normalized"] = merchant
    parsed["category"] = category
    parsed["subcategory"] = subcategory
    parsed["confidence"] = confidence

    return parsed