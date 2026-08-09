#!/usr/bin/env python3
"""Convert the supplied QS 2027 XLSX workbook to normalized CSV and JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


NAMESPACE = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SOURCE_HEADERS = [
    "Index", "Rank", "Previous Rank", "Name", "Country/Territory", "Region",
    "Size", "Focus", "Research", "Status", "AR SCORE", "AR RANK", "ER SCORE",
    "ER RANK", "FSR SCORE", "FSR RANK", "CPF SCORE", "CPF RANK", "IFR SCORE",
    "IFR RANK", "ISR SCORE", "ISR RANK", "IRN SCORE", "IRN RANK", "EO SCORE",
    "EO RANK", "SUS SCORE", "SUS RANK", "Overall SCORE",
]
FIELDS = [
    "index", "rank_2027", "rank_2026", "institution_name", "country_territory",
    "region", "size", "focus", "research_intensity", "status",
    "academic_reputation_score", "academic_reputation_rank",
    "employer_reputation_score", "employer_reputation_rank",
    "faculty_student_score", "faculty_student_rank",
    "citations_per_faculty_score", "citations_per_faculty_rank",
    "international_faculty_score", "international_faculty_rank",
    "international_students_score", "international_students_rank",
    "international_research_network_score", "international_research_network_rank",
    "employment_outcomes_score", "employment_outcomes_rank",
    "sustainability_score", "sustainability_rank", "overall_score",
]
SCORE_FIELDS = {field for field in FIELDS if field.endswith("_score")}


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise ValueError(f"Invalid cell reference: {reference}")
    result = 0
    for character in letters.group(0):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def read_rows(source: Path) -> list[list[str]]:
    with ZipFile(source) as archive:
        shared_strings: list[str] = []
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in shared_root.findall("m:si", NAMESPACE):
            shared_strings.append(
                "".join(node.text or "" for node in item.iterfind(".//m:t", NAMESPACE))
            )

        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet_root.findall(".//m:sheetData/m:row", NAMESPACE):
            row_number = int(row.attrib["r"])
            if row_number < 3:
                continue
            values = [""] * len(FIELDS)
            for cell in row.findall("m:c", NAMESPACE):
                index = column_index(cell.attrib["r"])
                if index >= len(values):
                    continue
                cell_type = cell.attrib.get("t")
                value_node = cell.find("m:v", NAMESPACE)
                value = "" if value_node is None else value_node.text or ""
                if cell_type == "s" and value:
                    value = shared_strings[int(value)]
                elif cell_type == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iterfind(".//m:t", NAMESPACE)
                    )
                values[index] = value.strip()
            rows.append(values)
    return rows


def normalize_score(value: str) -> float | int | None:
    if not value:
        return None
    try:
        number = Decimal(value).quantize(Decimal("0.1"))
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral() else float(number)


def convert(source: Path) -> list[dict[str, object]]:
    rows = read_rows(source)
    if rows[0] != SOURCE_HEADERS:
        raise ValueError(f"Unexpected QS headers: {rows[0]}")

    records: list[dict[str, object]] = []
    for values in rows[1:]:
        if not any(values):
            continue
        record: dict[str, object] = dict(zip(FIELDS, values, strict=True))
        record["index"] = int(values[0])
        for field in SCORE_FIELDS:
            record[field] = normalize_score(str(record[field]))
        records.append(record)
    return records


def write_outputs(source: Path, output_dir: Path, records: list[dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "2027_QS世界大学排名.csv"
    json_path = output_dir / "2027_QS世界大学排名.json"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

    payload = {
        "name": "2027 QS World University Rankings",
        "source_file": source.name,
        "record_count": len(records),
        "fields": FIELDS,
        "records": records,
    }
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=Path("data/sources/2027_QS世界大学排名原始数据.xlsx"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    records = convert(args.source)
    write_outputs(args.source, args.output_dir, records)
    print(json.dumps({"records": len(records), "fields": FIELDS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
