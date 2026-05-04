"""Spring API 연동 Repository."""

from __future__ import annotations

from typing import Any

import requests

from app.common.service_ops import post_json


class SpringRepository:
    """Spring API 연동 Repository."""

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        token: str | None,
        api_key: str | None,
    ) -> requests.Response:
        return post_json(url=url, payload=payload, token=token, api_key=api_key)
