"""분석 결과(CSV/데이터프레임)에서 사용자 알레르기에 해당하는 메뉴만 골라 냅니다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import repo_env
from user_features.allergen_catalog import (
    ALIAS_TO_CANONICAL,
    list_canonical_choices,
    normalize_user_allergen_tokens,
)


def detected_labels_from_summary(summary: str | None) -> list[str]:
    """알레르기_요약 문자열에서 '식품' 라벨 목록 추출."""
    if summary is None:
        return []
    s = str(summary).strip()
    if not s or s.lower() == "nan":
        return []
    parts = re.split(r"\s*/\s*", s)
    labels: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        for sep in (" — ", " - ", "—"):
            if sep in p:
                p = p.split(sep, 1)[0].strip()
                break
        if p:
            labels.append(p)
    return labels


def detected_label_to_canonical(label: str) -> str | None:
    """요약에서 뽑힌 식품 라벨(한 덩어리)을 canonical로만 매핑. 부분 문자열 매칭 없음.

    '콩'→대두, '땅콩'→땅콩처럼 표에 등록된 동의어 **전체 일치**만 인정.
    """
    d = label.strip()
    if not d:
        return None
    return ALIAS_TO_CANONICAL.get(d)


def matched_user_allergens(user_canonical: set[str], summary: str) -> list[str]:
    """요약문에 나타난 식품 라벨이 사용자 선택 알레르기와 겹치는 canonical 목록."""
    raw_labels = detected_labels_from_summary(summary)
    detected_canonical: set[str] = set()
    for d in raw_labels:
        c = detected_label_to_canonical(d)
        if c:
            detected_canonical.add(c)

    hit: list[str] = []
    for uc in user_canonical:
        if uc in detected_canonical:
            hit.append(uc)
    return hit


def seoul_weekday_char() -> str:
    order = "월화수목금토일"
    wd = datetime.now(ZoneInfo("Asia/Seoul")).weekday()
    return order[wd]


def filter_avoid_dataframe(
    df: pd.DataFrame,
    user_allergens: set[str],
    *,
    today_only: bool = False,
) -> pd.DataFrame:
    if "알레르기_요약" not in df.columns:
        raise ValueError("데이터에 '알레르기_요약' 열이 필요합니다 (menu_allergy CSV 등).")

    work = df.copy()
    if today_only and "요일열" in work.columns:
        prefix = seoul_weekday_char()
        col = work["요일열"].astype(str)
        work = work[col.str.startswith(prefix)]

    rows: list[dict] = []
    for _, row in work.iterrows():
        summary = row.get("알레르기_요약", "")
        if pd.isna(summary):
            summary = ""
        matched = matched_user_allergens(user_allergens, str(summary))
        if not matched:
            continue
        d = row.to_dict()
        d["matchedAllergensKo"] = matched
        rows.append(d)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _nullable_cell(val: object) -> str | None:
    """DataFrame 셀 값 → JSON 직렬화용: NaN/NA 는 None."""
    if val is None or pd.isna(val):
        return None
    return str(val)


def _matched_allergens_primitives(matched: object) -> list[str]:
    """matchedAllergensKo → NaN 없는 str 리스트."""
    if matched is None or (isinstance(matched, float) and pd.isna(matched)):
        return []
    if isinstance(matched, str):
        return [matched] if matched else []
    out: list[str] = []
    for item in list(matched):
        if pd.isna(item):
            continue
        out.append(str(item))
    return out


def avoid_menus_for_api_payload(df_avoid: pd.DataFrame) -> list[dict[str, object]]:
    """Spring 등 REST용 영문 키 목록."""
    out: list[dict[str, object]] = []
    for _, row in df_avoid.iterrows():
        raw_row_index = row.get("표행")
        table_row = int(raw_row_index) if pd.notna(raw_row_index) else None
        out.append(
            {
                "restaurant": _nullable_cell(row.get("식당")),
                "dayColumn": _nullable_cell(row.get("요일열")),
                "tableRow": table_row,
                "menuText": _nullable_cell(row.get("메뉴텍스트")),
                "matchedAllergensKo": _matched_allergens_primitives(
                    row.get("matchedAllergensKo", [])
                ),
                "allergySummaryKo": _nullable_cell(row.get("알레르기_요약")),
            }
        )
    return out


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(
        description="사용자 알레르기 기준 '피해야 할 메뉴' 목록 (분석 CSV 필요)",
    )
    parser.add_argument(
        "--csv",
        help="menu_allergy_gemini.csv 등 (알레르기_요약 열 포함). --list-allergens 시 생략 가능",
    )
    parser.add_argument(
        "--allergens",
        help="쉼표로 구분 (예: 우유,대두,난류). 생략 시 --list-allergens만",
    )
    parser.add_argument(
        "--today-only",
        action="store_true",
        help="한국(서울) 기준 오늘 요일 열만 (요일열이 월·화… 로 시작)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="표준출력에 JSON(avoidMenus API 형태)으로 출력",
    )
    parser.add_argument(
        "--list-allergens",
        action="store_true",
        help="canonical 알레르기 목록 출력 후 종료",
    )
    args = parser.parse_args()

    if args.list_allergens:
        print(", ".join(list_canonical_choices()))
        return

    if not args.csv:
        print("--csv 가 필요합니다.", file=sys.stderr)
        raise SystemExit(2)

    if not args.allergens:
        print("--allergens 가 필요합니다 (또는 --list-allergens).", file=sys.stderr)
        raise SystemExit(2)

    raw_tokens = [x.strip() for x in args.allergens.split(",")]
    user_set = normalize_user_allergen_tokens(raw_tokens)

    try:
        df = pd.read_csv(args.csv, encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"CSV 파일을 찾을 수 없습니다: {args.csv}", file=sys.stderr)
        raise SystemExit(2) from None
    except pd.errors.ParserError as e:
        print(f"CSV 형식을 해석하지 못했습니다: {args.csv}\n{e}", file=sys.stderr)
        raise SystemExit(2) from e
    except Exception as e:
        print(
            f"CSV를 읽는 중 오류가 발생했습니다: {args.csv} ({type(e).__name__})",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    try:
        avoid_df = filter_avoid_dataframe(df, user_set, today_only=args.today_only)
    except ValueError as e:
        print(
            f"알레르기 필터를 적용할 수 없습니다: {args.csv}\n"
            f"({e})",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    if args.json:
        payload = {
            "userAllergensKo": sorted(user_set),
            "avoidMenus": avoid_menus_for_api_payload(avoid_df),
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    if avoid_df.empty:
        print("조건에 해당하는 메뉴가 없습니다.")
        return

    pd.set_option("display.max_colwidth", 60)
    show = avoid_df[
        [c for c in ["식당", "요일열", "메뉴텍스트", "matchedAllergensKo", "알레르기_요약"] if c in avoid_df.columns]
    ]
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
