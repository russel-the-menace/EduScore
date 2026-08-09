# 数据目录与来源

本目录保存“中国及世界大学汇总”的来源数据、规范化结果和最终汇总表。所有 CSV 使用 UTF-8 with BOM；学校代码等标识字段按字符串处理。

## 目录

```text
data/
├── master/                         # 核心交付文件，仅 CSV
│   ├── 国内头部大学汇总.csv
│   ├── 国内非头部大学汇总.csv
│   ├── 国外头部大学汇总.csv
│   └── 国外非头部大学汇总.csv
├── audit/                          # 匹配过程与结果审计
│   ├── 国外大学排名匹配审计.json
│   └── QS中文名回填审计.json
├── china/
│   ├── moe/                        # 教育部普通、成人高校名单及原始 XLS
│   └── shanghairanking/            # 软科全部院校、分类 JSON、CSV、元数据
├── international/
│   ├── cscse/                      # 中国留服认证院校查询快照
│   └── greater_china/              # 港澳台院校中英文对照
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

该表只包含带 US News 名次的院校，按名次升序，同名次保持 US News 页面顺序，并补充 QS 名次。中文名先清空后重新匹配，优先级为港澳台人工对照、软科中国院校库、中留服英文名匹配、DeepSeek 补充。首轮英文匹配后，再为未进入头部表的 QS 院校生成中文名，并按中文名、国家及高置信英文别名回填 QS。

### 国外非头部大学汇总

`master/国外非头部大学汇总.csv` 共 6,171 行，字段为：

- `中文名`
- `外文名`
- `QS`

该表以中国留服名单为基准，按中文名排除已经出现在国外头部表中的院校，再按规范化外文名排序。两张国外表合计 8,421 行，全部带中文名；头部表 1,194 行带 QS 名次，非头部表 125 行带 QS 名次。

匹配统计见 `audit/国外大学排名匹配审计.json`。DeepSeek 处理前的未匹配记录和生成结果分别保存在 `international/generated/DeepSeek待补中文名.json` 与 `international/generated/DeepSeek补充中文名.json`；最终待补文件为空，模型补充结果共 883 行。

QS 二次回填的 493 条中文名保存在 `international/generated/DeepSeek_QS补充中文名.json`，逐条结果见 `audit/QS中文名回填审计.json`：其中 183 条回填头部表，306 条未找到安全对应项，4 条经人工确认属于不同学校或校区后排除。人工修正和排除规则保存在 `international/greater_china/QS院校中文名人工修正.csv` 与 `international/greater_china/QS错误匹配排除.csv`。模型生成名称不是权威数据源，涉及正式业务决策时仍应人工抽查。

头部表保留 US News 的全部有名次记录，包括中国大陆学校。中文名优先采用港澳台对照；中国大陆院校以软科英文名精确匹配；其余院校再匹配中国留服。排名区间如 `601-650`、`1401+` 保持源值，不转换成虚构的单一名次。

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

### 港澳台院校中英文对照

- 香港：香港教育局“专上院校”页面，https://www.edb.gov.hk/tc/edu-system/postsecondary/local-higher-edu/institutions/index.html
- 澳门：澳门特别行政区政府实体名录“高等教育”分类，https://www.bo.dsaj.gov.mo/cn/entities/priv/cat/tertiary
- 台湾：uniRank 台湾院校 A-Z 名录，https://www.unirank.org/tw/a-z/
- 整理结果：`international/greater_china/港澳台院校中英文对照.csv`

当前整理结果共 64 所，其中香港 22 所、澳门 10 所、台湾 32 所。香港和澳门来源为当地政府网站；台湾来源为第三方院校目录，不等同于台湾教育主管部门的官方完整名单。表内 `英文别名` 用于处理冠词、省略词、Macau/Macao 拼写及排名网站常见简称，不替代来源中的正式外文名。

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
DEEPSEEK_API_KEY=... python3 scripts/fill_chinese_names_with_deepseek.py
python3 scripts/build_university_summaries.py
DEEPSEEK_API_KEY=... python3 scripts/fill_chinese_names_with_deepseek.py \
  --pending DeepSeek_QS待补中文名.json \
  --output DeepSeek_QS补充中文名.json
python3 scripts/build_university_summaries.py
```

US News 数据需要按上一节说明在浏览器中重新抓取，再运行汇总脚本。
