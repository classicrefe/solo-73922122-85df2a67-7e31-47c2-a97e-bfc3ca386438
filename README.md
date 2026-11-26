# 骑马钉返印 API

印房返印骑马钉小册时复用旧印张的排程服务。提交新版页序和旧印张，服务自动拼版、
择优分配旧纸、生成返印单，并支持派工确认完工与报废重排。

- FastAPI + SQLite（标准库 `sqlite3`，JSON 存嵌套数据）
- 纯 Python 精确求解分配（位掩码 DP），无外部求解器

## 业务规则

**拼版**：新版页序在末尾补白凑足 4 的倍数，再按骑马钉从外到内拼版。
第 `i` 张（`i` 从 0 开始，0 为最外，页码从 1 开始，共 `N` 页）：

| | 左页 | 右页 |
|---|---|---|
| 正面（折后外侧） | `N-2i` | `2i+1` |
| 背面 | `2i+2` | `N-2i-1` |

**旧纸复用**：旧纸按原朝向使用（正反面、左右不可对调），每张至多一次；
已印面的左右页须与该位置新版拼版完全一致，未印面不限、按新版内容补印；
纯空白面免印。

**优化目标**：先尽量少用新纸（尽量多复用）；新纸用量相同时，选待印面总数
最少的方案。重排时在目标值相同的情况下尽量不动原安排。

**派工与完工**：每个位置签发一个派工号；完工凭该位置当前有效派工确认
（重复确认幂等）。报废未完工的旧纸后自动重排：已完工的纸留在原位；被改派
位置的旧派工退回（再凭它确认返回 409），并签发新派工；未改派位置保留原
派工，仍可按原安排确认。

## 运行

### Docker Compose（推荐）

```bash
docker compose up --build
# API: http://localhost:8000  文档: http://localhost:8000/docs
```

SQLite 数据落在命名卷 `reprint-data`（容器内 `/data/app.db`）。

### 本地开发

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload        # 数据在 ./data/app.db（可用 DB_PATH 覆盖）
pytest                               # 运行测试
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/work-orders` | 提交新版页序与旧印张，生成返印单（201） |
| `GET` | `/work-orders` | 工单列表（含汇总） |
| `GET` | `/work-orders/{oid}` | 工单当前状态 / 返印单 |
| `POST` | `/work-orders/{oid}/positions/{i}/confirm` | 凭派工号确认位置 `i` 完工 |
| `POST` | `/work-orders/{oid}/scrap` | 报废旧印张并重排 |

### 创建工单

```bash
curl -X POST http://localhost:8000/work-orders \
  -H 'Content-Type: application/json' -d '{
  "pages": ["COVER", "P2", "P3", "P4", "P5"],
  "old_sheets": [
    {"id": "S1", "front": {"left": null, "right": "COVER"}, "back": null},
    {"id": "S2", "front": null, "back": {"left": "P4", "right": "P5"}},
    {"id": "S3", "front": {"left": "OLD", "right": "STUFF"}, "back": null}
  ]}'
```

- `pages`：1–48 项，内容编号可重复；`null` 表示空白页；数字编号会规整为字符串。
- `old_sheets`：至多 40 张；`front`/`back` 为折后外侧正面与背面，`null` 表示该面未印。

响应（节选）：`positions` 从外到内列出每个位置——`use` 为旧纸编号或 `NEW`
（领新纸），`faces_to_print` 为还要印的面，`dispatch_id` 为该位置派工号；
`summary` 给出新纸用量与待印面数。

### 确认完工

```bash
curl -X POST http://localhost:8000/work-orders/$OID/positions/0/confirm \
  -H 'Content-Type: application/json' -d '{"dispatch_id": "<位置0的dispatch_id>"}'
```

### 报废重排

```bash
curl -X POST http://localhost:8000/work-orders/$OID/scrap \
  -H 'Content-Type: application/json' -d '{"sheet_ids": ["S2"]}'
```

响应中的 `returned_dispatches` 列出被改派位置及其已退回的旧派工号。

### 错误码

`404` 工单/位置/派工/旧印张不存在；`409` 派工不属于该位置、旧派工已退回、
报废已完工或已报废的旧纸；`422` 请求体校验失败（页数/张数超限、编号重复等）。

## 演示

启动服务后执行（需本机有 `python3` 解析 JSON）：

```bash
./demo.sh                  # 或 ./demo.sh http://localhost:8000
```

演示完整流程：建单 → 位置 0 派工确认 → 报废 S2 重排 → 旧派工确认被退回（409）
→ 新派工确认 → 纯空白面免印示例。

## 结构

```
app/
  imposition.py   补白 + 骑马钉拼版
  planner.py      旧纸分配优化（位掩码 DP：先最少新纸，再最少待印面）
  service.py      建单 / 确认 / 报废重排业务逻辑
  db.py           SQLite 连接与建表
  schemas.py      请求校验（Pydantic）
  main.py         FastAPI 路由
tests/            pytest（拼版、优化器、端到端 API）
demo.sh           可演示的 API 请求脚本
```

## 限制

- 单进程 SQLite，适合单店/单机等场景；未做鉴权。
- 内容编号按字符串精确匹配（数字会规整为字符串，如 `1` 与 `"1"` 视为同一编号）。
