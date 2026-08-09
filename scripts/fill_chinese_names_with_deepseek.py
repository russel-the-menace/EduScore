#!/usr/bin/env python3
"""Fill unresolved university Chinese names through the DeepSeek API."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data/international/generated"
PENDING = GENERATED / "DeepSeek待补中文名.json"
OUTPUT = GENERATED / "DeepSeek补充中文名.json"
API_URL = "https://api.deepseek.com/chat/completions"
BATCH_SIZE = 40


def load_json(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def parse_json_array(content: str) -> list[dict[str, str]]:
    fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", content, re.DOTALL)
    payload = fenced.group(1) if fenced else content
    result = json.loads(payload)
    if not isinstance(result, list):
        raise ValueError("DeepSeek response is not a JSON array")
    return result


def request_batch(api_key: str, batch: list[dict[str, object]]) -> list[dict[str, str]]:
    schools = [
        {
            "english_name": row["english_name"],
            "country": row["country"],
        }
        for row in batch
    ]
    prompt = (
        "你是大学名称数据清洗专家。请为下列学校给出通行、准确的简体中文校名。"
        "必须依据英文名和国家消歧；已有正式中文名时使用正式名，否则给出保守的规范译名。"
        "只返回 JSON 数组，每项严格包含 english_name 和 chinese_name，english_name 必须原样返回，"
        "不得省略、增加或调整顺序。数据：\n"
        + json.dumps(schools, ensure_ascii=False)
    )
    body = json.dumps(
        {
            "model": "deepseek-chat",
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "只输出有效 JSON，不要解释。"},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_array(result["choices"][0]["message"]["content"])


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    pending = load_json(PENDING)
    completed = load_json(OUTPUT)
    completed_by_name = {
        row["english_name"]: row
        for row in completed
        if row.get("english_name") and row.get("chinese_name")
    }
    remaining = [row for row in pending if row["english_name"] not in completed_by_name]
    for offset in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[offset : offset + BATCH_SIZE]
        expected = [row["english_name"] for row in batch]
        for attempt in range(3):
            try:
                results = request_batch(api_key, batch)
                actual = [row.get("english_name") for row in results]
                if actual != expected or any(not row.get("chinese_name") for row in results):
                    raise ValueError("DeepSeek response names do not match the request")
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        for row in results:
            completed_by_name[row["english_name"]] = {
                "english_name": row["english_name"],
                "chinese_name": row["chinese_name"].strip(),
                "source": "DeepSeek deepseek-chat",
            }
        ordered = [
            completed_by_name[row["english_name"]]
            for row in pending
            if row["english_name"] in completed_by_name
        ]
        OUTPUT.write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"completed {len(ordered)}/{len(pending)}", flush=True)


if __name__ == "__main__":
    main()
