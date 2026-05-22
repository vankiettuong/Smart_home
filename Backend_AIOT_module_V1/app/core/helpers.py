from typing import Any, Dict, List, Optional


def maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def maybe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def majority(values: List[str]) -> Optional[str]:
    if not values:
        return None
    counts: Dict[str, int] = {}
    for item in values:
        counts[item] = counts.get(item, 0) + 1
    return max(counts.items(), key=lambda x: x[1])[0]
