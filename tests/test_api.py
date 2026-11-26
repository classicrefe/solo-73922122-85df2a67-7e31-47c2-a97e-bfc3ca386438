"""端到端 API 测试：建单 → 派工确认 → 报废重排 → 旧派工退回。"""

PAGES = ["COVER", "P2", "P3", "P4", "P5"]  # 补白到 8 页，2 个位置
# 位置 0（最外）: 正面 {None, COVER}  背面 {P2, None}
# 位置 1        : 正面 {None, P3}     背面 {P4, P5}
SHEETS = [
    {"id": "S1", "front": {"left": None, "right": "COVER"}, "back": None},  # 配位置 0，补印背面
    {"id": "S2", "front": None, "back": {"left": "P4", "right": "P5"}},     # 配位置 1，补印正面
    {"id": "S3", "front": {"left": "OLD", "right": "STUFF"}, "back": None}, # 配不上，不用
]


def create(client, pages=PAGES, old_sheets=SHEETS):
    r = client.post("/work-orders", json={"pages": pages, "old_sheets": old_sheets})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_work_order_plan(client):
    st = create(client)
    assert st["status"] == "in_progress"
    assert st["padded_pages"] == ["COVER", "P2", "P3", "P4", "P5", None, None, None]
    positions = st["positions"]
    assert [p["position"] for p in positions] == [0, 1]  # 从外到内
    assert positions[0]["required"] == {
        "front": {"left": None, "right": "COVER"},
        "back": {"left": "P2", "right": None},
    }
    assert positions[0]["use"] == "S1"
    assert positions[0]["faces_to_print"] == ["back"]
    assert positions[1]["use"] == "S2"
    assert positions[1]["faces_to_print"] == ["front"]
    assert st["summary"] == {
        "positions": 2,
        "old_sheets_used": 2,
        "new_paper": 0,
        "faces_to_print": 2,
        "completed_positions": 0,
    }
    assert all(p["dispatch_id"] for p in positions)


def test_validation_limits(client):
    r = client.post("/work-orders", json={"pages": ["P"] * 49})
    assert r.status_code == 422
    r = client.post("/work-orders", json={"pages": []})
    assert r.status_code == 422
    r = client.post(
        "/work-orders",
        json={"pages": ["P"], "old_sheets": [{"id": f"S{i}"} for i in range(41)]},
    )
    assert r.status_code == 422
    r = client.post(
        "/work-orders",
        json={"pages": ["P"], "old_sheets": [{"id": "DUP"}, {"id": "DUP"}]},
    )
    assert r.status_code == 422


def test_blank_face_exempt_via_api(client):
    st = create(client, pages=["A"], old_sheets=[])
    pos = st["positions"][0]
    assert pos["use"] == "NEW"
    assert pos["faces_to_print"] == ["front"]  # 背面纯空白免印
    assert st["summary"]["new_paper"] == 1
    assert st["summary"]["faces_to_print"] == 1


def test_confirm_flow(client):
    st = create(client)
    oid = st["work_order_id"]
    d0 = st["positions"][0]["dispatch_id"]
    d1 = st["positions"][1]["dispatch_id"]

    r = client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": "bogus"})
    assert r.status_code == 404
    r = client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": d1})
    assert r.status_code == 409  # 派工不属于此位置

    r = client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": d0})
    assert r.status_code == 200
    st = r.json()
    assert st["positions"][0]["status"] == "completed"
    assert st["positions"][0]["faces_to_print"] == []

    r = client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": d0})
    assert r.status_code == 200  # 重复确认幂等

    r = client.post(f"/work-orders/{oid}/positions/1/confirm", json={"dispatch_id": d1})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_scrap_replan_and_returned_dispatch(client):
    st = create(client)
    oid = st["work_order_id"]
    d0 = st["positions"][0]["dispatch_id"]
    d1_old = st["positions"][1]["dispatch_id"]

    # 位置 0 完工；报废位置 1 的 S2（未完工）
    client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": d0})
    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["S2"]})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["scrapped_sheets"] == ["S2"]
    assert st["returned_dispatches"] == [
        {"position": 1, "returned_dispatch_id": d1_old, "old": "S2", "new": "NEW"}
    ]
    # 完工位置留在原位；位置 1 改领新纸，两面都要印
    assert st["positions"][0]["use"] == "S1"
    assert st["positions"][0]["status"] == "completed"
    assert st["positions"][1]["use"] == "NEW"
    assert st["positions"][1]["faces_to_print"] == ["front", "back"]
    d1_new = st["positions"][1]["dispatch_id"]
    assert d1_new != d1_old

    # 旧派工确认被退回；新派工可确认
    r = client.post(f"/work-orders/{oid}/positions/1/confirm", json={"dispatch_id": d1_old})
    assert r.status_code == 409
    assert "退回" in r.json()["detail"]
    r = client.post(f"/work-orders/{oid}/positions/1/confirm", json={"dispatch_id": d1_new})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_scrap_validation(client):
    st = create(client)
    oid = st["work_order_id"]
    d0 = st["positions"][0]["dispatch_id"]

    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["NOPE"]})
    assert r.status_code == 404

    client.post(f"/work-orders/{oid}/positions/0/confirm", json={"dispatch_id": d0})
    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["S1"]})
    assert r.status_code == 409  # 已完工不能报废

    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["S2"]})
    assert r.status_code == 200
    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["S2"]})
    assert r.status_code == 409  # 重复报废


def test_untouched_positions_keep_original_dispatch(client):
    # 9 页 -> 补白 12 页 -> 3 个位置
    pages = [f"P{i}" for i in range(1, 10)]
    sheets = [
        {"id": "SA", "front": {"left": None, "right": "P1"}, "back": None},
        {"id": "SB", "front": {"left": None, "right": "P3"}, "back": None},
        {"id": "SC", "front": {"left": "ZZ", "right": "QQ"}, "back": None},  # 未分配
    ]
    st = create(client, pages=pages, old_sheets=sheets)
    oid = st["work_order_id"]
    assert [p["use"] for p in st["positions"]] == ["SA", "SB", "NEW"]
    dispatches_before = [p["dispatch_id"] for p in st["positions"]]

    # 报废未分配的 SC：重排不应改动任何位置
    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["SC"]})
    assert r.status_code == 200
    st = r.json()
    assert st["returned_dispatches"] == []
    assert [p["dispatch_id"] for p in st["positions"]] == dispatches_before

    # 未改派位置仍可按原安排确认
    r = client.post(
        f"/work-orders/{oid}/positions/0/confirm",
        json={"dispatch_id": dispatches_before[0]},
    )
    assert r.status_code == 200
    assert r.json()["positions"][0]["status"] == "completed"


def test_replan_reuses_remaining_sheets(client):
    # 报废一张后，剩余旧纸应重新参与优化（此处 S2 报废后位置 1 只能领新纸，
    # 而 S3 配不上任何位置，保持未用）
    st = create(client)
    oid = st["work_order_id"]
    r = client.post(f"/work-orders/{oid}/scrap", json={"sheet_ids": ["S2"]})
    st = r.json()
    assert st["positions"][1]["use"] == "NEW"
    assert st["summary"]["new_paper"] == 1
    assert st["summary"]["old_sheets_used"] == 1


def test_get_and_list_orders(client):
    st = create(client)
    oid = st["work_order_id"]
    r = client.get(f"/work-orders/{oid}")
    assert r.status_code == 200
    assert r.json()["work_order_id"] == oid
    r = client.get("/work-orders")
    assert r.status_code == 200
    assert any(o["work_order_id"] == oid for o in r.json())
    r = client.get("/work-orders/nope")
    assert r.status_code == 404


def test_content_ids_may_repeat_and_ints_normalized(client):
    st = create(client, pages=[1, 1, 2], old_sheets=[])
    assert st["padded_pages"] == ["1", "1", "2", None]
