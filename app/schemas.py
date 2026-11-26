"""请求体的 Pydantic 模型与校验。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_PAGES = 48        # 新版最多 48 页
MAX_OLD_SHEETS = 40   # 至多 40 张旧印张

# 内容编号：字符串或数字，null 表示空白页；数字统一规整为字符串
ContentId = str | int | None


def _norm(v):
    return None if v is None else str(v)


class Face(BaseModel):
    """一个印面的左右页。整个面未印时在旧印张里用 null 表示。"""

    left: ContentId = None
    right: ContentId = None

    @field_validator("left", "right")
    @classmethod
    def _norm_side(cls, v):
        return _norm(v)


class OldSheet(BaseModel):
    """旧印张：编号 + 正反面。正面为折后外侧；未印面为 null。"""

    id: str = Field(min_length=1, max_length=64)
    front: Face | None = None
    back: Face | None = None


class CreateWorkOrder(BaseModel):
    pages: list[ContentId] = Field(min_length=1, max_length=MAX_PAGES)
    old_sheets: list[OldSheet] = Field(default_factory=list, max_length=MAX_OLD_SHEETS)

    @field_validator("pages")
    @classmethod
    def _norm_pages(cls, v):
        return [_norm(p) for p in v]

    @model_validator(mode="after")
    def _unique_sheet_ids(self):
        ids = [s.id for s in self.old_sheets]
        if len(ids) != len(set(ids)):
            raise ValueError("旧印张编号重复")
        return self


class ConfirmIn(BaseModel):
    dispatch_id: str = Field(min_length=1)


class ScrapIn(BaseModel):
    sheet_ids: list[str] = Field(min_length=1)
