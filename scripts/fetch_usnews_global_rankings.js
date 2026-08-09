/**
 * Run this script in the browser DevTools console while visiting:
 * https://www.usnews.com/education/best-global-universities/rankings
 *
 * It loads every result, validates the count, and downloads JSON and CSV files.
 */
(async () => {
  const SOURCE_URL =
    "https://www.usnews.com/education/best-global-universities/rankings";
  const EXPECTED_TOTAL = 2604;
  const CARD_SELECTOR =
    'section[class*="DetailCardGlobalUniversities__CardContainer"]';

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const getCards = () => Array.from(document.querySelectorAll(CARD_SELECTOR));

  while (getCards().length < EXPECTED_TOTAL) {
    const button = Array.from(document.querySelectorAll("button")).find(
      (element) => element.textContent.trim() === "Load More"
    );
    if (!button) break;

    const previousCount = getCards().length;
    button.scrollIntoView({ block: "center" });
    button.click();

    const deadline = Date.now() + 15000;
    while (getCards().length === previousCount && Date.now() < deadline) {
      await sleep(200);
    }
    if (getCards().length === previousCount) {
      throw new Error(`Loading stopped at ${previousCount} records`);
    }
    console.log(`Loaded ${getCards().length}/${EXPECTED_TOTAL}`);
  }

  const universities = getCards().map((section) => {
    const link = section.querySelector(
      'h2 a[href*="/education/best-global-universities/"]'
    );
    const location = Array.from(section.querySelectorAll("h2 + p span"));
    const rankItem = section.querySelector(".rank-list-item");
    const rankText = rankItem?.querySelector("strong")?.textContent.trim() || "";
    const rankLabelRaw = Array.from(rankItem?.querySelectorAll("strong") || [])
      .slice(1)
      .map((element) => element.textContent.trim())
      .join(" ");
    const stats = {};

    for (const term of section.querySelectorAll("dt")) {
      const value = term.nextElementSibling;
      if (value?.tagName === "DD") {
        stats[term.textContent.trim()] = value.textContent.trim();
      }
    }

    const url = link?.href || null;
    const idMatch = url?.match(/-(\d+)$/);
    const numericRank = rankText.match(/\d+/);
    const enrollment = stats.Enrollment;
    const globalScore = stats["Global Score"];

    return {
      id: idMatch ? Number(idMatch[1]) : null,
      name: link?.textContent.trim() || null,
      country: location[0]?.textContent.trim() || null,
      country_code:
        section
          .querySelector('img[src*="/flags-svg/"]')
          ?.src.match(/\/([A-Z]{3})\.svg/)?.[1] || null,
      city: location[2]?.textContent.trim() || null,
      rank: numericRank ? Number(numericRank[0]) : null,
      is_ranked: Boolean(numericRank),
      is_tied: /\(tie\)/i.test(rankLabelRaw),
      rank_label:
        rankLabelRaw.replace(/\s*\(tie\)\s*/i, "").trim() || null,
      global_score:
        globalScore && globalScore !== "N/A"
          ? Number(globalScore.replace(/,/g, ""))
          : null,
      enrollment:
        enrollment && enrollment !== "N/A"
          ? Number(enrollment.replace(/,/g, ""))
          : null,
      url,
      image_url:
        section.querySelector('img[src*="/object/image/"]')?.src || null,
    };
  });

  const uniqueUniversities = Array.from(
    new Map(universities.map((university) => [university.id, university])).values()
  );
  if (uniqueUniversities.length !== EXPECTED_TOTAL) {
    throw new Error(
      `Expected ${EXPECTED_TOTAL} unique records, got ${uniqueUniversities.length}`
    );
  }

  const output = {
    metadata: {
      title: "2026-2027 Best Global Universities Rankings",
      publisher: "U.S. News & World Report",
      source_url: SOURCE_URL,
      scraped_at: new Date().toISOString(),
      page_reported_total: EXPECTED_TOTAL,
      ranked_count: uniqueUniversities.filter((item) => item.is_ranked).length,
      unranked_count: uniqueUniversities.filter((item) => !item.is_ranked).length,
      record_count: uniqueUniversities.length,
      fields: [
        "id",
        "name",
        "country",
        "country_code",
        "city",
        "rank",
        "is_ranked",
        "is_tied",
        "rank_label",
        "global_score",
        "enrollment",
        "url",
        "image_url",
      ],
    },
    universities: uniqueUniversities,
  };

  const csvCell = (value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const csv = [
    output.metadata.fields.join(","),
    ...uniqueUniversities.map((university) =>
      output.metadata.fields.map((field) => csvCell(university[field])).join(",")
    ),
  ].join("\n") + "\n";

  const download = (content, type, filename) => {
    const blob = new Blob([content], { type });
    const downloadUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = downloadUrl;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(downloadUrl);
  };

  download(
    `${JSON.stringify(output, null, 2)}\n`,
    "application/json",
    "2026-2027_USNews世界大学排名.json"
  );
  download(
    `\uFEFF${csv}`,
    "text/csv;charset=utf-8",
    "2026-2027_USNews世界大学排名.csv"
  );

  console.log(output.metadata);
  return output;
})();
