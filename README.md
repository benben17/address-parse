# 址衡 Address Engine

> 中文联系人信息结构化抽取与地址智能纠错服务

---

## 目录

- [项目简介](#项目简介)
- [核心能力](#核心能力)
- [系统架构](#系统架构)
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
- **行政区划索引仲裁**：以本地精确匹配结果为锚点，修正两个库的输出
- **直辖市标准化**：自动将 CPCA 返回的 `市辖区` / `县` 统一为 `北京市` 等标准名称
- **乡镇街道推断**：在确定省 / 市 / 区县后，进一步从详细地址中补全乡镇街道（含别名匹配）
- **路名 POI 回退**（可选功能，默认关闭）：通过路名关键词辅助确定区县

---

## 系统架构

```
POST /api/v1/parse
        │
        ▼
AddressExtractionService.parse_text()
        │
        ├─ 文本标准化（合并多余空白）
        │
        ├─ 电话抽取（正则 + JioNLP 归属地）
        │
        ├─ 姓名抽取
        │   ├─ 标签式规则
        │   ├─ 称谓 + 手机号紧邻模式
        │   └─ 前置姓名启发式推断
        │
        ├─ 地址文本净化（剥离姓名、电话片段）
        │
        └─ 地址解析 _parse_address()
            ├─ JioNLP.parse_location()
            ├─ CPCA.transform()
            ├─ AdminIndex 精确区划匹配
            ├─ 行政区冲突仲裁与纠错
            ├─ (可选) RoadPOI 路名回退
            ├─ TownIndex 乡镇街道推断
            └─ 置信度评估 & 输出组装
```

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

### 健康检查

```
GET /health
```

**响应示例**

```json
{
  "status": "ok",
  "project": "Address Engine"
}
```

---

### 解析联系人信息

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

**响应示例**

```json
{
  "project": "Address Engine",
  "text": "收件人张三，电话13800138000，地址广东省深圳市南山区科技园科苑路15号",
  "person": {
    "name": "张三",
    "source": "rule"
  },
  "phones": [
    {
      "number": "13800138000",
      "type": "手机",
      "province": "广东",
      "city": "深圳"
    }
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
    "needs_review": false,
    "warnings": [],
    "corrections": [],
    "alternatives": []
  }
}
```

**错误响应**

```json
{"error": "`text` must be a non-empty string"}
```

HTTP 状态码：`400`

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

系统在双引擎解析结果之上增加了一层自研仲裁逻辑，按优先级依次执行：

1. **精确区县反推省市**：若文本中存在唯一区县名且该区县仅属于一个省市，则以区县为锚点纠正错误的省 / 市前缀。
2. **精确城市反推省份**：若文本中存在唯一城市名且不存在有效区县，则以城市为锚点纠正错误的省份前缀。
3. **行政区冲突检测**：比较原文中出现的省市名与最终确定的省市，发现冲突时记录 `corrections`。如涉及城市级别纠正，则同时置 `needs_review=true`。
4. **区县模糊纠错**：在已确定省市的上下文中，对详细地址里的区县-级 token 做单字模糊匹配（相似度阈值 ≥ 0.66），纠正轻微错字（如"天和区"→"天河区"）。
5. **重名区县歧义拦截**：若同名区县属于多个省市且缺乏足够的上下文（省名、市名、双引擎推断），则仅返回区县名，置 `needs_review=true`，`alternatives` 列出所有候选，**不盲猜**。
6. **乡镇街道推断**：在确定区县后，从详细地址段提取乡镇 / 街道（支持简称 / 别名匹配）。
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

当前测试用例覆盖：

| 测试场景 | 验证内容 |
|---------|---------|
| 正常地址解析 | 省市区县 + 详细地址 + 无纠错标记 |
| 错误省份纠正（by 区县） | `corrections` 含 province 字段 |
| 错误城市纠正（by 区县） | `needs_review=true` + corrections 含 city 字段 |
| 直辖市标准化 | city == province（如"上海市"） |
| 轻微区县错字纠正 | 模糊匹配命中并记录 corrections |
| 重名区县歧义拦截 | province/city 为 null，alternatives 非空 |
| 错误前缀冲突（叠加省名） | auto_corrected=true |
| 路名缺区县回退（可选功能） | resolved_by == "road_fallback" |
| 不完整路名不强制解析 | needs_review=true，county 为 null |
| 乡镇推断（标准名 + 别名） | town 字段被填充，standardized 含乡镇 |
| 不将路名误拆为街道别名 | town 为 null |
| 无标签前置姓名识别 | name 被识别，source == "heuristic" |
| 复姓识别 | 欧阳 / 南宫等复姓正确识别 |
| 黑名单词过滤 | 客服 / 售后等不被识别为姓名 |
| 四字常见词不误识别为姓名 | name 为 null |
| 称谓前置姓名识别（王先生） | name == "王先生"，从地址段中移除 |
| 路名 POI 冲突纠正区县 | resolved_by == "road_conflict_correction" |
| 路名 POI 补全城市和区县 | 省市区均被纠正 |

---

## Docker 部署

### 构建并启动

```bash
docker compose up -d --build
```

服务地址：`http://127.0.0.1:8000`

> **说明**：Dockerfile 在构建阶段预先执行 `import jionlp` 以解压词典文件，避免容器首次启动时因词典解压造成的延迟或权限报错。

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

- **JioNLP 词典权限**：`jionlp` 首次 import 会在安装目录解压词典，若安装在只读路径（如系统 Python）会报权限错误。推荐始终使用项目本地 `.venv`，或使用 Docker 镜像（构建时已预解压）。
- **CPCA 直辖市**：CPCA 对北京、上海、天津、重庆会返回 `市辖区` / `县` 作为城市字段，服务已内置标准化逻辑统一处理。
- **区县重名**：如"鼓楼区"同时存在于南京、福州、开封，在缺少省市上下文时，系统只返回区县名和候选列表，**不会盲猜**。
- **路名 POI 回退**：该功能默认关闭（`enable_road_poi_fallback=False`），仅在有内置路名关键词库的条件下有意义，且命中时会置 `needs_review=False`，请根据业务精度要求决定是否启用。
- **置信度仅供参考**：`confidence` 由解析深度和来源综合评估，不等同于地址绝对正确。建议高价值业务场景对 `needs_review=true` 的记录进行人工二次核查。
