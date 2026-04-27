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

from utils.json_extract import extract_json_object

SYSTEM_PROMPT = """당신은 음식 이미지를 보고 식재료를 추정하는 도우미입니다.
반드시 한국어로 답하고, 아래 JSON 객체 하나만 출력하세요.
"""


def _guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


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
    return extract_json_object(raw)


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
    parser.add_argument("image", nargs="?", default="test_image.jpeg")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    args = parser.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다.")
    client = genai.Client(api_key=api_key)
    result = analyze_food_image(client, args.model, args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
