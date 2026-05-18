from difflib import SequenceMatcher


def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()