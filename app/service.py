"""业务逻辑：建单、查询、派工确认、报废重排。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import db, imposition, planner

NEW = "NEW"  # 领新纸


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return uuid.uuid4().hex


def _load_order(c, oid: str):
    row = c.execute("SELECT * FROM work_orders WHERE id = ?", (oid,)).fetchone()
    if row is None:
        raise ApiError(404, "工单不存在")
    return row


def _position_rows(c, oid: str):
    return c.execute(
        "SELECT * FROM positions WHERE work_order_id = ? ORDER BY pos_index", (oid,)
    ).fetchall()


def _scrapped_ids(c, oid: str) -> set:
    rows = c.execute("SELECT sheet_id FROM scraps WHERE work_order_id = ?", (oid,)).fetchall()
    return {r["sheet_id"] for r in rows}


def _state(c, oid: str) -> dict:
    """工单当前状态：返印单（从外到内）+ 汇总。"""
    order = _load_order(c, oid)
    rows = _position_rows(c, oid)
    positions = []
    new_paper = old_used = faces_remaining = completed = 0
    for r in rows:
        planned = json.loads(r["faces_json"])
        remaining = [] if r["status"] == "completed" else planned
        if r["assignment"] == NEW:
            new_paper += 1
        else:
            old_used += 1
        faces_remaining += len(remaining)
        completed += r["status"] == "completed"
        positions.append(
            {
                "position": r["pos_index"],
                "required": json.loads(r["required_json"]),
                "use": r["assignment"],
                "faces_to_print": remaining,
                "status": r["status"],
                "dispatch_id": r["dispatch_id"],
            }
        )
    return {
        "work_order_id": oid,
        "status": "completed" if completed == len(rows) else "in_progress",
        "padded_pages": json.loads(order["pages_json"]),
        "old_sheets": json.loads(order["old_sheets_json"]),
        "scrapped_sheets": sorted(_scrapped_ids(c, oid)),
        "positions": positions,
        "summary": {
            "positions": len(rows),
            "old_sheets_used": old_used,
            "new_paper": new_paper,
            "faces_to_print": faces_remaining,
            "completed_positions": completed,
        },
        "created_at": order["created_at"],
    }


def create_work_order(pages: list, old_sheets: list[dict]) -> dict:
    """提交新版页序与旧印张，生成返印单（每个位置带派工号）。"""
    padded = imposition.pad_pages(pages)
    required_list = imposition.saddle_stitch_positions(padded)
    plan = planner.plan_positions(required_list, old_sheets)
    oid = _uuid()
    now = _now()
    with db.lock():
        c = db.conn()
        with c:
            c.execute(
                "INSERT INTO work_orders (id, pages_json, old_sheets_json, created_at) VALUES (?,?,?,?)",
                (oid, json.dumps(padded, ensure_ascii=False), json.dumps(old_sheets, ensure_ascii=False), now),
            )
            for pi, (required, p) in enumerate(zip(required_list, plan)):
                dispatch_id = _uuid()
                assignment = p["use"] if p["use"] is not None else NEW
                c.execute(
                    "INSERT INTO positions (work_order_id, pos_index, required_json, assignment, faces_json, status, dispatch_id)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (
                        oid,
                        pi,
                        json.dumps(required, ensure_ascii=False),
                        assignment,
                        json.dumps(p["faces"]),
                        "pending",
                        dispatch_id,
                    ),
                )
                c.execute(
                    "INSERT INTO dispatches (id, work_order_id, pos_index, assignment, state, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (dispatch_id, oid, pi, assignment, "active", now),
                )
        return _state(c, oid)


def get_work_order(oid: str) -> dict:
    with db.lock():
        return _state(db.conn(), oid)


def list_work_orders() -> list[dict]:
    with db.lock():
        c = db.conn()
        rows = c.execute("SELECT id FROM work_orders ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            st = _state(c, r["id"])
            out.append(
                {
                    "work_order_id": r["id"],
                    "created_at": st["created_at"],
                    "status": st["status"],
                    "summary": st["summary"],
                }
            )
        return out


def confirm_position(oid: str, pos_index: int, dispatch_id: str) -> dict:
    """凭该位置的有效派工确认完工。旧派工（已退回）确认会被拒绝。"""
    with db.lock():
        c = db.conn()
        _load_order(c, oid)
        pos = c.execute(
            "SELECT * FROM positions WHERE work_order_id = ? AND pos_index = ?",
            (oid, pos_index),
        ).fetchone()
        if pos is None:
            raise ApiError(404, "位置不存在")
        disp = c.execute(
            "SELECT * FROM dispatches WHERE id = ? AND work_order_id = ?",
            (dispatch_id, oid),
        ).fetchone()
        if disp is None:
            raise ApiError(404, "派工不存在")
        if disp["pos_index"] != pos_index:
            raise ApiError(409, "该派工不属于此位置")
        if disp["state"] == "returned":
            raise ApiError(409, "旧派工已退回：该位置已改派，请按新派工确认")
        if disp["state"] == "active":
            with c:
                c.execute("UPDATE dispatches SET state = 'confirmed' WHERE id = ?", (dispatch_id,))
                c.execute(
                    "UPDATE positions SET status = 'completed' WHERE work_order_id = ? AND pos_index = ?",
                    (oid, pos_index),
                )
        # state == 'confirmed'：重复确认按幂等处理，直接返回当前状态
        return _state(c, oid)


def scrap_sheets(oid: str, sheet_ids: list[str]) -> dict:
    """报废未完工的旧印张并重排。

    - 已完工位置留在原位，其旧纸不再进入纸池；
    - 其余位置用剩余旧纸重新优化（目标不变：先少新纸，再少待印面）；
    - 被改派位置的旧派工退回（confirm 会拒绝），并签发新派工；
    - 未改派位置保留原派工，仍可按原安排确认。
    """
    sheet_ids = list(dict.fromkeys(sheet_ids))  # 去重保序
    with db.lock():
        c = db.conn()
        order = _load_order(c, oid)
        old_sheets = json.loads(order["old_sheets_json"])
        by_id = {s["id"]: s for s in old_sheets}
        scrapped = _scrapped_ids(c, oid)
        rows = _position_rows(c, oid)
        completed_sheet_ids = {
            r["assignment"] for r in rows if r["status"] == "completed" and r["assignment"] != NEW
        }
        for sid in sheet_ids:
            if sid not in by_id:
                raise ApiError(404, f"旧印张不存在: {sid}")
            if sid in scrapped:
                raise ApiError(409, f"旧印张已报废: {sid}")
            if sid in completed_sheet_ids:
                raise ApiError(409, f"旧印张已完工，不能报废: {sid}")

        # 重排：完工位置固定，其余位置 + 剩余旧纸重新优化
        scrapped_all = scrapped | set(sheet_ids)
        pool = [
            s
            for s in old_sheets
            if s["id"] not in scrapped_all and s["id"] not in completed_sheet_ids
        ]
        free = [r for r in rows if r["status"] != "completed"]
        required_list = [json.loads(r["required_json"]) for r in free]
        keep = {i: r["assignment"] for i, r in enumerate(free) if r["assignment"] != NEW}
        plan = planner.plan_positions(required_list, pool, keep)

        now = _now()
        returned = []
        with c:
            for sid in sheet_ids:
                c.execute(
                    "INSERT INTO scraps (work_order_id, sheet_id, created_at) VALUES (?,?,?)",
                    (oid, sid, now),
                )
            for r, p in zip(free, plan):
                new_assignment = p["use"] if p["use"] is not None else NEW
                if new_assignment == r["assignment"]:
                    continue  # 未改派：保留原派工
                c.execute("UPDATE dispatches SET state = 'returned' WHERE id = ?", (r["dispatch_id"],))
                new_dispatch = _uuid()
                c.execute(
                    "UPDATE positions SET assignment = ?, faces_json = ?, dispatch_id = ?"
                    " WHERE work_order_id = ? AND pos_index = ?",
                    (new_assignment, json.dumps(p["faces"]), new_dispatch, oid, r["pos_index"]),
                )
                c.execute(
                    "INSERT INTO dispatches (id, work_order_id, pos_index, assignment, state, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (new_dispatch, oid, r["pos_index"], new_assignment, "active", now),
                )
                returned.append(
                    {
                        "position": r["pos_index"],
                        "returned_dispatch_id": r["dispatch_id"],
                        "old": r["assignment"],
                        "new": new_assignment,
                    }
                )
        state = _state(c, oid)
        state["returned_dispatches"] = returned
        return state
