"""모델 응답 문자열에서 JSON 객체를 추출하는 공통 유틸."""

from __future__ import annotations

import json
from typing import Any, Type


def extract_json_object(
    text: str,
    *,
    exception_cls: Type[Exception] = ValueError,
    not_found_message: str | None = None,
    not_object_message: str | None = None,
) -> dict[str, Any]:
    raw = text.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        msg = not_found_message or f"JSON 객체를 찾지 못했습니다: {raw[:200]}..."
        raise exception_cls(msg)
    obj = json.loads(raw[start : end + 1])
    if not isinstance(obj, dict):
        msg = not_object_message or "JSON 객체 형식이 아닙니다."
        raise exception_cls(msg)
    return obj

