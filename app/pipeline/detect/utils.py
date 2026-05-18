# app/pipeline/detect/utils.py

def serialize_rule_matches(rule_matches: list) -> list[dict]:
    return [
        {
            "rule_name": r.rule_name,
            "matched": r.matched,
            "detail": r.detail,
            "weight": r.weight,
        }
        for r in rule_matches
    ]