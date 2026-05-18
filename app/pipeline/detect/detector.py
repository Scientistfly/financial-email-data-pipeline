from .schemas import DetectionResult, RuleMatch
from .templates import TEMPLATES, TemplateDefinition


DETECTOR_VERSION = "v1"


def score_template(text: str, template: TemplateDefinition):
    matched_rules: list[RuleMatch] = []
    score = 0

    # Required rules
    for rule in template.required_rules:
        matched = rule.func(text)
        matched_rules.append(
            RuleMatch(
                rule_name=rule.name,
                matched=matched,
                detail=rule.detail,
                weight=rule.weight if matched else 0,
            )
        )
        if not matched:
            return None
        score += rule.weight

    # Optional rules
    for rule in template.optional_rules:
        matched = rule.func(text)
        matched_rules.append(
            RuleMatch(
                rule_name=rule.name,
                matched=matched,
                detail=rule.detail,
                weight=rule.weight if matched else 0,
            )
        )
        if matched:
            score += rule.weight

    # Negative rules
    for rule in template.negative_rules:
        matched = rule.func(text)
        matched_rules.append(
            RuleMatch(
                rule_name=rule.name,
                matched=matched,
                detail=rule.detail,
                weight=-rule.weight if matched else 0,
            )
        )
        if matched:
            score -= rule.weight

    if score < template.min_score:
        return None

    return {
        "template_id": template.template_id,
        "score": score,
        "matched_rules": matched_rules,
    }


def detect_template(text: str) -> DetectionResult:
    candidates = []

    for template in TEMPLATES:
        result = score_template(text, template)
        if result is not None:
            candidates.append(result)

    if not candidates:
        return DetectionResult(
            template_id=None,
            confidence=0.0,
            status="unknown",
            matched_rules=[],
            detector_version=DETECTOR_VERSION,
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)

    best = candidates[0]

    if len(candidates) > 1:
        second = candidates[1]
        if best["score"] - second["score"] <= 1:
            return DetectionResult(
                template_id=best["template_id"],
                confidence=round(best["score"] / 12, 2),
                status="ambiguous",
                matched_rules=best["matched_rules"],
                detector_version=DETECTOR_VERSION,
            )

    return DetectionResult(
        template_id=best["template_id"],
        confidence=min(round(best["score"] / 12, 2), 1.0),
        status="matched",
        matched_rules=best["matched_rules"],
        detector_version=DETECTOR_VERSION,
    )