from typing import Any, Dict, List, Optional


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def majority(values: List[str], default: str = "auto") -> str:
    if not values:
        return default
    counts: Dict[str, int] = {}
    for item in values:
        counts[item] = counts.get(item, 0) + 1
    return max(counts.items(), key=lambda x: x[1])[0]
