"""ProblemDetail 全局错误形归一（anchors-api.md §2/§3.2，kilo S-1 施工项）。

RFC 7807 风格四键：`type/title/status/detail`，`title`+`status` 必填。
三层接法（§3.2）：
- `HTTPException`（含未匹配路由 404）→ 统一换形；`detail` 以 `/errors/` 开头时
  同时用作 `type`（路由传机器码，如 `/errors/anchor-not-found`），否则按状态码映射；
- `RequestValidationError` → 422 `/errors/validation`，只回首个错误的字段+原因
  （不回全量错误路径，防内部结构泄漏）；
- handler 只换形不改状态码——409 保险丝等业务语义仍在路由内。

OpenAPI 声明不自动生成（§3.3 关键坑）：responses.Problem 注入在
`openapi_ext.custom_openapi()` 手工维护（快照已有 components.responses.Problem）。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_STATUS_TYPE = {
    400: "/errors/bad-request",
    404: "/errors/not-found",
    409: "/errors/conflict",
}

#: 机器码 → 人读短标题（路由传 /errors/... 机器码时按此定 title）
_TYPE_TITLE = {
    "/errors/anchor-not-found": "玩家档不存在",
    "/errors/profile-not-found": "配置档案不存在",
    "/errors/anchor-protected": "该档不可删除",
    "/errors/world-not-ready": "世界未就绪",
    "/errors/validation": "请求校验失败",
}

_STATUS_TITLE = {
    400: "请求错误",
    404: "资源不存在",
    409: "冲突",
    500: "服务内部错误",
}


def _problem(status: int, type_: str, title: str, detail: str) -> dict[str, Any]:
    """四键 ProblemDetail 构造（title+status 必填，type/detail 附加）。"""
    return {"type": type_, "title": title, "status": status, "detail": detail}


def install_error_handlers(app: FastAPI) -> None:
    """全局错误形归一：HTTPException / 未匹配 404 / 422 校验 → ProblemDetail。"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = str(exc.detail)
        # 路由传机器码（/errors/... 开头）→ 同时用作 type；`机器码|人读详情`
        # 分段时 type 取码、detail 取人读段；否则按状态码映射
        if detail.startswith("/errors/"):
            type_, _, human = detail.partition("|")
            body_detail = human if human else detail
        else:
            type_ = _STATUS_TYPE.get(exc.status_code, "/errors/http-error")
            body_detail = detail
        title = _TYPE_TITLE.get(type_) or _STATUS_TITLE.get(exc.status_code, "请求错误")
        return JSONResponse(
            status_code=exc.status_code,
            content=_problem(exc.status_code, type_, title, body_detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first["loc"][1:]) or "body"
        return JSONResponse(
            status_code=422,
            content=_problem(
                422,
                "/errors/validation",
                "请求校验失败",
                f"{loc}: {first['msg']}",
            ),
        )
