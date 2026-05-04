"""Uvicorn 진입점.

    uvicorn main:app --host 0.0.0.0 --port 8000

기존 `user_features.live_service:app`와 동일한 앱 인스턴스를 노출합니다.
"""

from __future__ import annotations

from user_features.live_service import app

__all__ = ["app"]
