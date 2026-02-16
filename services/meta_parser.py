import json


def _is_purchase_action(action_type: str) -> bool:
    """
    Meta API action_type이 '구매'에 해당하는지.
    omni_purchase만 사용 (픽셀 + 오프라인 통합 구매)
    """
    if not action_type:
        return False
    at = (action_type or "").strip().lower()
    return at == "omni_purchase"


def parse_meta_actions(actions_raw) -> float:
    """Meta API actions 필드에서 구매 전환 수만 합계."""
    if not actions_raw:
        return 0.0
    try:
        data = actions_raw if isinstance(actions_raw, list) else json.loads(actions_raw)
        total = 0.0
        for item in data:
            at = item.get("action_type") or ""
            if _is_purchase_action(at):
                total += float(item.get("value") or 0)
        return total
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def parse_meta_action_values(action_values_raw) -> float:
    """Meta API action_values 필드에서 구매 전환 금액만 합계."""
    if not action_values_raw:
        return 0.0
    try:
        data = action_values_raw if isinstance(action_values_raw, list) else json.loads(action_values_raw)
        total = 0.0
        for item in data:
            at = item.get("action_type") or ""
            if _is_purchase_action(at):
                total += float(item.get("value") or 0)
        return total
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0
