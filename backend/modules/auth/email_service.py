#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件发送服务模块
使用 SMTP 发送验证码邮件。
配置通过环境变量或配置文件读取。
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

from modules.app_paths import user_config_dir

import logging

logger = logging.getLogger(__name__)

# 默认 SMTP 配置（可通过配置文件覆盖）
_DEFAULT_SMTP_HOST = ""
_DEFAULT_SMTP_PORT = 465
_DEFAULT_SMTP_USER = ""
_DEFAULT_SMTP_PASSWORD = ""
_DEFAULT_SMTP_USE_SSL = True
_DEFAULT_EMAIL_FROM = ""


def _load_smtp_config() -> dict:
    """从配置文件加载 SMTP 配置，环境变量优先"""
    config = {
        "host": os.environ.get("SACV_SMTP_HOST", _DEFAULT_SMTP_HOST),
        "port": int(os.environ.get("SACV_SMTP_PORT", str(_DEFAULT_SMTP_PORT))),
        "user": os.environ.get("SACV_SMTP_USER", _DEFAULT_SMTP_USER),
        "password": os.environ.get("SACV_SMTP_PASSWORD", _DEFAULT_SMTP_PASSWORD),
        "use_ssl": os.environ.get("SACV_SMTP_USE_SSL", str(_DEFAULT_SMTP_USE_SSL)).lower() in ("1", "true", "yes"),
        "from_email": os.environ.get("SACV_SMTP_FROM", _DEFAULT_EMAIL_FROM),
    }

    # 尝试从配置文件补充缺失项
    cfg_path = user_config_dir() / "smtp_config.json"
    if cfg_path.exists():
        try:
            file_config = json.loads(cfg_path.read_text(encoding="utf-8"))
            for key in ("host", "port", "user", "password", "use_ssl", "from_email"):
                if not config[key] and key in file_config:
                    config[key] = file_config[key]
        except Exception as e:
            logger.warning(f"读取 SMTP 配置文件失败: {e}")

    return config


def send_verification_email(to_email: str, code: str, code_type: str = "register") -> bool:
    """
    发送验证码邮件。
    返回 True 表示发送成功，False 表示失败。
    """
    config = _load_smtp_config()

    if not config["host"] or not config["user"] or not config["password"]:
        logger.warning(
            "SMTP 配置不完整，验证码邮件未发送。"
            f"code={code} to={to_email} type={code_type}"
        )
        # 开发阶段：打印验证码到日志
        logger.info(f"[DEV] 验证码: {code} (发送至 {to_email}, 类型={code_type})")
        return False

    if code_type == "register":
        subject = "注册验证码 - AI智能视频剪辑"
        body = f"您的注册验证码为：{code}，有效期5分钟。如非本人操作，请忽略此邮件。"
    else:
        subject = "重置密码验证码 - AI智能视频剪辑"
        body = f"您的重置密码验证码为：{code}，有效期5分钟。如非本人操作，请忽略此邮件。"

    msg = MIMEMultipart()
    msg["From"] = config["from_email"] or config["user"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if config["use_ssl"]:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=10)
        else:
            server = smtplib.SMTP(config["host"], config["port"], timeout=10)
            server.starttls()

        server.login(config["user"], config["password"])
        server.sendmail(msg["From"], [to_email], msg.as_string())
        server.quit()
        logger.info(f"验证码邮件已发送: to={to_email} type={code_type}")
        return True
    except Exception as e:
        logger.error(f"发送验证码邮件失败: {e}")
        # 开发阶段回退到日志
        logger.info(f"[DEV-FALLBACK] 验证码: {code} (发送至 {to_email}, 类型={code_type})")
        return False
