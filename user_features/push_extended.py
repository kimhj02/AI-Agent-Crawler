#!/usr/bin/env python3
"""확장 페이로드(알레르기 필터·선택 i18n)를 Spring Boot로 POST합니다."""

from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd
import requests
from google import genai

import repo_env
from app.domain.crawler.kumoh_menu import load_menus
from app.domain.crawler.push_menus import post_menu_ingest
from user_features.i18n_summary import load_rows_from_analysis_csv, summarize_for_locale
from user_features.payloads import build_extended_menu_payload


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(
        description="급식 크롤 + (선택)분석 CSV로 확장 JSON POST",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SPRING_MENUS_URL", "").strip() or None,
        help="또는 SPRING_MENUS_URL",
    )
    parser.add_argument(
        "--analysis-csv",
        help="menu_allergy_gemini.csv — 있으면 avoidMenus 생성",
    )
    parser.add_argument(
        "--allergens",
        help="쉼표 구분 canonical/별칭 (예: 우유,대두)",
    )
    parser.add_argument(
        "--today-only-avoid",
        action="store_true",
        help="avoidMenus 를 오늘(서울) 요일 열만 필터",
    )
    parser.add_argument(
        "--with-i18n",
        action="store_true",
        help="Gemini로 i18nSummary 생성 후 페이로드에 포함",
    )
    parser.add_argument("--i18n-locale", default="en", help="BCP-47 태그")
    parser.add_argument(
        "--i18n-limit",
        type=int,
        default=25,
        help="i18n에 넣을 분석 행 상한",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force-empty",
        action="store_true",
        help="크롤 결과가 비어 있어도 POST 허용 (기본은 거부)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    menus = load_menus()
    if not menus and not args.dry_run and not args.force_empty:
        print(
            "경고: load_menus() 결과가 비었습니다. restaurants 없이 POST하지 않습니다. "
            "미리보기만 하려면 --dry-run, 빈 페이로드를 내려면 --force-empty",
            file=sys.stderr,
        )
        raise SystemExit(1)

    analysis_df = None
    if args.analysis_csv:
        analysis_df = pd.read_csv(args.analysis_csv, encoding="utf-8-sig")

    user_list: list[str] | None = None
    if args.allergens:
        user_list = [x.strip() for x in args.allergens.split(",") if x.strip()]

    i18n_block = None
    if args.with_i18n:
        if analysis_df is None:
            raise SystemExit("--with-i18n 은 --analysis-csv 가 필요합니다.")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit("GEMINI_API_KEY 가 필요합니다.")
        rows = load_rows_from_analysis_csv(args.analysis_csv, limit=args.i18n_limit)
        client = genai.Client(api_key=api_key)
        i18n_block = summarize_for_locale(client, args.model, rows, args.i18n_locale)

    payload = build_extended_menu_payload(
        menus,
        analysis_df=analysis_df,
        user_allergens_raw=user_list,
        today_only_avoid=args.today_only_avoid,
        i18n_summary=i18n_block,
    )

    if args.dry_run:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    if not args.url:
        raise SystemExit("--url 또는 SPRING_MENUS_URL 이 필요합니다.")

    token = os.environ.get("SPRING_API_TOKEN", "").strip() or None
    api_key_hdr = os.environ.get("SPRING_API_KEY", "").strip() or None

    try:
        res = post_menu_ingest(
            args.url,
            payload,
            bearer_token=token,
            api_key=api_key_hdr,
            timeout=args.timeout,
        )
    except requests.RequestException as e:
        print(f"요청 실패: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    print("HTTP", res.status_code)
    body = (res.text or "").strip()
    if not res.ok and body:
        print(body[:8000])
        if len(body) > 8000:
            print("... (응답 잘림)")

    if not res.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
