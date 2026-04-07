"""메뉴·알레르기 요약을 외국인용 로케일(영어 등)로 한 번 더 생성합니다."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import pandas as pd
from google import genai
from google.genai import types

import repo_env

I18N_SYSTEM = """You assist international diners at a Korean university cafeteria.
You receive a JSON array of menu rows with Korean text and allergy-related notes (AI-estimated, not medical fact).

Rules:
- Output **one JSON object only** (no markdown code fences).
- Include keys: "locale" (BCP-47 tag), "disclaimer" (short English legal/safety note that this is AI estimation),
  "items" (array).
- Each element of "items" must have:
  - "restaurant" (Korean name OK),
  - "dayColumn" (copy original string),
  - "menuTextKo" (original menu string),
  - "menuSummaryEn" (concise English description of the dish set),
  - "allergyNotesEn" (translate and condense allergy hints; say "possible" / "may contain" where appropriate).
- Keep tone helpful and cautious. Do not claim medical certainty."""


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"JSON 객체를 찾지 못했습니다: {text[:200]}...")
    return json.loads(text[start : end + 1])


def load_rows_from_analysis_csv(path: str, *, limit: int | None) -> list[dict[str, Any]]:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if limit is not None:
        df = df.head(limit)
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        rows.append(
            {
                "식당": r.get("식당"),
                "요일열": r.get("요일열"),
                "메뉴텍스트": r.get("메뉴텍스트"),
                "추정_재료": r.get("추정_재료", ""),
                "알레르기_요약": r.get("알레르기_요약", ""),
            }
        )
    return rows


def summarize_for_locale(
    client: genai.Client,
    model_name: str,
    rows: list[dict[str, Any]],
    locale_tag: str,
) -> dict[str, Any]:
    user_prompt = f"""Target locale (BCP-47): {locale_tag}

Input JSON:
{json.dumps(rows, ensure_ascii=False)}

Produce the JSON object as specified in the system instructions. Set "locale" to "{locale_tag}"."""

    resp = client.models.generate_content(
        model=model_name,
        contents=[user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=I18N_SYSTEM,
            temperature=0.2,
            max_output_tokens=8192,
        ),
    )
    raw = (getattr(resp, "text", "") or "").strip()
    if not raw:
        raise RuntimeError("모델 응답이 비었습니다.")
    parsed = _extract_json_object(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("Invalid model response: root JSON is not an object")
    if not all(k in parsed for k in ("locale", "disclaimer", "items")):
        raise RuntimeError(
            "Invalid model response: missing locale.disclaimer.items (expected top-level keys)"
        )
    if not isinstance(parsed["items"], list):
        raise RuntimeError("Invalid model response: items is not a list")
    if len(rows) > 0 and len(parsed["items"]) == 0:
        raise RuntimeError(
            "Invalid model response: items is empty but input contained menu rows"
        )
    return parsed


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(description="메뉴·알레르기 요약 다국어 생성 (Gemini)")
    parser.add_argument("--csv", required=True, help="menu_allergy_gemini.csv 등")
    parser.add_argument(
        "--locale",
        default="en",
        help="BCP-47 로케일 태그 (프롬프트에 전달, 예: en, en-US, ja)",
    )
    parser.add_argument("--limit", type=int, default=30, help="최대 행 수 (토큰 절약)")
    parser.add_argument(
        "-o",
        "--output",
        help="JSON 저장 경로 (미지정 시 stdout)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        help="Gemini 모델명",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY 가 필요합니다 (.env 또는 환경 변수).")

    rows = load_rows_from_analysis_csv(args.csv, limit=args.limit)
    if not rows:
        raise SystemExit("입력 CSV에 행이 없습니다.")

    client = genai.Client(api_key=api_key)
    result = summarize_for_locale(client, args.model, rows, args.locale)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("저장:", args.output)
    else:
        print(text)


if __name__ == "__main__":
    main()
