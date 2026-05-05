#!/usr/bin/env python3
"""Gemini 텍스트 API 실테스트 실행 스크립트."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types


def load_request(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("요청 파일은 JSON 객체여야 합니다.")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini 텍스트 API 실테스트")
    parser.add_argument(
        "--request",
        default="gemini_text_request_sample.json",
        help="요청 JSON 파일 경로",
    )
    parser.add_argument(
        "--out",
        default="",
        help="응답 저장 파일 경로 (미지정 시 자동 파일명)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    request_path = Path(args.request)
    if not request_path.is_absolute():
        request_path = script_dir / request_path

    repo_root = script_dir.parents[1]
    import sys

    sys.path.insert(0, str(repo_root))
    import repo_env  # noqa: PLC0415

    repo_env.load_dotenv_from_repo_root()

    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY 가 없습니다. .env 또는 환경 변수에 설정하세요.")

    request_data = load_request(request_path)
    model = str(request_data.get("model") or "gemini-2.5-flash")
    system_instruction = str(request_data.get("systemInstruction") or "").strip()
    prompt = str(request_data.get("prompt") or "").strip()
    if not prompt:
        raise SystemExit("prompt 값이 비어 있습니다.")

    generation = request_data.get("generationConfig") or {}
    response_schema = request_data.get("responseSchema")

    config = types.GenerateContentConfig(
        system_instruction=system_instruction if system_instruction else None,
        temperature=float(generation.get("temperature", 0.2)),
        top_p=float(generation.get("topP", 0.9)),
        max_output_tokens=int(generation.get("maxOutputTokens", 1024)),
        response_mime_type="application/json",
        response_schema=response_schema if response_schema else None,
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=config,
    )

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise SystemExit("응답이 비어 있습니다.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"응답 JSON 파싱 실패: {exc}") from exc

    output = {
        "requestedAt": datetime.now().isoformat(),
        "model": model,
        "requestFile": str(request_path),
        "prompt": prompt,
        "response": parsed,
    }

    out_path = Path(args.out) if args.out else script_dir / "gemini_text_response_output.json"
    if not out_path.is_absolute():
        out_path = script_dir / out_path
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] Gemini 호출 성공: {out_path}")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
