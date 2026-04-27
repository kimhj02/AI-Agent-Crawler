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
from app.domain.crawler.kumoh_menu import load_menus

SYSTEM_INSTRUCTION = """당신은 한국 대학 급식 메뉴 문구를 분석하는 조력자입니다."""
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
                out.append({"식당": place, "요일열": col, "표행": int(idx), "메뉴텍스트": s})
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
        prompt = f"입력:\n{user_payload}\n출력은 JSON 배열만."
        resp = None
        last_err: BaseException | None = None
        for attempt in range(max_retries):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[SYSTEM_INSTRUCTION, prompt],
                    config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=8192),
                )
                break
            except google_api_exceptions.ResourceExhausted as e:
                last_err = e
                time.sleep(sleep_between_batches_sec * (attempt + 1))
        if resp is None:
            if last_err is not None:
                raise last_err
            raise RuntimeError("Gemini 호출 재시도 횟수가 0이거나 응답 생성에 실패했습니다.")
        raw = (getattr(resp, "text", "") or "").strip()
        if not raw:
            raise RuntimeError("Gemini 응답이 비었습니다.")
        parsed = extract_json_array(raw)
        for j, e in enumerate(chunk):
            if j < len(parsed) and isinstance(parsed[j], dict):
                row = dict(e)
                for k, v in parsed[j].items():
                    if k not in _MENU_ENTRY_IDENTITY_KEYS:
                        row[k] = v
                row.setdefault("추정_재료", [])
                row.setdefault("알레르기_유발가능", [])
                all_results.append(row)
            else:
                all_results.append({**e, "추정_재료": [], "알레르기_유발가능": [], "오류": "모델 응답 누락/형식 오류"})
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
                "추정_재료": ", ".join(ingredients) if isinstance(ingredients, list) else str(ingredients),
                "알레르기_요약": " / ".join(
                    f"{a.get('식품', a)} — {a.get('근거', '')}" if isinstance(a, dict) else str(a)
                    for a in (allergies or [])
                ),
            }
        )
    return pd.DataFrame(flat_rows)


def main() -> None:
    repo_env.load_dotenv_from_repo_root()
    parser = argparse.ArgumentParser(description="Gemini로 급식 메뉴 알레르기·재료 추정")
    parser.add_argument("-o", "--output", default="menu_allergy_gemini.csv")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"))
    args = parser.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다.")
    client = genai.Client(api_key=api_key)
    menus = load_menus()
    entries = iter_menu_entries(menus)
    if not entries:
        raise SystemExit("분석할 메뉴가 없습니다.")
    results = analyze_menus_with_gemini(client, args.model, entries)
    summary_df = results_to_dataframe(results)
    summary_df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print("저장:", args.output)


if __name__ == "__main__":
    main()
