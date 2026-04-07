#!/usr/bin/env python3
"""음식 이미지를 Gemini Vision으로 분석합니다."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path

import repo_env
from google import genai
from google.genai import types

SYSTEM_PROMPT = """당신은 음식 이미지를 보고 식재료를 추정하는 도우미입니다.
반드시 한국어로 답하고, 아래 JSON 객체 하나만 출력하세요.

형식:
{
  "음식명": "추정 음식명",
  "추정_식재료": [
    {"재료": "...", "신뢰도": 0.0~1.0, "근거": "짧은 근거"}
  ],
  "주의사항": "혼동 가능성 또는 한계"
}

규칙:
- 확실하지 않으면 신뢰도를 낮게 주세요.
- 보이지 않거나 확신이 어려운 재료는 억지로 단정하지 마세요.
- JSON 외 텍스트 금지.
"""


def _guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def _extract_json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"JSON 객체를 찾지 못했습니다: {text[:200]}...")
    return json.loads(text[start : end + 1])


def analyze_food_image_bytes(
    client: genai.Client,
    model_name: str,
    image_bytes: bytes,
    mime_type: str,
) -> dict:
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_text(text=SYSTEM_PROMPT),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )

    raw = (response.text or "").strip()
    if not raw:
        raise RuntimeError("모델 응답이 비어 있습니다.")

    return _extract_json(raw)


def analyze_food_image(client: genai.Client, model_name: str, image_path: str | Path) -> dict:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    image_bytes = path.read_bytes()
    mime_type = _guess_mime_type(path)

    return analyze_food_image_bytes(client, model_name, image_bytes, mime_type)


def main() -> None:
    repo_env.load_dotenv_from_repo_root()

    parser = argparse.ArgumentParser(description="음식 이미지 식재료 추정 (Gemini)")
    parser.add_argument(
        "image",
        nargs="?",
        default="test_image.jpeg",
        help="분석할 이미지 경로 (기본: test_image.jpeg)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        help="모델명",
    )
    parser.add_argument(
        "--ingredients-table",
        action="store_true",
        help="추정_식재료를 표 형태로 추가 출력",
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

    result = analyze_food_image(client, args.model, args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.ingredients_table:
        import pandas as pd

        ing = result.get("추정_식재료", [])
        if ing:
            print()
            print(pd.DataFrame(ing).to_string())


if __name__ == "__main__":
    main()
