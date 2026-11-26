"""FastAPI 入口：骑马钉返印 API。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import db, service
from .schemas import ConfirmIn, CreateWorkOrder, ScrapIn


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(title="骑马钉返印 API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(service.ApiError)
async def api_error_handler(_: Request, exc: service.ApiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
def root():
    return {"service": "骑马钉返印 API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/work-orders", status_code=201)
def create_work_order(body: CreateWorkOrder):
    """提交新版页序（<=48 页）与旧印张（<=40 张），生成返印单。"""
    sheets = [s.model_dump() for s in body.old_sheets]
    return service.create_work_order(body.pages, sheets)


@app.get("/work-orders")
def list_work_orders():
    return service.list_work_orders()


@app.get("/work-orders/{oid}")
def get_work_order(oid: str):
    return service.get_work_order(oid)


@app.post("/work-orders/{oid}/positions/{pos_index}/confirm")
def confirm_position(oid: str, pos_index: int, body: ConfirmIn):
    """凭该位置的有效派工确认完工。"""
    return service.confirm_position(oid, pos_index, body.dispatch_id)


@app.post("/work-orders/{oid}/scrap")
def scrap_sheets(oid: str, body: ScrapIn):
    """报废未完工的旧印张并重排；完工位置留在原位。"""
    return service.scrap_sheets(oid, body.sheet_ids)
