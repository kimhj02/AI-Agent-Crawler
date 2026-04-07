#!/usr/bin/env python3
"""식단표를 수집해 콘솔에 출력합니다."""

from __future__ import annotations

import pandas as pd

from crawler.kumoh_menu import URLS, load_menus


def main() -> None:
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    print("대상 식당:", ", ".join(URLS.keys()))
    menus = load_menus()

    for name, df in menus.items():
        print(f"\n=== {name} (shape={df.shape}) ===")
        print(df.to_string())
        print()

    missing = set(URLS) - set(menus)
    for name in missing:
        print(f"[{name}] 테이블 없음")


if __name__ == "__main__":
    main()
