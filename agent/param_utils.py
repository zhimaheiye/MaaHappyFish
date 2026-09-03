import json
from typing import Any, Optional


def parse_dict_param(raw: Any) -> dict:
    """
    Safely parse custom_action_param / custom_recognition_param into a dict.
    Covers None, empty string, 'null', '[]', 'true', malformed json, etc.
    Guaranteed to return a dict.
    """
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            val = json.loads(text)
        except Exception:
            return {}
        return val if isinstance(val, dict) else {}
    return {}


def safe_float(val: Any, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        res = float(val)
    except (TypeError, ValueError):
        res = default
    if min_val is not None:
        res = max(min_val, res)
    if max_val is not None:
        res = min(max_val, res)
    return res


def safe_int(val: Any, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        res = int(val)
    except (TypeError, ValueError):
        res = default
    if min_val is not None:
        res = max(min_val, res)
    if max_val is not None:
        res = min(max_val, res)
    return res
