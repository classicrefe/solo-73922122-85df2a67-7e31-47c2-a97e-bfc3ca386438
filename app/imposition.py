"""骑马钉（saddle-stitch）拼版。

页序先在末尾补白（None）凑足 4 的倍数，再按骑马钉从外到内拼版：
第 i 张（i 从 0 开始，0 为最外）：
  正面（折后外侧）：左 = 第 N-2i 页，右 = 第 2i+1 页
  背面            ：左 = 第 2i+2 页，右 = 第 N-2i-1 页
页码从 1 开始。
"""
from __future__ import annotations


def pad_pages(pages: list) -> list:
    """在末尾补白页（None）凑足 4 的倍数。"""
    pages = list(pages)
    rem = len(pages) % 4
    if rem:
        pages.extend([None] * (4 - rem))
    return pages


def saddle_stitch_positions(padded_pages: list) -> list[dict]:
    """把补白后的页序拼成印张位置，从外到内。

    返回每个位置的正反面左右页（内容编号，None 表示空白）：
    [{"front": {"left": .., "right": ..}, "back": {"left": .., "right": ..}}, ...]
    正面为折后外侧。
    """
    n = len(padded_pages)

    def page(no: int):  # no 为 1 起始页码
        return padded_pages[no - 1]

    positions = []
    for i in range(n // 4):
        positions.append(
            {
                "front": {"left": page(n - 2 * i), "right": page(2 * i + 1)},
                "back": {"left": page(2 * i + 2), "right": page(n - 2 * i - 1)},
            }
        )
    return positions
