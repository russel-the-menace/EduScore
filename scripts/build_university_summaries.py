#!/usr/bin/env python3
"""Build the domestic and international university summary CSV files."""

from __future__ import annotations

import csv
import difflib
import json
import locale
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MASTER = DATA / "master"
STOP_WORDS = {"the", "of", "in", "at", "van"}
DIRECTION_WORDS = {
    "north", "south", "east", "west", "central", "northern", "southern",
    "eastern", "western",
}
WORD_ALIASES = {
    "universita": "university",
    "universitat": "university",
    "universite": "university",
    "universiteit": "university",
    "universiti": "university",
    "universidad": "university",
    "universidade": "university",
    "universitas": "university",
    "universitet": "university",
    "universitesi": "university",
    "technological": "technology",
    "sciences": "science",
}
COUNTRY_ALIASES = {
    "brunei darussalam": "brunei",
    "china mainland": "china",
    "czechia": "czech republic",
    "hong kong sar china": "hong kong",
    "iran islamic republic": "iran",
    "macau sar china": "macau",
    "republic korea": "south korea",
    "russian federation": "russia",
    "taiwan china": "taiwan",
    "turkiye": "turkey",
    "united states america": "united states",
    "viet nam": "vietnam",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ascii_text(value: str | None) -> str:
    return (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def normalize_name(value: str | None, *, strip_parenthetical: bool = True) -> str:
    text = ascii_text(value).replace("&", " and ")
    if strip_parenthetical:
        text = re.sub(r"\([^)]*\)", " ", text)
    words = [WORD_ALIASES.get(word, word) for word in re.findall(r"[a-z0-9]+", text)]
    return " ".join(word for word in words if word not in STOP_WORDS)


def base_name(value: str | None) -> str:
    """Remove a campus/location suffix used by ranking sites."""
    text = value or ""
    text = re.split(r"\s*(?:--|—)\s*", text, maxsplit=1)[0]
    return normalize_name(text)


def normalize_country(value: str | None) -> str:
    country = normalize_name(value)
    return COUNTRY_ALIASES.get(country, country)


def similarity(left: str, right: str) -> tuple[float, float]:
    left_name = normalize_name(left)
    right_name = normalize_name(right)
    if not left_name or not right_name:
        return 0.0, 0.0
    left_tokens = set(left_name.split())
    right_tokens = set(right_name.split())
    sequence = difflib.SequenceMatcher(None, left_name, right_name).ratio()
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return sequence, jaccard


def incompatible_directions(left: str, right: str) -> bool:
    left_directions = set(normalize_name(left).split()) & DIRECTION_WORDS
    right_directions = set(normalize_name(right).split()) & DIRECTION_WORDS
    return bool(left_directions or right_directions) and left_directions != right_directions


def infer_cscse_country_map(
    cscse: list[dict[str, Any]], world_rows: list[dict[str, str]]
) -> dict[str, str]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for school in cscse:
        by_name[normalize_name(school.get("english_name"))].append(school)
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for row in world_rows:
        matches = by_name.get(normalize_name(row["name"]), [])
        if len(matches) == 1:
            votes[matches[0]["country"]][normalize_country(row["country"])] += 1
    return {
        chinese_country: counts.most_common(1)[0][0]
        for chinese_country, counts in votes.items()
        if counts
    }


def deduplicate_cscse(
    schools: list[dict[str, Any]], country_map: dict[str, str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for school in schools:
        country = country_map.get(
            school.get("country") or "", f"cscse:{school.get('country') or ''}"
        )
        english_name = school.get("english_name") or ""
        chinese_name = school.get("chinese_name") or ""
        key = (
            country,
            normalize_name(english_name, strip_parenthetical=False),
            re.sub(r"\s+", "", chinese_name),
        )
        if key not in grouped:
            grouped[key] = school
    return list(grouped.values())


def rebuild_index(entities: list[dict[str, Any]]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = defaultdict(list)
    for entity_index, entity in enumerate(entities):
        for name in entity["names"]:
            normalized = normalize_name(name)
            if normalized and entity_index not in index[normalized]:
                index[normalized].append(entity_index)
            base = base_name(name)
            if base and entity_index not in index[f"__base__:{base}"]:
                index[f"__base__:{base}"].append(entity_index)
    return index


def add_names_to_index(
    index: dict[str, list[int]], entity_index: int, names: list[str]
) -> None:
    for name in names:
        normalized = normalize_name(name)
        if normalized and entity_index not in index[normalized]:
            index[normalized].append(entity_index)
        base = base_name(name)
        if base and entity_index not in index[f"__base__:{base}"]:
            index[f"__base__:{base}"].append(entity_index)


def match_entity(
    name: str,
    country: str,
    entities: list[dict[str, Any]],
    exact_index: dict[str, list[int]],
    country_index: dict[str, list[int]],
    occupied_field: str,
    preferred_field: str | None = None,
) -> tuple[int | None, str]:
    exact = [
        index
        for index in exact_index.get(normalize_name(name), [])
        if entities[index]["country"] == country
        and not entities[index][occupied_field]
    ]
    if len(exact) == 1:
        return exact[0], "exact"
    if preferred_field:
        preferred = [index for index in exact if entities[index][preferred_field]]
        if len(preferred) == 1:
            return preferred[0], "exact_preferred"
    base_exact = [
        index
        for index in exact_index.get(f"__base__:{base_name(name)}", [])
        if entities[index]["country"] == country
        and not entities[index][occupied_field]
    ]
    if len(base_exact) == 1:
        return base_exact[0], "base_exact"
    global_exact = [
        index
        for index in exact_index.get(normalize_name(name), [])
        if not entities[index][occupied_field]
    ]
    if len(global_exact) == 1:
        return global_exact[0], "exact_global"

    candidates: list[tuple[float, float, int]] = []
    for index in country_index.get(country, []):
        entity = entities[index]
        if entity[occupied_field]:
            continue
        valid_names = [
            candidate
            for candidate in entity["names"]
            if not incompatible_directions(name, candidate)
        ]
        if not valid_names:
            continue
        sequence, jaccard = max(
            (similarity(name, candidate) for candidate in valid_names),
            default=(0.0, 0.0),
        )
        if (sequence >= 0.965 and jaccard >= 0.60) or (
            sequence >= 0.90 and jaccard >= 0.80
        ):
            candidates.append((sequence, jaccard, index))
    candidates.sort(reverse=True)
    if not candidates:
        return None, "unmatched"
    best = candidates[0]
    second_score = candidates[1][0] if len(candidates) > 1 else 0.0
    if best[0] < 0.985 and best[0] - second_score < 0.035:
        return None, "ambiguous"
    return best[2], "fuzzy"


def build_domestic() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    universities = load_json(DATA / "china/shanghairanking/全部高校.json")
    ranked = universities[:590]
    unranked = universities[590:]
    locale.setlocale(locale.LC_COLLATE, "zh_CN.UTF-8")
    unranked.sort(key=lambda row: locale.strxfrm(row.get("nameCn") or ""))

    head_rows: list[dict[str, Any]] = []
    for university in ranked:
        codes = set(university.get("charCode") or [])
        head_rows.append(
            {
                "中文名": university.get("nameCn") or "",
                "外文名": university.get("nameEn") or "",
                "软科排名": university.get("rankBcur") or "",
                "985": "是" if 985 in codes else "否",
                "211": "是" if 211 in codes else "否",
                "双一流": "是" if 105 in codes else "否",
            }
        )
    non_head_rows: list[dict[str, Any]] = []
    for university in unranked:
        codes = set(university.get("charCode") or [])
        non_head_rows.append(
            {
                "中文名": university.get("nameCn") or "",
                "外文名": university.get("nameEn") or "",
                "软科排名": "",
                "独立学院": "是" if 22 in codes else "否",
                "民办高校": "是" if 20 in codes else "否",
            }
        )
    return head_rows, non_head_rows


def build_international() -> tuple[list[dict[str, Any]], dict[str, int]]:
    cscse = load_json(
        DATA / "international/cscse/中国留服认证院校名单.json"
    )["schools"]
    usnews = load_json(
        DATA / "rankings/usnews/2026-2027_USNews世界大学排名.json"
    )["universities"]
    qs = load_json(DATA / "rankings/qs/2027_QS世界大学排名.json")["records"]
    shanghai = load_json(DATA / "china/shanghairanking/全部高校.json")

    world_rows = [
        {"name": row["name"], "country": row["country"]} for row in usnews
    ] + [
        {"name": row["institution_name"], "country": row["country_territory"]}
        for row in qs
    ]
    cscse_country_map = infer_cscse_country_map(cscse, world_rows)
    entities: list[dict[str, Any]] = [
        {
            "chinese_name": school.get("chinese_name") or "",
            "display_name": school.get("english_name") or school.get("chinese_name") or "",
            "names": [school.get("english_name") or ""],
            "country": cscse_country_map.get(
                school.get("country") or "", f"cscse:{school.get('country') or ''}"
            ),
            "us_rank": None,
            "us_order": None,
            "has_us": False,
            "qs_rank": "",
            "has_qs": False,
        }
        for school in cscse
    ]

    stats: Counter[str] = Counter()
    exact_index = rebuild_index(entities)
    country_index: dict[str, list[int]] = defaultdict(list)
    for entity_index, entity in enumerate(entities):
        country_index[entity["country"]].append(entity_index)
    for order, row in enumerate(usnews):
        country = normalize_country(row["country"])
        index, method = match_entity(
            row["name"], country, entities, exact_index, country_index, "has_us"
        )
        stats[f"us_{method}"] += 1
        if index is None:
            new_index = len(entities)
            entities.append(
                {
                    "chinese_name": "",
                    "display_name": row["name"],
                    "names": [row["name"]],
                    "country": country,
                    "us_rank": row.get("rank"),
                    "us_order": order,
                    "has_us": True,
                    "qs_rank": "",
                    "has_qs": False,
                }
            )
            add_names_to_index(exact_index, new_index, [row["name"]])
            country_index[country].append(new_index)
        else:
            entity = entities[index]
            entity["names"].append(row["name"])
            entity["display_name"] = row["name"]
            entity["us_rank"] = row.get("rank")
            entity["us_order"] = order
            entity["has_us"] = True
            add_names_to_index(exact_index, index, [row["name"]])

    for row in qs:
        country = normalize_country(row["country_territory"])
        index, method = match_entity(
            row["institution_name"],
            country,
            entities,
            exact_index,
            country_index,
            "has_qs",
            "has_us",
        )
        stats[f"qs_{method}"] += 1
        if index is None:
            new_index = len(entities)
            entities.append(
                {
                    "chinese_name": "",
                    "display_name": row["institution_name"],
                    "names": [row["institution_name"]],
                    "country": country,
                    "us_rank": None,
                    "us_order": None,
                    "has_us": False,
                    "qs_rank": row.get("rank_2027") or "",
                    "has_qs": True,
                }
            )
            add_names_to_index(exact_index, new_index, [row["institution_name"]])
            country_index[country].append(new_index)
        else:
            entity = entities[index]
            entity["names"].append(row["institution_name"])
            if entity["us_order"] is None:
                entity["display_name"] = row["institution_name"]
            entity["qs_rank"] = row.get("rank_2027") or ""
            entity["has_qs"] = True
            add_names_to_index(exact_index, index, [row["institution_name"]])

    # ShanghaiRanking supplies Chinese names for exact English-name matches.
    exact_index = rebuild_index(entities)
    for university in shanghai:
        english_name = university.get("nameEn") or ""
        candidates = exact_index.get(normalize_name(english_name), [])
        if english_name and len(candidates) == 1:
            entity = entities[candidates[0]]
            entity["chinese_name"] = university.get("nameCn") or entity["chinese_name"]
            stats["shanghai_exact"] += 1

    def sort_key(entity: dict[str, Any]) -> tuple[Any, ...]:
        name = normalize_name(entity["display_name"])
        if entity["us_rank"] is not None:
            return (0, entity["us_rank"], entity["us_order"] or 0, name)
        if entity["us_order"] is not None:
            return (1, name)
        return (2, name)

    entities.sort(key=sort_key)
    rows = [
        {
            "中文名": entity["chinese_name"],
            "外文名": entity["display_name"],
            "USNEWS": entity["us_rank"] if entity["us_rank"] is not None else "",
            "QS": entity["qs_rank"],
        }
        for entity in entities
    ]
    stats["final_rows"] = len(rows)
    stats["chinese_names"] = sum(bool(row["中文名"]) for row in rows)
    stats["missing_chinese_names"] = len(rows) - stats["chinese_names"]
    stats["us_ranked"] = sum(row["USNEWS"] != "" for row in rows)
    stats["qs_ranked"] = sum(row["QS"] != "" for row in rows)
    return rows, dict(stats)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    domestic_head, domestic_non_head = build_domestic()
    international, stats = build_international()
    international_head = [row for row in international if row["USNEWS"] != ""]
    international_non_head = [
        {"中文名": row["中文名"], "外文名": row["外文名"], "QS": row["QS"]}
        for row in international
        if row["USNEWS"] == ""
    ]
    international_non_head.sort(key=lambda row: normalize_name(row["外文名"]))
    write_csv(MASTER / "国内头部大学汇总.csv", domestic_head)
    write_csv(MASTER / "国内非头部大学汇总.csv", domestic_non_head)
    write_csv(MASTER / "国外头部大学汇总.csv", international_head)
    write_csv(MASTER / "国外非头部大学汇总.csv", international_non_head)
    audit = {
        "rules": {
            "domestic_ranked_rows": 590,
            "domestic_tail_sort": "zh_CN.UTF-8 collation",
            "international_primary_sort": "USNEWS rank, then source order",
            "international_tail_sort": "normalized foreign name",
            "mainland_chinese_names_are_allowed": True,
            "fuzzy_matching_is_conservative": True,
        },
        "counts": {
            "domestic_head_rows": len(domestic_head),
            "domestic_non_head_rows": len(domestic_non_head),
            "international_head_rows": len(international_head),
            "international_non_head_rows": len(international_non_head),
            **stats,
        },
        "note": (
            "Missing Chinese names are not automatically errors: the CSCSE snapshot can omit "
            "some ranking entries, campus-level entities, and institutions represented under "
            "different official names. Unmatched records are retained rather than assigned a guessed name."
        ),
    }
    (MASTER / "国外大学排名匹配审计.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "domestic_head_rows": len(domestic_head),
                "domestic_non_head_rows": len(domestic_non_head),
                "international_head_rows": len(international_head),
                "international_non_head_rows": len(international_non_head),
                "international": stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
