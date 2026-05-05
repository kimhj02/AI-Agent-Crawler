#!/usr/bin/env python3
"""food_image 폴더 이미지 일괄 Gemini 검증."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from google.api_core.exceptions import ServiceUnavailable
from google import genai

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))

import repo_env  # noqa: E402
from app.domain.image.agent import analyze_food_image  # noqa: E402


def _extract_food_name(payload: dict) -> str | None:
    return payload.get("음식명") or payload.get("foodName")


def _extract_ingredient_count(payload: dict) -> int:
    items = payload.get("추정_식재료") or payload.get("ingredients") or payload.get("식재료") or []
    return len(items) if isinstance(items, list) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="food_image 폴더 이미지 일괄 Gemini 검증")
    parser.add_argument("--wait-seconds", type=int, default=20, help="이미지 간 대기 시간(초)")
    parser.add_argument("--max-retries", type=int, default=2, help="503 발생 시 이미지당 최대 재시도 횟수")
    parser.add_argument("--output", default="gemini_food_image_validation_results.json", help="결과 저장 파일명")
    args = parser.parse_args()
    if args.wait_seconds < 0:
        raise SystemExit("--wait-seconds 는 0 이상의 정수여야 합니다.")
    if args.max_retries < 0:
        raise SystemExit("--max-retries 는 0 이상의 정수여야 합니다.")

    repo_env.load_dotenv_from_repo_root()
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다.")

    model = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    client = genai.Client(api_key=api_key)

    base = Path(__file__).resolve().parent
    images = sorted([p for p in base.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}])
    results: list[dict] = []

    for idx, image_path in enumerate(images):
        item: dict = {"file": str(image_path)}
        last_error = ""
        for attempt in range(args.max_retries + 1):
            try:
                analyzed = analyze_food_image(client, model, image_path)
                item["ok"] = True
                item["foodName"] = _extract_food_name(analyzed)
                item["ingredientCount"] = _extract_ingredient_count(analyzed)
                item["raw"] = analyzed
                print(f"[OK] {image_path.name} | 음식명={item['foodName']} | 재료수={item['ingredientCount']}")
                break
            except ServiceUnavailable as exc:
                last_error = str(exc)
                if attempt < args.max_retries:
                    wait_retry = min(60, args.wait_seconds + 10 * (attempt + 1))
                    print(f"[RETRY] {image_path.name} | {last_error} | {wait_retry}초 후 재시도")
                    time.sleep(wait_retry)
                    continue
                item["ok"] = False
                item["error"] = last_error
                print(f"[FAIL] {image_path.name} | {last_error}")
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                item["ok"] = False
                item["error"] = last_error
                print(f"[FAIL] {image_path.name} | {last_error}")
                break
        results.append(item)
        if idx < len(images) - 1:
            time.sleep(max(args.wait_seconds, 0))

    out_path = base / args.output
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
