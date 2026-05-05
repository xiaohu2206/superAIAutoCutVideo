#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户认证路由：请求体与 Authorization 原样转发至上游账号服务，响应原样返回。
"""

from fastapi import APIRouter, Request

from modules.auth.auth_upstream import AUTH_ME_HTTP_TIMEOUT, forward_upstream_get, forward_upstream_post

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/send-register-code", summary="发送注册验证码")
async def send_register_code(request: Request):
    body = await request.json()
    return await forward_upstream_post(
        "/api/auth/send-register-code",
        body,
        request.headers.get("Authorization"),
    )


@router.post("/register", summary="注册用户")
async def register(request: Request):
    body = await request.json()
    return await forward_upstream_post(
        "/api/auth/register",
        body,
        request.headers.get("Authorization"),
    )


@router.post("/login", summary="用户登录")
async def login(request: Request):
    body = await request.json()
    return await forward_upstream_post("/api/auth/login", body, None)


@router.get("/me", summary="获取当前用户信息")
async def get_me(request: Request):
    return await forward_upstream_get(
        "/api/auth/me",
        request.headers.get("Authorization"),
        timeout=AUTH_ME_HTTP_TIMEOUT,
    )


@router.post("/send-reset-code", summary="发送重置密码验证码")
async def send_reset_code(request: Request):
    body = await request.json()
    return await forward_upstream_post(
        "/api/auth/send-reset-code",
        body,
        request.headers.get("Authorization"),
    )


@router.post("/reset-password", summary="重置密码")
async def reset_password(request: Request):
    body = await request.json()
    return await forward_upstream_post(
        "/api/auth/reset-password",
        body,
        request.headers.get("Authorization"),
    )
