"""旧印张复用排程。

把旧印张分配到拼版位置，规则：
- 旧纸按原朝向使用，每张至多一次，每个位置至多一张；
- 已印面的左右页须与该位置新版拼版完全一致；未印面不限，按新版内容补印；
- 纯空白面免印。

优化目标（按优先级）：
1. 尽量少用新纸（即尽量多复用旧印张）；
2. 新纸用量相同时，待印面总数最少。

重排时传入 keep（位置 -> 当前旧纸编号），在目标值相同的情况下
倾向保留原安排，使未受影响的位置不被改派。

实现：位置数 <= 12（48 页 / 4），旧纸 <= 40 张，
用「旧纸逐个决策 + 位置位掩码」的 DP 精确求解二分指派。
"""
from __future__ import annotations

SIDES = ("front", "back")

# 待印面差值的放大倍数；保留奖励为 1，远小于一个面的权重，
# 因此保留奖励只在「复用张数、待印面数都相同」时起作用。
FACE_SCALE = 100
KEEP_BONUS = 1


def face_is_blank(face: dict) -> bool:
    """纯空白面：左右页都是空白。"""
    return face["left"] is None and face["right"] is None


def _face_matches(printed: dict, required: dict) -> bool:
    return printed["left"] == required["left"] and printed["right"] == required["right"]


def sheet_compatible(sheet: dict, required: dict) -> bool:
    """旧纸能否用于该位置：所有已印面都与新版拼版一致（原朝向）。"""
    for side in SIDES:
        printed = sheet[side]
        if printed is not None and not _face_matches(printed, required[side]):
            return False
    return True


def faces_with_sheet(sheet: dict, required: dict) -> list[str]:
    """用该旧纸时还需印的面：未印且新版该面非纯空白。"""
    out = []
    for side in SIDES:
        if sheet[side] is None and not face_is_blank(required[side]):
            out.append(side)
    return out


def faces_with_new_paper(required: dict) -> list[str]:
    """领新纸时还需印的面（纯空白面免印）。"""
    return [side for side in SIDES if not face_is_blank(required[side])]


def plan_positions(required_list: list[dict], sheets: list[dict], keep: dict | None = None) -> list[dict]:
    """为每个位置选择旧纸或新纸。

    required_list: 每个位置的新版拼版（从外到内）。
    sheets: 可用旧纸 [{"id", "front", "back"}]，front/back 为 {"left","right"} 或 None（未印）。
    keep: 可选，{位置序号: 当前旧纸编号}，用于重排时尽量不动原安排。

    返回与 required_list 等长的列表：
    [{"use": 旧纸编号或 None(领新纸), "faces": ["front"/"back", ...]}]
    """
    keep = keep or {}
    n_pos = len(required_list)
    if n_pos == 0:
        return []
    new_faces = [len(faces_with_new_paper(r)) for r in required_list]

    # 每张旧纸的兼容边列表：[(位置, 边权)]；边权为相比新纸的待印面差加权重，
    # 减去保留奖励
    sheet_edges: list[list[tuple[int, int]]] = []
    for sheet in sheets:
        edges = []
        for pi in range(n_pos):
            if not sheet_compatible(sheet, required_list[pi]):
                continue
            cost = (len(faces_with_sheet(sheet, required_list[pi])) - new_faces[pi]) * FACE_SCALE
            if keep.get(pi) == sheet["id"]:
                cost -= KEEP_BONUS
            edges.append((pi, cost))
        sheet_edges.append(edges)

    # DP：dp[mask] 为打包分数（复用张数 * MATCH - 费用），mask 为已占用位置的位掩码。
    # 打包后比较即「先最多复用，再最少费用」的字典序。
    MATCH = 10 ** 6
    NEG = -10 ** 18
    size = 1 << n_pos
    dp = [NEG] * size
    dp[0] = 0
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    for si, edges in enumerate(sheet_edges):
        if not edges:
            continue
        snapshot = dp[:]  # 每张纸至多用一次：只从上一轮状态扩展
        for mask in range(size):
            base = snapshot[mask]
            if base == NEG:
                continue
            for pi, cost in edges:
                bit = 1 << pi
                if mask & bit:
                    continue
                nmask = mask | bit
                cand = base + (MATCH - cost)
                if cand > dp[nmask]:
                    dp[nmask] = cand
                    parent[(si, nmask)] = (mask, pi)

    best_mask = max(range(size), key=lambda k: dp[k])
    assignment: dict[int, int] = {}  # 位置 -> 旧纸下标
    mask = best_mask
    for si in range(len(sheets) - 1, -1, -1):
        key = (si, mask)
        if key in parent:
            pmask, pi = parent[key]
            assignment[pi] = si
            mask = pmask

    plan = []
    for pi in range(n_pos):
        if pi in assignment:
            sheet = sheets[assignment[pi]]
            plan.append({"use": sheet["id"], "faces": faces_with_sheet(sheet, required_list[pi])})
        else:
            plan.append({"use": None, "faces": faces_with_new_paper(required_list[pi])})
    return plan
