# 址衡 Address Engine

> 中文联系人信息结构化抽取与地址智能纠错服务

---

## 目录

- [项目简介](#项目简介)
- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [解析流程](#解析流程)
- [基础数据](#基础数据)
- [快速开始](#快速开始)
- [API 文档](#api-文档)
- [输出字段说明](#输出字段说明)
- [纠错策略详解](#纠错策略详解)
- [测试](#测试)
- [Docker 部署](#docker-部署)
- [依赖说明](#依赖说明)
- [已知边界与注意事项](#已知边界与注意事项)

---

## 项目简介

**址衡 Address Engine** 是一个基于 Flask 的轻量级中文收件信息解析服务，专为电商、物流、CRM 等场景设计。

它能从一段非结构化的自由文本中，同时提取：

- **收件人姓名**（支持标签式、前置无标签、称谓前置、复姓等多种形式）
- **手机号 / 固定电话**（含归属地省市和号码类型）
- **省 / 市 / 区县 / 乡镇街道 / 详细地址**（含标准化拼接结果）

与此同时，服务内置多层地址智能纠错逻辑，能自动处理错误省市前缀、轻微区县错字、重名区县歧义等常见脏数据问题，并在输出中标注纠正记录和置信度，满足批处理和审计场景的追溯需求。

此外，项目引入了自维护的**标准行政区划基础数据**，支持对最新行政区划和前端省市区联动的级联查询，为地址抽取提供高置信度的本地判断依据。

---

## 核心能力

### 姓名抽取

| 场景 | 示例输入 | 识别结果 |
|------|---------|---------|
| 标签式（收件人 / 联系人等） | `收件人张三，...` | `张三` |
| 无标签前置姓名 + 地址上下文 | `张三 上海市徐汇区...` | `张三` |
| 称谓前置（姓名紧邻手机号） | `王先生13511112222` | `王先生` |
| 复姓 | `欧阳娜娜 上海市...` | `欧阳娜娜` |
| 黑名单过滤 | `客服 上海市...` | `null` |
| 四字常见词过滤 | `王者荣耀 上海市...` | `null` |

### 电话抽取

- 支持大陆手机号（1[3-9]xxxxxxxxx）和固话（区号 + 号码）
- 自动去重，多号码按出现顺序排列
- 每个号码附带 JioNLP 归属地查询结果（省、市、类型）

### 地址解析与纠错

- **双引擎**：JioNLP（自由文本解析）+ CPCA（省市区抽取）
- **基础数据强校验**：结合本地自维护的标准省市区镇（`data/clean`）四级维度判定区划唯一性，大幅提升纠正鲁棒性
- **行政区划索引仲裁**：以本地精确匹配结果为锚点，修正两个库的输出
- **直辖市标准化**：自动将 CPCA 返回的 `市辖区` / `县` 统一为 `北京市` 等标准名称
- **乡镇街道推断**：在确定省 / 市 / 区县后，进一步从详细地址中补全乡镇街道（含别名匹配）
- **路名 POI 回退**（可选功能，默认关闭）：通过路名关键词辅助确定区县

### 基础数据支撑

- **省市区镇字典树查询**：为前端提供标准省、市、区（县）、镇（乡/街道）四级级联数据源。

---

## 系统架构

```
POST /api/v1/parse                                   GET /api/v1/regions/tree
        │                                                     │
        ▼                                                     ▼
AddressExtractionService.parse_text()               RegionTreeService.build_tree()
        │                                                     │
        ├─ 电话抽取与正则化                                   ├─ 读取 data/clean 基础数据
        │                                                     │
        ├─ 姓名抽取                                           └─ 组装指定层级的行政区划树
        │
        └─ 地址解析 _parse_address()
            ├─ JioNLP & CPCA 双引擎解析
            ├─ AdminIndex 基于本地数据的精确区划匹配 ◀━━━ [本地基础数据 data/clean]
            ├─ 行政区冲突仲裁与纠错                      (provinces/cities/counties/towns.csv)
            ├─ (可选) RoadPOI 路名回退
            ├─ TownIndex 乡镇街道推断
            └─ 置信度评估 & 输出组装
```

---

## 解析流程

`/api/v1/parse` 的处理链路采用“规则优先 + 本地数据校验 + 模型解析补充”的方式，目标是优先保证 `人名 / 电话 / 省 / 市 / 区县 / 镇街 / 详细地址` 的稳定性和可解释性。

### 1. 文本预处理

- 统一空白、标点和常见噪声字符
- 保留原文，生成可解析文本副本
- 对姓名、电话等高干扰片段做后续剥离准备

### 2. 电话抽取

- 用正则优先识别手机号、固话
- 对号码去重并保持出现顺序
- 调用 `JioNLP` 补充号码类型及归属地信息

### 3. 姓名抽取

- 先走标签规则，如 `收件人`、`联系人`
- 再走“称谓 + 手机号紧邻”规则，如 `王先生135...`
- 最后走无标签启发式识别，并结合黑名单降低误判

### 4. 地址净化

- 从原文本中剥离已识别的电话和姓名
- 保留真正参与地址解析的净化文本
- 避免姓名撞地名、电话落入详细地址

### 5. 地址解析

- `JioNLP` 解析自由文本地址
- `CPCA` 抽取省市区信息
- `AdminIndex` 基于 `data/clean` 做本地省市区精确匹配、别名匹配和模糊纠错
- `TownIndex` 在已确定区县后补全镇/街道

### 6. 冲突仲裁与纠错

- 处理错误省市前缀、区县冲突、轻微错别字
- 结合本地基础数据判断能否自动纠正
- 无法高置信确认时返回 `needs_review=true`

### 7. 输出组装

- 返回统一结构：`code + data`
- `data` 内保留原有字段：`person`、`phones`、`address`
- `address` 内继续返回 `province / city / county / town / detail` 以及纠错元信息

---

## 基础数据

系统引入了详尽的高质量行政区划基础数据集，文件位于 `data/clean/` 目录下：

- **provinces.csv**：标准省份 / 直辖市信息及简称、别名映射
- **cities.csv**：标准城市信息
- **counties.csv**：标准区县信息（用于消歧、反推补全与匹配验证）
- **towns.csv**：全国范围的镇、街道、乡细颗粒度数据（用于在提取完成后对详细地址进行街道截取判定）
- **city_telcodes.csv**：国内城市电话区号数据辅助
- **quality_report.json**：数据清洗的特征和记录条数报告

**特点：** 这些数据均为结构化 CSV 格式，并附带诸如 `disabled/enabled` 开关、别名和短名支持，是本系统强力纠错策略得以实现的核心。

---

## 快速开始

### 本地运行

```bash
# 创建虚拟环境并安装依赖
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 启动开发服务器（端口 5000）
.venv/bin/flask --app app.api run --debug
```

或直接运行入口脚本：

```bash
.venv/bin/python run.py
```

### PyCharm 配置

1. 解释器选择项目本地 `.venv`
2. 运行目标选择根目录 `run.py`，Working Directory 设为项目根目录
3. 可选：配置模块方式运行 `python -m app`

---

## API 文档

### 1. 健康检查

```
GET /health
```

**响应示例**

```json
{
  "code": 200,
  "status": "ok",
  "project": "Address Engine"
}
```

---

### 2. 解析联系人信息

```
POST /api/v1/parse
Content-Type: application/json
```

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 待解析的自由文本，不能为空 |

**请求示例**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/parse \
  -H 'Content-Type: application/json' \
  -d '{"text":"收件人张三，电话13800138000，地址广东省深圳市南山区科技园科苑路15号"}'
```

**响应示例** (截取地址部分)

```json
{
  "code": 200,
  "data": {
    "project": "Address Engine",
    "text": "收件人张三，电话13800138000，地址广东省深圳市南山区科技园科苑路15号",
    "person": { "name": "张三", "source": "rule" },
    "phones": [
      { "number": "13800138000", "type": "手机", "province": "广东", "city": "深圳" }
    ],
    "address": {
      "raw": "收件人张三，电话13800138000，地址广东省深圳市南山区科技园科苑路15号",
      "parsed_text": "广东省深圳市南山区科技园科苑路15号",
      "province": "广东省",
      "city": "深圳市",
      "county": "南山区",
      "town": null,
      "detail": "科技园科苑路15号",
      "standardized": "广东省深圳市南山区科技园科苑路15号",
      "confidence": "high",
      "resolved_by": "exact_county",
      "auto_corrected": false,
      "needs_review": false
    }
  }
}
```

**错误响应**

HTTP 状态码：`400`

```json
{"code": 400, "error": "`text` must be a non-empty string"}
```

---

### 3. 获取标准行政区划树 (级联数据)

为前端提供多级联动区划数据，可直接用于 `省 -> 市 -> 区县 -> 镇/街道` 下拉选择。数据来源于项目内置的 `data/clean` 目录。

```
GET /api/v1/regions/tree
```

**查询参数（Query Params）**

| 参数名 | 类型 | 说明 | 联动逻辑 |
|--------|------|------|---------|
| `province` | string | *(可选)* 省/直辖市名称 | 传空时返回全国各省级节点列表 |
| `city`     | string | *(可选)* 城市名称 | 依赖 `province`，传入时返回该市下属区县级联 |
| `county`   | string | *(可选)* 区县名称 | 依赖前两者，传入时返回下属乡镇/街道级联 |

**查询规则**

- 不传参数：返回全部省级节点
- 只传 `province`：返回该省及其下属市节点
- 传 `province + city`：返回该市及其下属区县节点
- 传 `province + city + county`：返回该区县及其下属镇/街道节点

**请求示例**（获取上海市 / 上海市 / 青浦区 下属镇街）

```bash
curl "http://127.0.0.1:8000/api/v1/regions/tree?province=上海市&city=上海市&county=青浦区"
```

**响应示例**

```json
{
  "code": 200,
  "level": "town",
  "filters": {
    "province": "上海市",
    "city": "上海市",
    "county": "青浦区"
  },
  "tree": [
    {
      "label": "上海市",
      "value": "上海市",
      "code": "310000",
      "level": "province",
      "children": [
        {
          "label": "上海市",
          "value": "上海市",
          "code": "direct-12",
          "level": "city",
          "children": [
            {
              "label": "青浦区",
              "value": "青浦区",
              "code": "12017",
              "level": "county",
              "children": [
                { "label": "徐泾镇", "value": "徐泾镇", "code": "1201703", "level": "town", "children": [] }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**错误响应**

直接传 `city` 但未传 `province` 时，HTTP 状态码：`400`

```json
{"code": 400, "error": "`city` requires `province`."}
```

区划不存在时，HTTP 状态码：`400`

```json
{"code": 400, "error": "Province `不存在省份` not found."}
```

---

## 输出字段说明

### `person` 对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string \| null | 识别到的姓名，未识别则为 null |
| `source` | string | 识别来源：`rule`（标签/称谓规则）或 `heuristic`（启发式推断） |

### `phones` 数组（每项）

| 字段 | 类型 | 说明 |
|------|------|------|
| `number` | string | 号码（已去除空格） |
| `type` | string \| null | 号码类型（手机 / 固话等） |
| `province` | string \| null | 归属省份 |
| `city` | string \| null | 归属城市 |

### `address` 对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `raw` | string | 原始输入文本 |
| `parsed_text` | string | 剥离姓名 / 电话后的地址净化文本 |
| `province` | string \| null | 省/直辖市 |
| `city` | string \| null | 市/地区 |
| `county` | string \| null | 区/县/旗 |
| `town` | string \| null | 乡镇/街道 |
| `detail` | string \| null | 详细地址（街路门牌楼层等） |
| `standardized` | string \| null | 标准化拼接地址 |
| `confidence` | string | 置信度：`high` / `medium` / `low` |
| `resolved_by` | string | 解析来源（见下表） |
| `auto_corrected` | boolean | 是否发生了自动纠正 |
| `needs_review` | boolean | 是否建议人工复核 |
| `warnings` | string[] | 风险说明列表 |
| `corrections` | object[] | 纠正记录，每条含 `field` / `from` / `to` / `reason` |
| `alternatives` | object[] | 区县重名时的候选地址列表 |

### `resolved_by` 取值

| 取值 | 含义 |
|------|------|
| `exact_county` | 区县名称唯一精确匹配 |
| `exact_county_disambiguated` | 区县重名经上下文消歧后确定 |
| `exact_city` | 城市名称唯一精确匹配 |
| `exact_city_disambiguated` | 城市重名经上下文消歧后确定 |
| `jionlp_cpca_consensus` | JioNLP 与 CPCA 双引擎结果一致 |
| `jionlp` | 仅由 JioNLP 支撑 |
| `cpca` | 仅由 CPCA 支撑（置信度较低，标记 `needs_review`） |
| `fuzzy_county` | 区县轻微错字经模糊纠正 |
| `road_fallback` | 路名 POI 回退补全区县（需启用可选功能） |
| `road_conflict_correction` | 路名 POI 与现有区县冲突，执行了纠正 |
| `jionlp_multi_county` | 文本含多区县，采用 JioNLP 结果消歧 |
| `none` | 未能解析出任何行政区划 |

---

## 纠错策略详解

系统在双引擎解析结果之上，强依赖本地基础数据库（`data/clean`），增加了一层自研仲裁逻辑，按优先级依次执行：

1. **精确区县反推省市**：若文本中存在唯一区县名且该区县仅属于一个省市，则以区县为锚点纠正错误的省 / 市前缀。
2. **精确城市反推省份**：若文本中存在唯一城市名且不存在有效区县，则以城市为锚点纠正错误的省份前缀。
3. **行政区冲突检测**：比较原文中出现的省市名与最终确定的省市，发现冲突时记录 `corrections`。如涉及城市级别纠正，则同时置 `needs_review=true`。
4. **区县模糊纠错**：在已确定省市的上下文中，对详细地址里的区县-级 token 做单字模糊匹配（相似度阈值 ≥ 0.66），纠正轻微错字（如"天和区"→"天河区"）。
5. **重名区县歧义拦截**：若同名区县属于多个省市且缺乏足够的上下文（省名、市名、双引擎推断），则仅返回区县名，置 `needs_review=true`，`alternatives` 列出所有候选，**不盲猜**。
6. **乡镇街道推断**：在确定区县后，使用内置的 `towns.csv` 从详细地址段提取确切的乡镇 / 街道（支持简称 / 别名精准匹配）。
7. **路名 POI 回退**（可选，默认关闭）：通过预置路名关键词库辅助确定区县，适用于仅有路名无明确区县的输入。启用方式：实例化时传入 `enable_road_poi_fallback=True`。

---

## 置信度规则

| 条件 | 置信度 |
|------|------|
| 省 + 市 + 区县均已确定，且来源非 CPCA 单引擎，且无 `needs_review` | `high` |
| 省 + 市已确定（含 `needs_review` 情形） | `medium` |
| 仅有区县或完全无法解析 | `low` |

---

## 测试

```bash
.venv/bin/python -m pytest
```

---

## Docker 部署

### 构建并启动

```bash
docker compose up -d --build
```

服务地址：`http://127.0.0.1:8000`

> **说明**：Dockerfile 在构建阶段预先执行 `import jionlp` 以解压词典文件，避免容器首次启动时因词典解压造成的延迟或权限报错。本地挂载的 `data/` 目录亦会被加载入内核构建寻址。

### 停止服务

```bash
docker compose down
```

### 生产参数（Gunicorn）

| 参数 | 值 |
|------|-----|
| 绑定地址 | `0.0.0.0:8000` |
| Worker 数 | 2 |
| Thread 数 | 2 |
| 超时时间 | 120s |

### 健康检查

容器内置健康检查，每 30 秒探测一次 `/health` 端点，失败 3 次后标记为 `unhealthy`。

---

## 依赖说明

| 依赖 | 版本 | 作用 |
|------|------|------|
| Flask | 3.1.3 | HTTP 服务框架 |
| jionlp | 1.5.27 | 中文地址 NLP 解析（含电话归属地） |
| cpca | 0.5.5 | 省市区抽取 |
| gunicorn | 23.0.0 | 生产环境 WSGI 服务器 |
| pytest | 9.0.2 | 单元测试框架 |

---

## 已知边界与注意事项

- **JioNLP 词典权限**：`jionlp` 首次 import 会在安装目录解压词典，若安装在只读路径会报权限错误。推荐使用项目本地 `.venv`。
- **CPCA 直辖市**：CPCA 对直辖市会返回 `市辖区` / `县` 作为城市，服务内部已通过 `data/` 结合将其标准化统一处理。
- **区县重名不盲猜**：同名区县（如"鼓楼区"）在缺少省市上下文时只返回区县名及候选列表。
- **本地行政数据结构缓存**：系统在初始化 `AddressExtractionService` 以及 `RegionTreeService` 时会将对应的 CSV 内容读入内存构建字典，如果直接在物理磁盘更新 CSV 源文件，需要重启应用服务才能生效。
