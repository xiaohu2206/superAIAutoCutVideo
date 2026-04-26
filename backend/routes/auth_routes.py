#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户认证路由
提供注册、登录、获取用户信息、验证码发送、重置密码等接口。
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.auth.user_store import user_store
from modules.auth.code_service import code_service
from modules.auth.jwt_utils import create_token, decode_token, get_user_id_from_token
from modules.auth.email_service import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ---------- 请求模型 ----------


class SendCodeRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    newPassword: str = Field(..., min_length=6)


# ---------- 工具函数 ----------

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_email(email: str) -> str:
    email = email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式校验失败")
    return email.lower()


def _get_current_user(request: Request):
    """从请求头中提取并验证当前用户"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth_header[len("Bearer "):]
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


# ---------- 接口 ----------


@router.post("/send-register-code", summary="发送注册验证码")
async def send_register_code(req: SendCodeRequest):
    email = _validate_email(req.email)

    # 已注册用户不再发送注册验证码
    if user_store.get_by_email(email):
        raise HTTPException(status_code=400, detail="邮箱已注册")

    try:
        code = code_service.send_code(email, code_type="register")
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    # 尝试发送邮件（未配置 SMTP 时会打印到日志）
    send_verification_email(email, code, code_type="register")

    return {"code": 0, "message": "success", "data": True}


@router.post("/register", summary="注册用户")
async def register(req: RegisterRequest):
    email = _validate_email(req.email)

    if not code_service.verify_code(email, req.code, code_type="register"):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    if user_store.get_by_email(email):
        raise HTTPException(status_code=400, detail="邮箱已注册")

    try:
        user = user_store.create_user(email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"code": 0, "message": "success", "data": {"userId": user.id}}


@router.post("/login", summary="用户登录")
async def login(req: LoginRequest):
    email = _validate_email(req.email)

    user = user_store.get_by_email(email)
    if not user or not user_store.verify_password(user, req.password):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    if user.status == "disabled":
        raise HTTPException(status_code=403, detail="账号已禁用")

    token = create_token(user.id, user.email)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "status": user.status,
            },
        },
    }


@router.get("/me", summary="获取当前用户信息")
async def get_me(request: Request):
    user = _get_current_user(request)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": user.id,
            "email": user.email,
            "status": user.status,
            "createdAt": user.created_at,
            "updatedAt": user.updated_at,
        },
    }


@router.post("/send-reset-code", summary="发送重置密码验证码")
async def send_reset_code(req: SendCodeRequest):
    email = _validate_email(req.email)

    # 重置密码时需确认用户存在
    if not user_store.get_by_email(email):
        # 为安全起见不提示"用户不存在"，统一返回成功
        return {"code": 0, "message": "success", "data": True}

    try:
        code = code_service.send_code(email, code_type="reset")
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    send_verification_email(email, code, code_type="reset")

    return {"code": 0, "message": "success", "data": True}


@router.post("/reset-password", summary="重置密码")
async def reset_password(req: ResetPasswordRequest):
    email = _validate_email(req.email)

    if not code_service.verify_code(email, req.code, code_type="reset"):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    user = user_store.get_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")

    user_store.update_password(user.id, req.newPassword)

    return {"code": 0, "message": "success", "data": True}
