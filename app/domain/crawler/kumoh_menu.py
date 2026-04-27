"""금오공대 식당 급식표 HTML에서 메뉴 테이블을 가져옵니다."""

from __future__ import annotations

import logging
from io import StringIO

import pandas as pd
import requests
from pandas.errors import ParserError

logger = logging.getLogger(__name__)

URLS = {
    "학생식당": "https://www.kumoh.ac.kr/ko/restaurant01.do",
    "교직원식당": "https://www.kumoh.ac.kr/ko/restaurant02.do",
    "분식당": "https://www.kumoh.ac.kr/ko/restaurant04.do",
}


def fetch_html(url: str) -> str:
    res = requests.get(url, timeout=15)
    res.raise_for_status()
    res.encoding = "utf-8"
    return res.text


def load_menus() -> dict[str, pd.DataFrame]:
    menus: dict[str, pd.DataFrame] = {}
    for name, url in URLS.items():
        try:
            html = fetch_html(url)
            try:
                tables = pd.read_html(StringIO(html))
            except ValueError:
                continue
            if not tables:
                continue
            df = tables[0].copy()
            df.columns = [str(c).strip() for c in df.columns]
            df = df.replace(r"\s+", " ", regex=True)
            menus[name] = df
        except (
            requests.exceptions.RequestException,
            ParserError,
            ValueError,
            UnicodeError,
            OSError,
        ) as e:
            logger.warning("[%s] 메뉴 로드 실패: %s", name, type(e).__name__)
            continue
    return menus
