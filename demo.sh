#!/usr/bin/env bash
# 演示骑马钉返印 API 的完整流程：
#   建单(5 页新版 + 3 张旧印张) → 位置 0 派工确认完工 → 报废 S2 重排
#   → 旧派工确认被退回 → 新派工确认 → 纯空白面免印示例
# 用法: ./demo.sh [base_url]   （默认 http://localhost:8000，需本机有 python3 用于解析 JSON）
set -euo pipefail
BASE="${1:-http://localhost:8000}"

pick() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
show() { python3 -m json.tool --no-ensure-ascii 2>/dev/null || cat; }

echo "== 0. 健康检查 =="
curl -sS "$BASE/health" | show

echo
echo "== 1. 创建工单：新版 5 页（补白到 8 页，2 张印张）+ 3 张旧印张 =="
RESP=$(curl -sS -X POST "$BASE/work-orders" -H 'Content-Type: application/json' -d '{
  "pages": ["COVER", "P2", "P3", "P4", "P5"],
  "old_sheets": [
    {"id": "S1", "front": {"left": null, "right": "COVER"}, "back": null},
    {"id": "S2", "front": null, "back": {"left": "P4", "right": "P5"}},
    {"id": "S3", "front": {"left": "OLD", "right": "STUFF"}, "back": null}
  ]}')
echo "$RESP" | show
OID=$(echo "$RESP" | pick "d['work_order_id']")
D0=$(echo "$RESP" | pick "d['positions'][0]['dispatch_id']")
D1_OLD=$(echo "$RESP" | pick "d['positions'][1]['dispatch_id']")
echo "--> 位置 0 用旧纸 S1（只需补印背面），位置 1 用旧纸 S2（只需补印正面），S3 配不上未用，新纸 0 张"

echo
echo "== 2. 位置 0 凭派工确认完工 =="
curl -sS -X POST "$BASE/work-orders/$OID/positions/0/confirm" \
  -H 'Content-Type: application/json' -d "{\"dispatch_id\": \"$D0\"}" | show

echo
echo "== 3. 报废未完工的旧纸 S2，自动重排（完工的 S1 留在原位） =="
RESP=$(curl -sS -X POST "$BASE/work-orders/$OID/scrap" \
  -H 'Content-Type: application/json' -d '{"sheet_ids": ["S2"]}')
echo "$RESP" | show
D1_NEW=$(echo "$RESP" | pick "d['positions'][1]['dispatch_id']")
echo "--> 位置 1 改领新纸（正背面都要印），旧派工 $D1_OLD 已退回，新派工 $D1_NEW"

echo
echo "== 4. 用已退回的旧派工确认位置 1（应 409 被拒绝） =="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST \
  "$BASE/work-orders/$OID/positions/1/confirm" \
  -H 'Content-Type: application/json' -d "{\"dispatch_id\": \"$D1_OLD\"}"

echo
echo "== 5. 用新派工确认位置 1 =="
curl -sS -X POST "$BASE/work-orders/$OID/positions/1/confirm" \
  -H 'Content-Type: application/json' -d "{\"dispatch_id\": \"$D1_NEW\"}" | show

echo
echo "== 6. 纯空白面免印：1 页新版，背面全空白 =="
curl -sS -X POST "$BASE/work-orders" -H 'Content-Type: application/json' -d '{
  "pages": ["ONLY"],
  "old_sheets": []
}' | show
