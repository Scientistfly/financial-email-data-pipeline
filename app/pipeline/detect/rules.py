import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class Rule:
    name: str
    weight: int
    func: Callable[[str], bool]
    detail: str


def contains_phrase_rule(name: str, phrase: str, weight: int) -> Rule:
    phrase_lower = phrase.lower()

    def _check(text: str) -> bool:
        return phrase_lower in text.lower()

    return Rule(
        name=name,
        weight=weight,
        func=_check,
        detail=f"contains '{phrase}'"
    )


def regex_rule(name: str, pattern: str, weight: int) -> Rule:
    compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

    def _check(text: str) -> bool:
        return bool(compiled.search(text))

    return Rule(
        name=name,
        weight=weight,
        func=_check,
        detail=f"regex '{pattern}'"
    )


def contains_all_rule(name: str, keywords: list[str], weight: int) -> Rule:
    keywords_lower = [k.lower() for k in keywords]

    def _check(text: str) -> bool:
        text_lower = text.lower()
        return all(k in text_lower for k in keywords_lower)

    return Rule(
        name=name,
        weight=weight,
        func=_check,
        detail=f"contains all {keywords}"
    )