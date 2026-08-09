# 数据目录与来源

本目录保存“中国及世界大学汇总”的来源数据、规范化结果和最终汇总表。所有 CSV 使用 UTF-8 with BOM；学校代码等标识字段按字符串处理。

## 目录

```text
data/
├── master/                         # 最终交付文件
│   ├── 国内头部大学汇总.csv
│   ├── 国内非头部大学汇总.csv
│   ├── 国外头部大学汇总.csv
│   ├── 国外非头部大学汇总.csv
│   └── 国外大学排名匹配审计.json
├── china/
│   ├── moe/                        # 教育部普通、成人高校名单及原始 XLS
│   └── shanghairanking/            # 软科全部院校、分类 JSON、CSV、元数据
├── international/
│   └── cscse/                      # 中国留服认证院校查询快照
└── rankings/
    ├── qs/                         # 2027 QS 排名及原始 XLSX
    └── usnews/                     # 2026-2027 US News 排名
```

## 最终汇总

### 国内头部大学汇总

`master/国内头部大学汇总.csv` 共 590 行，字段为：

- `中文名`
- `外文名`
- `软科排名`
- `985`
- `211`
- `双一流`

该表保持软科页面前 590 条的顺序和源站 `rankBcur` 排名，例如综合、医药、财经等不同类别的排名标签。985、211、双一流由软科源数据的 `charCode` 标签生成。

### 国内非头部大学汇总

`master/国内非头部大学汇总.csv` 共 2,381 行，字段为：

- `中文名`
- `外文名`
- `软科排名`
- `独立学院`
- `民办高校`

该表包含软科院校库第 591 条起的院校，软科排名统一留空，按中文名的 `zh_CN.UTF-8` 拼音排序规则排列。独立学院和民办高校由源数据的 `charCode` 标签生成。

按产品表结构要求，本表不展示 985、211、双一流列。需注意，软科源数据第 591 条以后仍包含少量具有这些标签的特殊类别或军事院校，因此“未展示”不等同于源标签为否；完整标签仍保留在 `china/shanghairanking/全部高校.json`。

### 国外头部大学汇总

`master/国外头部大学汇总.csv` 共 2,250 行，字段为：

- `中文名`
- `外文名`
- `USNEWS`
- `QS`

该表只包含带 US News 名次的院校，按名次升序，同名次保持 US News 页面顺序，并补充 QS 名次和中文名。

### 国外非头部大学汇总

`master/国外非头部大学汇总.csv` 共 7,143 行，字段为：

- `中文名`
- `外文名`
- `QS`

该表包含 US News 收录但未给出名次的院校，以及仅在 QS 或中国留服中出现的院校，按规范化外文名排序。两张国外表合计 9,393 行，其中 1,504 行带 QS 名次、8,017 行带中文名。

匹配方式和无中文名统计见 `master/国外大学排名匹配审计.json`。无中文名不一定表示漏抓，可能是中留服快照未收录、排名使用了校区名称或两边正式名称不同。

合并时保留全部来源记录，包括中国大陆学校。中文名优先采用中国留服；中国大陆院校在英文名精确一致时由软科补充中文名。排名区间如 `601-650`、`1401+` 保持源值，不转换成虚构的单一名次。

名称匹配依次使用规范化精确匹配、国家一致的高置信模糊匹配和保守的歧义拦截。同名但国家、校区或方向词不同的记录不会仅因字符串相似而合并。

## 数据源

### 中华人民共和国教育部

- 数据：全国普通高等学校名单、全国成人高等学校名单
- 页面：http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202606/t20260618_1441074.html
- 发布日期：2026-06-18
- 统计口径：截至 2026-06-17，普通高校 2,952 所、成人高校 244 所，不含港澳台地区高校
- 原始附件：`china/moe/sources/*.xls`

转换脚本：`scripts/extract_xls.py`。转换时提取省级地区、规范序号，并把学校标识码保存为精确的 10 位字符串。

### 中国留学服务中心

- 数据：认证院校查询快照
- 查询页：https://yxcx.cscse.edu.cn/rzyxmd2
- API：https://yxcx.cscse.edu.cn/api/xlxwrzz/xlxwrz/getUniversityListOrPage
- 当前快照：7,574 所，抓取时间见 `international/cscse/中国留服认证院校名单.metadata.json`

查询结果用于院校名称和认证业务检索，不代表对院校质量的排名或永久认证承诺。应保留 `review_note` 等源站审查提示。

### 软科

- 数据：中国院校库及双一流、985、211、合作办学、民办、独立学院分类
- 页面：https://www.shanghairanking.cn/institution?name=&c=0&r=0&l=0&e=0
- 当前快照：全部院校 2,971 所；双一流 147、985 39、211 115、合作办学 16、民办 679、独立学院 148
- 元数据：`china/shanghairanking/软科院校库.metadata.json`

抓取脚本：`scripts/fetch_shanghairanking_universities.js`。分类标签适合作为可解释特征，但不应把历史政策标签直接等同于当前办学质量。

### QS

- 数据：2027 QS World University Rankings
- 页面：https://www.topuniversities.com/world-university-rankings
- 当前快照：1,504 所
- 原始工作簿：`rankings/qs/sources/2027_QS世界大学排名原始数据.xlsx`

原始工作簿声明仅供参考，实际决策应与 QS 网站及当期排名说明交叉核对。转换脚本：`scripts/convert_qs_ranking.py`。

### U.S. News & World Report

- 数据：2026-2027 Best Global Universities Rankings
- 页面：https://www.usnews.com/education/best-global-universities/rankings
- 当前快照：2,604 所，其中 2,250 所有名次、354 所未排名
- 抓取时间：见 `rankings/usnews/2026-2027_USNews世界大学排名.json` 元数据

抓取脚本：`scripts/fetch_usnews_global_rankings.js`，需在排名页面的浏览器开发者工具 Console 中运行。

## 重新生成

```bash
python3 scripts/extract_xls.py data/china/moe/sources/中国普通高校名单.xls data/china/moe 中国普通高校名单
python3 scripts/extract_xls.py data/china/moe/sources/中国成人高校名单.xls data/china/moe 中国成人高校名单
node scripts/fetch_cscse_schools.mjs
node scripts/fetch_shanghairanking_universities.js
python3 scripts/convert_qs_ranking.py
python3 scripts/build_university_summaries.py
```

US News 数据需要按上一节说明在浏览器中重新抓取，再运行汇总脚本。
