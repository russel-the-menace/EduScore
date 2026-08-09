#!/usr/bin/env node

const fs = require("fs");
const crypto = require("crypto");
const https = require("https");
const path = require("path");
const vm = require("vm");

const PAGE_URL =
  "https://www.shanghairanking.cn/institution?name=&c=0&r=0&l=0&e=0";
const OUTPUT_DIR = path.resolve(
  process.argv[2] || path.join(__dirname, "..", "data", "china", "shanghairanking")
);

const categories = [
  { filename: "双一流高校.json", code: 105 },
  { filename: "985高校.json", code: 985 },
  { filename: "211高校.json", code: 211 },
  { filename: "合作高校.json", code: 21 },
  { filename: "民办高校.json", code: 20 },
  { filename: "独立学院.json", code: 22 },
];

function request(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
            "AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
          Referer: PAGE_URL,
        },
      },
      (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume();
          resolve(request(new URL(res.headers.location, url).href));
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode}: ${url}`));
          return;
        }

        res.setEncoding("utf8");
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => resolve(body));
      }
    );
    req.on("error", reject);
  });
}

function findPayloadUrl(pageHtml) {
  const match = pageHtml.match(
    /https:\/\/www\.shanghairanking\.cn\/_nuxt\/static\/[^"']+\/institution\/payload\.js/
  );
  if (match) return match[0];

  const relative = pageHtml.match(
    /\/_nuxt\/static\/[^"']+\/institution\/payload\.js/
  );
  if (relative) return new URL(relative[0], PAGE_URL).href;

  throw new Error("未在页面中找到 institution/payload.js");
}

function parsePayload(source) {
  let captured;
  const context = {
    __NUXT_JSONP__: (route, data) => {
      captured = { route, data };
    },
  };
  vm.runInNewContext(source, context, { timeout: 30000 });

  const universities = captured?.data?.data?.[0]?.univList;
  if (!Array.isArray(universities)) {
    throw new Error("载荷结构变化：未找到 data[0].univList");
  }
  return universities;
}

function writeJson(filename, data) {
  const target = path.join(OUTPUT_DIR, filename);
  fs.writeFileSync(target, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  console.log(`${filename}: ${data.length}`);
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function sha256(filename) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(path.join(OUTPUT_DIR, filename)))
    .digest("hex");
}

function writeCsv(universities) {
  const fields = [
    "univ_code", "slug", "name_cn", "name_en", "province", "city",
    "admin_type", "category", "level", "education_level", "current_rank",
    "is_vocational", "is_double_first_class", "is_985", "is_211",
    "is_cooperative", "is_private", "is_independent_college",
  ];
  const rows = universities.map((university) => ({
    univ_code: university.univCode ?? null,
    slug: university.up ?? null,
    name_cn: university.nameCn ?? null,
    name_en: university.nameEn ?? null,
    province: university.provinceShort ?? null,
    city: university.cityName ?? null,
    admin_type: university.adminType ?? null,
    category: university.categoryName ?? null,
    level: university.level ?? null,
    education_level: university.eduLevel ?? null,
    current_rank: university.rankBcur ?? null,
    is_vocational: Boolean(university.isVocational),
    is_double_first_class: university.charCode?.includes(105) ?? false,
    is_985: university.charCode?.includes(985) ?? false,
    is_211: university.charCode?.includes(211) ?? false,
    is_cooperative: university.charCode?.includes(21) ?? false,
    is_private: university.charCode?.includes(20) ?? false,
    is_independent_college: university.charCode?.includes(22) ?? false,
  }));
  const csv = [
    fields.join(","),
    ...rows.map((row) => fields.map((field) => csvCell(row[field])).join(",")),
  ].join("\n") + "\n";
  fs.writeFileSync(path.join(OUTPUT_DIR, "软科全部高校.csv"), `\uFEFF${csv}`, "utf8");
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const pageHtml = await request(PAGE_URL);
  const payloadUrl = findPayloadUrl(pageHtml);
  const payload = await request(payloadUrl);
  const payloadUniversities = parsePayload(payload);
  // Match the site's default list: historical changed/merged institutions are hidden.
  const universities = payloadUniversities.filter(
    (university) => !university.changeType
  );

  writeJson("全部高校.json", universities);
  writeCsv(universities);
  const counts = { 全部高校: universities.length };
  for (const category of categories) {
    const rows = universities.filter(
      (university) =>
        Array.isArray(university.charCode) &&
        university.charCode.includes(category.code)
    );
    writeJson(category.filename, rows);
    counts[path.basename(category.filename, ".json")] = rows.length;
  }

  const files = ["全部高校.json", ...categories.map((item) => item.filename), "软科全部高校.csv"];
  const metadata = {
    publisher: "软科（ShanghaiRanking）",
    source_url: PAGE_URL,
    payload_url: payloadUrl,
    exported_at: new Date().toISOString(),
    counts,
    files: Object.fromEntries(files.map((filename) => [filename, { sha256: sha256(filename) }])),
  };
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "软科院校库.metadata.json"),
    `${JSON.stringify(metadata, null, 2)}\n`,
    "utf8"
  );
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
