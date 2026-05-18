from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RuleMatch:
    rule_name: str
    matched: bool
    detail: str
    weight: int


@dataclass
class DetectionResult:
    template_id: Optional[str]
    confidence: float
    status: str  # matched, unknown, ambiguous
    matched_rules: List[RuleMatch] = field(default_factory=list)
    detector_version: str = "v1"