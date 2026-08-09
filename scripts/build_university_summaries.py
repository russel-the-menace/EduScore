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


def load_greater_china_names() -> list[dict[str, str]]:
    path = DATA / "international/greater_china/港澳台院校中英文对照.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def build_international() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, int]
]:
    cscse = load_json(
        DATA / "international/cscse/中国留服认证院校名单.json"
    )["schools"]
    usnews = load_json(
        DATA / "rankings/usnews/2026-2027_USNews世界大学排名.json"
    )["universities"]
    qs = load_json(DATA / "rankings/qs/2027_QS世界大学排名.json")["records"]
    shanghai = load_json(DATA / "china/shanghairanking/全部高校.json")
    greater_china = load_greater_china_names()
    generated_path = DATA / "international/generated/DeepSeek补充中文名.json"
    generated_names = load_json(generated_path) if generated_path.exists() else []
    qs_generated_path = DATA / "international/generated/DeepSeek_QS补充中文名.json"
    qs_generated_names = load_json(qs_generated_path) if qs_generated_path.exists() else []
    corrections_path = DATA / "international/greater_china/院校中文名人工修正.csv"
    with corrections_path.open(encoding="utf-8-sig", newline="") as source:
        chinese_name_corrections = {
            normalize_name(row["外文名"]): row["中文名"] for row in csv.DictReader(source)
        }
    qs_corrections_path = DATA / "international/greater_china/QS院校中文名人工修正.csv"
    with qs_corrections_path.open(encoding="utf-8-sig", newline="") as source:
        qs_chinese_name_corrections = {
            normalize_name(row["QS外文名"]): row["中文名"] for row in csv.DictReader(source)
        }
    qs_exclusions_path = DATA / "international/greater_china/QS错误匹配排除.csv"
    with qs_exclusions_path.open(encoding="utf-8-sig", newline="") as source:
        qs_match_exclusions = {
            (normalize_name(row["QS外文名"]), normalize_name(row["USNEWS外文名"]))
            for row in csv.DictReader(source)
        }

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
            "cscse_chinese_name": school.get("chinese_name") or "",
            "display_name": school.get("english_name") or school.get("chinese_name") or "",
            "names": [school.get("english_name") or ""],
            "country": cscse_country_map.get(
                school.get("country") or "", f"cscse:{school.get('country') or ''}"
            ),
            "us_rank": None,
            "us_order": None,
            "has_us": False,
            "qs_rank": "",
            "qs_source_name": "",
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
                    "cscse_chinese_name": "",
                    "display_name": row["name"],
                    "names": [row["name"]],
                    "country": country,
                    "us_rank": row.get("rank"),
                    "us_order": order,
                    "has_us": True,
                    "qs_rank": "",
                    "qs_source_name": "",
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
                    "cscse_chinese_name": "",
                    "display_name": row["institution_name"],
                    "names": [row["institution_name"]],
                    "country": country,
                    "us_rank": None,
                    "us_order": None,
                    "has_us": False,
                    "qs_rank": row.get("rank_2027") or "",
                    "qs_source_name": row["institution_name"],
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
            entity["qs_source_name"] = row["institution_name"]
            entity["has_qs"] = True
            add_names_to_index(exact_index, index, [row["institution_name"]])

    # Rebuild head-table Chinese names from explicit English-name matches only.
    region_country = {"香港": "hong kong", "澳门": "macau", "台湾": "taiwan"}
    manual_index: dict[tuple[str, str], str] = {}
    for school in greater_china:
        aliases = [school["外文名"]]
        aliases.extend(
            alias.strip() for alias in school.get("英文别名", "").split("|") if alias.strip()
        )
        for alias in aliases:
            manual_index[(region_country[school["地区"]], normalize_name(alias))] = school["中文名"]

    generated_index = {
        normalize_name(row.get("english_name")): row.get("chinese_name") or ""
        for row in generated_names
        if row.get("english_name") and row.get("chinese_name")
    }
    shanghai_index: dict[str, str] = {}
    for university in shanghai:
        english_name = university.get("nameEn") or ""
        chinese_name = university.get("nameCn") or ""
        if english_name and chinese_name:
            shanghai_index.setdefault(normalize_name(english_name), chinese_name)
    pending: list[dict[str, Any]] = []
    used_head_chinese_names: set[str] = set()
    for entity in entities:
        if entity["us_rank"] is None:
            continue
        entity["chinese_name"] = ""
        manual_name = next(
            (
                manual_index[(entity["country"], normalize_name(name))]
                for name in entity["names"]
                if (entity["country"], normalize_name(name)) in manual_index
            ),
            "",
        )
        if manual_name:
            entity["chinese_name"] = manual_name
            stats["head_chinese_greater_china"] += 1
        elif entity["country"] == "china" and normalize_name(entity["display_name"]) in shanghai_index:
            entity["chinese_name"] = shanghai_index[normalize_name(entity["display_name"])]
            stats["head_chinese_shanghai"] += 1
        elif entity["cscse_chinese_name"]:
            entity["chinese_name"] = entity["cscse_chinese_name"]
            stats["head_chinese_cscse"] += 1
        else:
            generated_name = generated_index.get(normalize_name(entity["display_name"]), "")
            if generated_name:
                entity["chinese_name"] = generated_name
                stats["head_chinese_deepseek"] += 1
            else:
                pending.append(
                    {
                        "english_name": entity["display_name"],
                        "country": entity["country"],
                        "usnews_rank": entity["us_rank"],
                    }
                )
        if entity["chinese_name"]:
            used_head_chinese_names.add(re.sub(r"\s+", "", entity["chinese_name"]))

    for entity in entities:
        correction = chinese_name_corrections.get(normalize_name(entity["display_name"]))
        if entity["us_rank"] is not None and correction:
            entity["chinese_name"] = correction
            stats["head_chinese_manual_correction"] += 1

    qs_pending = [
        {
            "english_name": entity["qs_source_name"],
            "country": entity["country"],
            "qs_rank": entity["qs_rank"],
        }
        for entity in entities
        if entity["has_qs"] and entity["us_rank"] is None
    ]
    qs_pending_path = DATA / "international/generated/DeepSeek_QS待补中文名.json"
    qs_pending_path.parent.mkdir(parents=True, exist_ok=True)
    qs_pending_path.write_text(
        json.dumps(qs_pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    qs_generated_index = {
        normalize_name(row.get("english_name")): row.get("chinese_name") or ""
        for row in qs_generated_names
        if row.get("english_name") and row.get("chinese_name")
    }
    qs_match_audit: list[dict[str, Any]] = []
    for qs_entity in entities:
        if not qs_entity["has_qs"] or qs_entity["us_rank"] is not None:
            continue
        generated_chinese = qs_generated_index.get(
            normalize_name(qs_entity["qs_source_name"]), ""
        )
        generated_chinese = qs_chinese_name_corrections.get(
            normalize_name(qs_entity["qs_source_name"]), generated_chinese
        )
        if not generated_chinese:
            continue
        chinese_aliases = {generated_chinese}
        if qs_entity["cscse_chinese_name"]:
            chinese_aliases.add(qs_entity["cscse_chinese_name"])
        chinese_keys = {re.sub(r"\s+", "", name) for name in chinese_aliases}
        candidates = [
            entity
            for entity in entities
            if entity["us_rank"] is not None
            and not entity["qs_rank"]
            and entity["country"] == qs_entity["country"]
            and re.sub(r"\s+", "", entity["chinese_name"]) in chinese_keys
        ]
        method = "unique_chinese_country"
        matched: dict[str, Any] | None = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            scored = sorted(
                (
                    max(similarity(qs_entity["qs_source_name"], name)[0] for name in candidate["names"]),
                    candidate,
                )
                for candidate in candidates
            )
            if scored[-1][0] >= 0.65 and (
                len(scored) == 1 or scored[-1][0] - scored[-2][0] >= 0.10
            ):
                matched = scored[-1][1]
                method = "chinese_country_english_disambiguated"
        if matched is None and not candidates:
            english_candidates: list[tuple[float, float, dict[str, Any]]] = []
            for entity in entities:
                if (
                    entity["us_rank"] is None
                    or entity["qs_rank"]
                    or entity["country"] != qs_entity["country"]
                ):
                    continue
                sequence, jaccard = max(
                    (
                        similarity(qs_entity["qs_source_name"], name)
                        for name in entity["names"]
                    ),
                    default=(0.0, 0.0),
                )
                english_candidates.append((sequence, jaccard, entity))
            english_candidates.sort(key=lambda item: (item[0], item[1]))
            if english_candidates:
                best_sequence, best_jaccard, best_entity = english_candidates[-1]
                second_sequence = (
                    english_candidates[-2][0] if len(english_candidates) > 1 else 0.0
                )
                if (
                    best_sequence >= 0.88
                    and best_sequence - second_sequence >= 0.08
                ) or (
                    best_sequence >= 0.82
                    and best_jaccard >= 0.66
                    and best_sequence - second_sequence >= 0.06
                ):
                    matched = best_entity
                    method = "english_high_confidence"
        if matched is not None and (
            normalize_name(qs_entity["qs_source_name"]),
            normalize_name(matched["display_name"]),
        ) in qs_match_exclusions:
            matched = None
            method = "manually_excluded"
        if matched is not None:
            matched["qs_rank"] = qs_entity["qs_rank"]
            matched["has_qs"] = True
            matched["names"].append(qs_entity["qs_source_name"])
            qs_entity["qs_rank"] = ""
            stats[f"qs_deepseek_{method}"] += 1
        qs_match_audit.append(
            {
                "qs_english_name": qs_entity["qs_source_name"],
                "deepseek_chinese_name": generated_chinese,
                "cscse_chinese_name": qs_entity["cscse_chinese_name"],
                "country": qs_entity["country"],
                "qs_rank": matched["qs_rank"] if matched is not None else qs_entity["qs_rank"],
                "matched_usnews_english_name": matched["display_name"] if matched else "",
                "method": method if matched else (
                    method if method == "manually_excluded" else ("ambiguous" if candidates else "unmatched")
                ),
                "candidate_count": len(candidates),
            }
        )
    qs_audit_path = MASTER / "QS中文名回填审计.json"
    qs_audit_path.parent.mkdir(parents=True, exist_ok=True)
    qs_audit_path.write_text(
        json.dumps(qs_match_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    used_head_chinese_names |= {
        re.sub(r"\s+", "", entity["chinese_name"])
        for entity in entities
        if entity["us_rank"] is not None and entity["chinese_name"]
    }

    pending_path = DATA / "international/generated/DeepSeek待补中文名.json"
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def sort_key(entity: dict[str, Any]) -> tuple[Any, ...]:
        name = normalize_name(entity["display_name"])
        if entity["us_rank"] is not None:
            return (0, entity["us_rank"], entity["us_order"] or 0, name)
        if entity["us_order"] is not None:
            return (1, name)
        return (2, name)

    entities.sort(key=sort_key)
    head_rows = [
        {
            "中文名": entity["chinese_name"],
            "外文名": entity["display_name"],
            "USNEWS": entity["us_rank"] if entity["us_rank"] is not None else "",
            "QS": entity["qs_rank"],
        }
        for entity in entities
        if entity["us_rank"] is not None
    ]

    qs_by_cscse_chinese: dict[str, str] = {}
    for entity in entities:
        chinese_name = re.sub(r"\s+", "", entity["cscse_chinese_name"])
        if chinese_name and entity["qs_rank"]:
            qs_by_cscse_chinese.setdefault(chinese_name, entity["qs_rank"])
    non_head_rows: list[dict[str, Any]] = []
    seen_chinese_names: set[str] = set()
    for school in cscse:
        chinese_key = re.sub(r"\s+", "", school.get("chinese_name") or "")
        if not chinese_key or chinese_key in used_head_chinese_names or chinese_key in seen_chinese_names:
            continue
        seen_chinese_names.add(chinese_key)
        non_head_rows.append(
            {
                "中文名": school.get("chinese_name") or "",
                "外文名": school.get("english_name") or "",
                "QS": qs_by_cscse_chinese.get(chinese_key, ""),
            }
        )
    non_head_rows.sort(key=lambda row: normalize_name(row["外文名"]))

    stats["head_rows"] = len(head_rows)
    stats["head_chinese_names"] = sum(bool(row["中文名"]) for row in head_rows)
    stats["head_missing_chinese_names"] = len(pending)
    stats["non_head_rows"] = len(non_head_rows)
    stats["qs_ranked_head"] = sum(row["QS"] != "" for row in head_rows)
    stats["qs_ranked_non_head"] = sum(row["QS"] != "" for row in non_head_rows)
    return head_rows, non_head_rows, dict(stats)


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
    international_head, international_non_head, stats = build_international()
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
            "qs_second_pass": "DeepSeek Chinese name + country, then conservative English disambiguation",
            "qs_manual_exclusions_are_enforced": True,
        },
        "counts": {
            "domestic_head_rows": len(domestic_head),
            "domestic_non_head_rows": len(domestic_non_head),
            "international_head_rows": len(international_head),
            "international_non_head_rows": len(international_non_head),
            **stats,
        },
        "note": (
            "Head-table Chinese names are rebuilt in priority order from the Greater China "
            "mapping, ShanghaiRanking, CSCSE English-name matches, and saved DeepSeek results. "
            "The non-head table contains CSCSE records whose normalized Chinese names are not "
            "used by the head table. Same Chinese names can still identify distinct institutions "
            "in different countries, so head rows remain keyed by their English ranking entities."
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
