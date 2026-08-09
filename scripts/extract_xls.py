#!/usr/bin/env python3
"""Extract a single-sheet legacy .xls file through Microsoft Excel on macOS."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path


FIELD_SEPARATOR = "\x1f"
ROW_SEPARATOR = "\x1e"


OPEN_APPLESCRIPT = r'''
on run argv
    set inputPath to item 1 of argv
    set fieldSeparator to ASCII character 31

    tell application "Microsoft Excel"
        set display alerts to false
        set workbookRef to open workbook workbook file name inputPath
        set worksheetRef to worksheet 1 of workbookRef
        set worksheetName to name of worksheetRef
        set workbookName to name of workbookRef
        set usedAddress to get address of used range of worksheetRef
    end tell
    return workbookName & fieldSeparator & worksheetName & fieldSeparator & usedAddress
end run
'''


CHUNK_APPLESCRIPT = r'''
on run argv
    set workbookName to item 1 of argv
    set rangeAddress to item 2 of argv
    set fieldSeparator to ASCII character 31
    set rowSeparator to ASCII character 30

    tell application "Microsoft Excel"
        set workbookRef to workbook workbookName
        set worksheetRef to worksheet 1 of workbookRef
        set dataRows to value of (range rangeAddress of worksheetRef)
    end tell

    set outputRows to {}
    repeat with rowValues in dataRows
        set outputValues to {}
        repeat with currentValue in rowValues
            if currentValue is not missing value then
                set valueText to currentValue as text
                set valueText to my replaceText(valueText, fieldSeparator, " ")
                set valueText to my replaceText(valueText, rowSeparator, " ")
                set end of outputValues to valueText
            else
                set end of outputValues to ""
            end if
        end repeat
        set previousDelimiters to AppleScript's text item delimiters
        set AppleScript's text item delimiters to fieldSeparator
        set end of outputRows to outputValues as text
        set AppleScript's text item delimiters to previousDelimiters
    end repeat
    set previousDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to rowSeparator
    set outputText to outputRows as text
    set AppleScript's text item delimiters to previousDelimiters
    return outputText
end run

on replaceText(sourceText, searchText, replacementText)
    set previousDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to searchText
    set sourceParts to text items of sourceText
    set AppleScript's text item delimiters to replacementText
    set resultText to sourceParts as text
    set AppleScript's text item delimiters to previousDelimiters
    return resultText
end replaceText
'''


CLOSE_APPLESCRIPT = r'''
on run argv
    set workbookName to item 1 of argv
    tell application "Microsoft Excel"
        close workbook workbookName saving no
        set display alerts to true
    end tell
end run
'''


def run_applescript(script: str, *args: str) -> str:
    result = subprocess.run(
        ["osascript", "-", *args],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


def column_number(column_name: str) -> int:
    result = 0
    for character in column_name:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def column_name(column_number_value: int) -> str:
    result = ""
    while column_number_value:
        column_number_value, remainder = divmod(column_number_value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def extract_rows(source: Path) -> tuple[str, list[list[str]]]:
    open_result = run_applescript(OPEN_APPLESCRIPT, str(source))
    workbook_name, sheet_name, used_address = open_result.split(FIELD_SEPARATOR)
    address_match = re.fullmatch(
        r"\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)", used_address
    )
    if not address_match:
        raise ValueError(f"Unsupported used range address: {used_address}")
    start_column, start_row, end_column, end_row = address_match.groups()
    start_row_number = int(start_row)
    end_row_number = int(end_row)
    end_column_number = column_number(end_column)
    normalized_end_column = column_name(end_column_number)

    rows: list[list[str]] = []
    try:
        for chunk_start in range(start_row_number, end_row_number + 1, 250):
            chunk_end = min(chunk_start + 249, end_row_number)
            range_address = (
                f"{start_column}{chunk_start}:{normalized_end_column}{chunk_end}"
            )
            chunk_result = run_applescript(
                CHUNK_APPLESCRIPT, workbook_name, range_address
            )
            records = chunk_result.rstrip(ROW_SEPARATOR).split(ROW_SEPARATOR)
            rows.extend(
                record.split(FIELD_SEPARATOR) for record in records if record
            )
    finally:
        run_applescript(CLOSE_APPLESCRIPT, workbook_name)
    return sheet_name, rows


def normalize(rows: list[list[str]]) -> tuple[list[str], list[dict[str, str]]]:
    header_index = next(
        index
        for index, row in enumerate(rows)
        if any("学校名称" in cell for cell in row)
    )
    raw_headers = rows[header_index]
    source_headers = [cell.strip().replace("\n", "") for cell in raw_headers]
    width = len(source_headers)
    headers = [source_headers[0], "省级地区", *source_headers[1:]]

    records: list[dict[str, str]] = []
    current_region = ""
    for row in rows[header_index + 1 :]:
        values = (row + [""] * width)[:width]
        values = [value.strip() for value in values]
        region_match = re.fullmatch(r"(.+?)[（(]\s*\d+\s*所\s*[）)]", values[0])
        if region_match and not any(values[1:]):
            current_region = region_match.group(1).strip()
            continue

        source_record = dict(zip(source_headers, values, strict=True))
        if not source_record.get("学校名称"):
            continue
        serial_number = source_record[source_headers[0]]
        if re.fullmatch(r"\d+\.0", serial_number):
            serial_number = serial_number[:-2]
        source_record[source_headers[0]] = serial_number
        school_id = source_record.get("学校标识码", "")
        if re.fullmatch(r"\d+(?:\.\d+)?[Ee][+-]?\d+", school_id):
            try:
                source_record["学校标识码"] = format(Decimal(school_id), "f").split(".")[0]
            except InvalidOperation:
                pass
        record = {
            source_headers[0]: serial_number,
            "省级地区": current_region,
            **{header: source_record[header] for header in source_headers[1:]},
        }
        records.append(record)
    return headers, records


def write_outputs(
    output_dir: Path,
    base_name: str,
    source: Path,
    sheet_name: str,
    headers: list[str],
    records: list[dict[str, str]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)

    payload = {
        "name": base_name,
        "source_file": source.name,
        "source_sheet": sheet_name,
        "record_count": len(records),
        "fields": headers,
        "records": records,
    }
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("base_name")
    args = parser.parse_args()

    sheet_name, rows = extract_rows(args.source.resolve())
    headers, records = normalize(rows)
    write_outputs(
        args.output_dir.resolve(),
        args.base_name,
        args.source.resolve(),
        sheet_name,
        headers,
        records,
    )
    print(
        json.dumps(
            {
                "sheet": sheet_name,
                "rows": len(records),
                "fields": headers,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
