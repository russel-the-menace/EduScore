#!/usr/bin/env node
/**
 * Download all institutions published by CSCSE's "认证院校查询" service.
 *
 * Requirements: Node.js 18+ (uses the built-in fetch API)
 * Usage: node fetch_cscse_schools.mjs [output-directory]
 */

import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const PAGE_SIZE = 1000;
const REQUEST_DELAY_MS = 120;
const SOURCE_URL = "https://yxcx.cscse.edu.cn/rzyxmd2";
const API_URL = "https://yxcx.cscse.edu.cn/api/xlxwrzz/xlxwrz/getUniversityListOrPage";
const outputDirectory = resolve(process.argv[2] ?? "./data/international/cscse");
const execFileAsync = promisify(execFile);

function delay(milliseconds) {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

async function query(payload) {
  // curl is used because this service currently rejects Node's built-in TLS client
  // in some networks, while accepting its browser-compatible TLS handshake.
  const { stdout } = await execFileAsync("curl", [
    "--fail-with-body",
    "--silent",
    "--show-error",
    "--request", "POST",
    "--header", "Content-Type: application/json",
    "--header", "Origin: https://yxcx.cscse.edu.cn",
    "--referer", SOURCE_URL,
    "--user-agent", "cscse-school-export/1.0",
    "--data", JSON.stringify(payload),
    API_URL,
  ], { maxBuffer: 10 * 1024 * 1024 });

  let body;
  try {
    body = JSON.parse(stdout);
  } catch {
    throw new Error(`API returned invalid JSON for ${JSON.stringify(payload)}.`);
  }
  if (!Array.isArray(body.data) || !Number.isInteger(body.total)) {
    throw new Error(`Unexpected API response for ${JSON.stringify(payload)}: ${JSON.stringify(body)}`);
  }
  return body;
}

function normalize(row) {
  return {
    id: String(row.ID),
    chinese_name: row.CHINESE_NAME ?? null,
    english_name: row.ENGLISH_NAME ?? null,
    country: row.COUNTRY ?? null,
    university_index: row.UNIVERSITYINDEX ?? null,
    country_index: row.COUNTRYINDEX ?? null,
    status: row.STATUS ?? null,
    review_note: row.ICON ?? null,
  };
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

async function main() {
  await mkdir(outputDirectory, { recursive: true });

  // The API provides its authoritative current list of school-name indexes.
  const firstPage = await query({ currentPage: 1, pageSize: PAGE_SIZE, universityIndex: "A" });
  const indexes = firstPage.indexList;
  if (!Array.isArray(indexes) || indexes.length === 0) {
    throw new Error("The API did not return university indexes.");
  }

  const schoolsById = new Map();
  const perIndex = {};

  for (const index of indexes) {
    const first = index === "A"
      ? firstPage
      : await query({ currentPage: 1, pageSize: PAGE_SIZE, universityIndex: index });
    const pages = Math.ceil(first.total / PAGE_SIZE);
    perIndex[index] = first.total;

    for (let page = 1; page <= pages; page += 1) {
      const result = page === 1 ? first : await query({
        currentPage: page,
        pageSize: PAGE_SIZE,
        universityIndex: index,
      });

      if (result.total !== first.total) {
        throw new Error(`Total changed while downloading index ${index}; rerun the export for a consistent snapshot.`);
      }
      for (const row of result.data) {
        const school = normalize(row);
        if (!school.id || school.id === "undefined") {
          throw new Error(`Encountered a school without ID in index ${index}, page ${page}.`);
        }
        schoolsById.set(school.id, school);
      }
      process.stderr.write(`\r${index}: page ${page}/${pages}`);
      await delay(REQUEST_DELAY_MS);
    }
    process.stderr.write("\n");
  }

  const schools = [...schoolsById.values()].sort((a, b) =>
    (a.university_index ?? "").localeCompare(b.university_index ?? "") ||
    (a.chinese_name ?? "").localeCompare(b.chinese_name ?? "", "zh-Hans-CN") ||
    a.id.localeCompare(b.id),
  );
  const exportedAt = new Date().toISOString();
  const metadata = {
    source: SOURCE_URL,
    api: API_URL,
    exported_at: exportedAt,
    schema: {
      id: "CSCSE institution ID",
      chinese_name: "Chinese institution name",
      english_name: "English institution name",
      country: "Country or region",
      university_index: "Name index returned by the source API",
      country_index: "Country index returned by the source API",
      status: "Source status value",
      review_note: "Source review notice, including strengthened-review warnings",
    },
    source_totals_by_index: perIndex,
    source_total: Object.values(perIndex).reduce((sum, value) => sum + value, 0),
    unique_school_count: schools.length,
  };

  const columns = [
    "id", "chinese_name", "english_name", "country", "university_index",
    "country_index", "status", "review_note",
  ];
  const csv = [
    columns.join(","),
    ...schools.map((school) => columns.map((column) => csvCell(school[column])).join(",")),
  ].join("\n") + "\n";

  await writeFile(resolve(outputDirectory, "中国留服认证院校名单.csv"), `\uFEFF${csv}`);
  await writeFile(resolve(outputDirectory, "中国留服认证院校名单.json"), `${JSON.stringify({ metadata, schools }, null, 2)}\n`);
  await writeFile(resolve(outputDirectory, "中国留服认证院校名单.jsonl"), schools.map((school) => JSON.stringify(school)).join("\n") + "\n");
  await writeFile(resolve(outputDirectory, "中国留服认证院校名单.metadata.json"), `${JSON.stringify(metadata, null, 2)}\n`);

  console.log(`Exported ${schools.length} unique schools to ${outputDirectory}`);
}

main().catch((error) => {
  console.error(error.stack ?? error);
  process.exitCode = 1;
});
