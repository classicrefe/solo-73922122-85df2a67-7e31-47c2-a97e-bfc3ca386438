from app.planner import (
    faces_with_new_paper,
    faces_with_sheet,
    plan_positions,
    sheet_compatible,
)


def req(fl, fr, bl, br):
    return {"front": {"left": fl, "right": fr}, "back": {"left": bl, "right": br}}


def face(l, r):
    return {"left": l, "right": r}


def sheet(sid, front=None, back=None):
    return {"id": sid, "front": front, "back": back}


def test_printed_face_must_match_exactly():
    required = req("X", "A", "B", "C")
    assert sheet_compatible(sheet("S1", front=face("X", "A")), required)
    assert not sheet_compatible(sheet("S2", front=face("A", "X")), required)  # 左右颠倒
    assert not sheet_compatible(sheet("S3", back=face("B", "X")), required)


def test_unprinted_face_imposes_no_constraint():
    required = req("X", "A", "B", "C")
    assert sheet_compatible(sheet("S1"), required)  # 两面都未印
    assert sheet_compatible(sheet("S2", front=face("X", "A")), required)


def test_blank_face_exempt_from_printing():
    required = req(None, "A", None, None)  # 背面纯空白
    assert faces_with_new_paper(required) == ["front"]
    assert faces_with_sheet(sheet("S1"), required) == ["front"]
    # 正面已印、背面未印但纯空白 -> 无需印任何面
    assert faces_with_sheet(sheet("S2", front=face(None, "A")), required) == []


def test_minimize_new_paper_first():
    required = [req("X", "A", "B", "C"), req("D", "E", "F", "G")]
    s1 = sheet("S1", front=face("X", "A"), back=face("B", "C"))  # 只配位置 0，0 面待印
    s2 = sheet("S2")  # 未印，两个位置都配，2 面待印
    plan = plan_positions(required, [s1, s2])
    # 两张都用上（0 张新纸），即使 s2 要印 2 面
    assert [p["use"] for p in plan] == ["S1", "S2"]
    assert plan[0]["faces"] == []
    assert plan[1]["faces"] == ["front", "back"]


def test_tie_break_fewest_faces():
    required = [req("X", "A", "B", "C")]
    s1 = sheet("S1")  # 2 面待印
    s2 = sheet("S2", front=face("X", "A"))  # 1 面待印
    s3 = sheet("S3", front=face("X", "A"), back=face("B", "C"))  # 0 面待印
    plan = plan_positions(required, [s1, s2, s3])
    assert plan == [{"use": "S3", "faces": []}]


def test_sheet_used_at_most_once():
    required = [req("X", "A", "B", "C"), req("X", "A", "B", "C")]
    s1 = sheet("S1", front=face("X", "A"), back=face("B", "C"))
    plan = plan_positions(required, [s1])
    uses = [p["use"] for p in plan]
    assert uses.count("S1") == 1
    assert uses.count(None) == 1


def test_unprinted_sheet_counts_as_old_paper():
    required = [req("X", "A", "B", "C")]
    plan = plan_positions(required, [sheet("S1")])
    assert plan == [{"use": "S1", "faces": ["front", "back"]}]


def test_new_paper_faces_respect_blank_exemption():
    required = [req(None, None, None, None)]  # 整页空白（例如 0 内容页之外的补白张）
    plan = plan_positions(required, [])
    assert plan == [{"use": None, "faces": []}]


def test_keep_bonus_keeps_current_assignment_on_replan():
    # 两个相同位置、两张等效旧纸：重排时应保持 keep 指定的现状
    required = [req("X", "A", "B", "C"), req("X", "A", "B", "C")]
    s1 = sheet("S1", front=face("X", "A"), back=face("B", "C"))
    s2 = sheet("S2", front=face("X", "A"), back=face("B", "C"))
    plan = plan_positions(required, [s1, s2], keep={0: "S2", 1: "S1"})
    assert [p["use"] for p in plan] == ["S2", "S1"]


def test_faces_objective_dominates_keep_bonus():
    # 保留现状要多印 1 面时，应按规则选待印面更少的方案
    required = [req("X", "A", "B", "C")]
    s1 = sheet("S1")  # 2 面待印，当前在位置 0
    s2 = sheet("S2", front=face("X", "A"), back=face("B", "C"))  # 0 面待印
    plan = plan_positions(required, [s1, s2], keep={0: "S1"})
    assert plan == [{"use": "S2", "faces": []}]


def test_original_orientation_required():
    # 旧纸正反面不可对调：背面内容印在正面不算匹配
    required = [req("X", "A", "B", "C")]
    flipped = sheet("S1", front=face("B", "C"), back=face("X", "A"))
    plan = plan_positions(required, [flipped])
    assert plan[0]["use"] is None
