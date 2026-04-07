#!/usr/bin/env python3
"""Gemini로 급식 메뉴 셀별 추정 재료·알레르기 정보를 생성합니다."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any

import pandas as pd
from google import genai
from google.api_core import exceptions as google_api_exceptions
from google.genai import types

import repo_env
from crawler.kumoh_menu import load_menus

SYSTEM_INSTRUCTION = """당신은 한국 대학 급식 메뉴 문구를 분석하는 조력자입니다.
메뉴 이름·반찬 나열에서 **추정되는 재료**와 **알레르기 유발 가능이 있는 식품**을 정리합니다.

규칙:
- 반드시 **한국어**로 답합니다.
- 메뉴 문구만 보고 **추정**이며, 확정이 아님을 전제로 합니다.
- 알레르기는 식약처 고시 **알레르기 유발 식품 표시 대상**(난류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 아황산류, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣 등) 중 **해당될 가능성이 있는 것**을 골라 이유를 짧게 씁니다.
- 없으면 빈 배열로 둡니다.
- 응답은 **JSON만** 출력합니다. 마크다운 코드블록 금지."""

# 입력 청크의 식별 필드 — 모델이 잘못 복사해도 덮어쓰지 않음
_MENU_ENTRY_IDENTITY_KEYS = frozenset({"식당", "요일열", "표행", "메뉴텍스트"})


def iter_menu_entries(menus: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for place, df in menus.items():
        for col in df.columns:
            for idx, val in df[col].items():
                if val is None or pd.isna(val):
                    continue
                s = str(val).strip()
                if not s or "운영 없음" in s:
                    continue
                out.append(
                    {
                        "식당": place,
                        "요일열": col,
                        "표행": int(idx),
                        "메뉴텍스트": s,
                    }
                )
    return out


def extract_json_array(text: str) -> list:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise ValueError(f"JSON 배열을 찾을 수 없습니다: {text[:200]}...")
    return json.loads(m.group())


def analyze_menus_with_gemini(
    client: genai.Client,
    model_name: str,
    entries: list[dict],
    batch_size: int = 4,
    sleep_between_batches_sec: float = 21.0,
    max_retries: int = 5,
) -> list[dict]:
    all_results: list[dict] = []
    for i in range(0, len(entries), batch_size):
        chunk = entries[i : i + batch_size]
        user_payload = json.dumps(chunk, ensure_ascii=False)
        prompt = f"""다음은 급식표에서 뽑은 객체 배열입니다. 각 항목에 대해 분석해 주세요.

입력:
{user_payload}

출력 형식: **JSON 배열** 하나만. 각 원소는 입력 순서와 동일하게 다음 키를 가집니다.
- "식당", "요일열", "표행", "메뉴텍스트" (입력과 동일하게 복사)
- "추정_재료": 문자열 배열 (예: ["쌀", "닭고기", ...])
- "알레르기_유발가능": 배열. 각 원소는 {{"식품": "...", "근거": "메뉴 문구에서 ... 때문에"}} 형태

다른 설명 없이 JSON 배열만 출력하세요."""

        resp = None
        last_err: BaseException | None = None
        for attempt in range(max_retries):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[SYSTEM_INSTRUCTION, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                break
            except google_api_exceptions.ResourceExhausted as e:
                last_err = e
                wait = sleep_between_batches_sec * (attempt + 1)
                print(
                    f"429 할당량/속도 제한 — {wait:.0f}초 대기 후 재시도 ({attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
        if resp is None:
            raise last_err  # type: ignore[misc]

        raw = (getattr(resp, "text", "") or "").strip()
        if not raw:
            raise RuntimeError(
                "Gemini 응답이 비었습니다. finish_reason 또는 안전 필터를 확인하세요."
            )
        parsed = extract_json_array(raw)
        if len(parsed) != len(chunk):
            print(
                f"경고: 배치 {i // batch_size}에서 개수 불일치 (기대 {len(chunk)}, 실제 {len(parsed)})"
            )
        for j, e in enumerate(chunk):
            if j < len(parsed):
                p = parsed[j]
                if not isinstance(p, dict):
                    all_results.append(
                        {
                            **e,
                            "추정_재료": [],
                            "알레르기_유발가능": [],
                            "오류": "모델 응답 항목 형식 오류",
                        }
                    )
                    continue
                row = dict(e)
                for k, v in p.items():
                    if k not in _MENU_ENTRY_IDENTITY_KEYS:
                        row[k] = v
                row.setdefault("추정_재료", [])
                row.setdefault("알레르기_유발가능", [])
                all_results.append(row)
            else:
                all_results.append(
                    {
                        **e,
                        "추정_재료": [],
                        "알레르기_유발가능": [],
                        "오류": "모델 응답에서 해당 항목 누락",
                    }
                )
        if i + batch_size < len(entries):
            time.sleep(sleep_between_batches_sec)
    return all_results


def results_to_dataframe(results: list[dict]) -> pd.DataFrame:
    flat_rows = []
    for r in results:
        ingredients = r.get("추정_재료", [])
        allergies = r.get("알레르기_유발가능", [])
        flat_rows.append(
            {
                "식당": r.get("식당"),
                "요일열": r.get("요일열"),
                "표행": r.get("표행"),
                "메뉴텍스트": r.get("메뉴텍스트"),
                "추정_재료": ", ".join(ingredients)
                if isinstance(ingredients, list)
                else str(ingredients),
                "알레르기_요약": " / ".join(
                    f"{a.get('식품', a)} — {a.get('근거', '')}"
                    if isinstance(a, dict)
                    else str(a)
                    for a in (allergies or [])
                ),
            }
        )
    return pd.DataFrame(flat_rows)


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(description="Gemini로 급식 메뉴 알레르기·재료 추정")
    parser.add_argument(
        "-o",
        "--output",
        default="menu_allergy_gemini.csv",
        help="결과 CSV 경로",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="분석할 메뉴 셀 상한 (테스트용)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="한 번에 Gemini에 보낼 항목 수",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=21.0,
        help="배치 사이 대기(초)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        help="모델명 (기본: 환경변수 GEMINI_MODEL 또는 gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--print-preview",
        action="store_true",
        help="요약 DataFrame 일부를 콘솔에 출력",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit(
            "환경변수 GEMINI_API_KEY가 없습니다. "
            ".env 파일(cp .env.example .env) 또는 export GEMINI_API_KEY='...' 로 설정하세요."
        )

    print("사용 모델:", args.model)
    client = genai.Client(api_key=api_key)

    menus = load_menus()
    for k, v in menus.items():
        print(k, v.shape)

    entries = iter_menu_entries(menus)
    if args.limit is not None:
        entries = entries[: args.limit]
    print("분석 대상 셀 수:", len(entries))
    if not entries:
        raise SystemExit("분석할 메뉴가 없습니다.")

    results = analyze_menus_with_gemini(
        client,
        args.model,
        entries,
        batch_size=args.batch_size,
        sleep_between_batches_sec=args.sleep,
    )
    summary_df = results_to_dataframe(results)
    summary_df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print("저장:", args.output)

    if args.print_preview:
        pd.set_option("display.max_colwidth", 80)
        print(summary_df.head(20).to_string())


if __name__ == "__main__":
    main()
