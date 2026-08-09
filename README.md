# EduScore

EduScore 是面向 HR 的候选人学历数据与可解释评分项目。当前仓库先建立可追溯的院校基础数据，后续评分规则见 `docs/学历评分方案.md`。

## 数据集

| 数据集 | 记录数 | 格式 |
| --- | ---: | --- |
| 中国普通高校名单 | 2,952 | CSV、JSON、原始 XLS |
| 中国成人高校名单 | 244 | CSV、JSON、原始 XLS |
| 中国留服认证院校名单 | 7,574 | CSV、JSON、JSONL |
| 2027 QS 世界大学排名 | 1,504 | CSV、JSON、原始 XLSX |

CSV 文件使用 UTF-8 with BOM；学校标识码等标识字段按字符串保存，避免科学计数法和精度损失。

## 官方数据源

- 中国留学服务中心“认证院校查询”：https://yxcx.cscse.edu.cn/rzyxmd2
- 中华人民共和国教育部“全国高等学校名单”（2026-06-18）：http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202606/t20260618_1441074.html

教育部页面说明，截至 2026 年 6 月 17 日，全国高等学校共 3,196 所，其中普通高校 2,952 所、成人高校 244 所；本仓库保留页面附件原始文件并提供规范化版本。

当前中国留服快照抓取于 2026-08-09。查询结果是认证业务的院校查询信息，不等同于对院校质量的排名或永久认证承诺。数据可能更新，使用时应记录抓取时间，并保留 `review_note` 等审查提示。

QS 数据来自仓库内提供的原始工作簿。原文件明确提示仅供参考，决策时应与 QS 网站及对应排名说明交叉核对；在 HR 评分中不应把综合排名作为唯一或决定性依据。

## 重新生成

```bash
python3 scripts/extract_xls.py data/sources/中国普通高校名单.xls data 中国普通高校名单
python3 scripts/extract_xls.py data/sources/中国成人高校名单.xls data 中国成人高校名单
node scripts/fetch_cscse_schools.mjs data
python3 scripts/convert_qs_ranking.py
```

`extract_xls.py` 在 macOS 上通过 Microsoft Excel 只读提取旧版 `.xls`。QS 转换仅使用 Python 标准库读取 `.xlsx` 内部 XML。
