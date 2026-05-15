from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging
import httpx

from modules.httpx_trust_env import trust_env_for_http_url
from modules.config.ai_search_shot_model_config import (
    AiSearchShotModelConfig,
    ai_search_shot_model_config_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings/ai-search-shot", tags=["设置"])


class AiSearchShotModelConfigRequest(BaseModel):
    config: AiSearchShotModelConfig = Field(..., description="向量模型 模型配置")


class AiSearchShotTestRequest(BaseModel):
    config: AiSearchShotModelConfig = Field(..., description="用于测试的 向量模型 模型配置")


def safe_config_dict_hide_apikey(config: AiSearchShotModelConfig) -> dict:
    config_dict = config.dict()
    api_key = config_dict.get("api_key")
    if api_key and len(api_key) > 8:
        config_dict["api_key"] = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
    return config_dict


@router.get("")
async def get_ai_search_shot_model_config():
    try:
        config = ai_search_shot_model_config_manager.get_config()
        return {
            "success": True,
            "data": {
                "config": safe_config_dict_hide_apikey(config),
            },
            "message": "获取 向量模型 模型配置成功",
        }
    except Exception as e:
        logger.error(f"获取 向量模型 模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_ai_search_shot_model_config(request: AiSearchShotModelConfigRequest):
    try:
        old_config = ai_search_shot_model_config_manager.get_config()
        new_config = request.config

        if (
            old_config
            and new_config.api_key
            and "*" in new_config.api_key
            and old_config.api_key[:4] == new_config.api_key[:4]
            and old_config.api_key[-4:] == new_config.api_key[-4:]
        ):
            new_config.api_key = old_config.api_key

        saved_config = ai_search_shot_model_config_manager.update_config(new_config)
        return {
            "success": True,
            "data": {
                "config": safe_config_dict_hide_apikey(saved_config),
            },
            "message": "向量模型 模型配置更新成功",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新 向量模型 模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _merge_stored_api_key_if_masked(new_config: AiSearchShotModelConfig) -> AiSearchShotModelConfig:
    """测试请求里常带脱敏 api_key，与已保存配置合并为完整密钥后再调用上游。"""
    old_config = ai_search_shot_model_config_manager.get_config()
    if (
        old_config
        and new_config.api_key
        and "*" in new_config.api_key
        and old_config.api_key[:4] == new_config.api_key[:4]
        and old_config.api_key[-4:] == new_config.api_key[-4:]
    ):
        merged = new_config.copy(deep=True)
        merged.api_key = old_config.api_key
        return merged
    return new_config


async def _test_embedding_config(config: AiSearchShotModelConfig) -> dict:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.embedding_model,
        "input": "test embedding text",
    }
    timeout = httpx.Timeout(float(config.timeout_seconds or 300))
    async with httpx.AsyncClient(
        timeout=timeout,
        trust_env=trust_env_for_http_url(str(config.embedding_base_url)),
    ) as client:
        response = await client.post(
            str(config.embedding_base_url),
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    embedding = None
    try:
        embedding = data["data"][0]["embedding"]
    except Exception as exc:
        raise RuntimeError(f"向量接口返回结构异常: {data}") from exc

    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("向量接口未返回有效 embedding")

    return {
        "success": True,
        "message": "向量模型测试成功",
        "dimension": len(embedding),
        "preview": embedding[:5],
    }


async def _test_rerank_config(config: AiSearchShotModelConfig) -> dict:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.rerank_model,
        "query": "测试召回模型是否可用",
        "documents": [
            "这是第一条用于测试的文本。",
            "这是第二条用于测试的文本。",
            "这是一条和查询更相关的测试文本。",
        ],
        "top_n": 2,
    }
    timeout = httpx.Timeout(float(config.timeout_seconds or 300))
    async with httpx.AsyncClient(
        timeout=timeout,
        trust_env=trust_env_for_http_url(str(config.rerank_base_url)),
    ) as client:
        response = await client.post(
            str(config.rerank_base_url),
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    results = None
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        if isinstance(data.get("results"), list):
            results = data.get("results")
        elif isinstance(data.get("data"), list):
            results = data.get("data")

    if not isinstance(results, list) or not results:
        raise RuntimeError(f"召回接口返回结构异常: {data}")

    return {
        "success": True,
        "message": "召回模型测试成功",
        "count": len(results),
        "preview": results[:2],
    }


@router.post("/test/embedding")
async def test_ai_search_shot_embedding(request: AiSearchShotTestRequest):
    try:
        config = _merge_stored_api_key_if_masked(request.config)
        result = await _test_embedding_config(config)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"测试 向量模型 向量模型失败: {e}")
        return {"success": False, "data": {"success": False, "message": str(e)}}


@router.post("/test/rerank")
async def test_ai_search_shot_rerank(request: AiSearchShotTestRequest):
    try:
        config = _merge_stored_api_key_if_masked(request.config)
        result = await _test_rerank_config(config)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"测试 向量模型 召回模型失败: {e}")
        return {"success": False, "data": {"success": False, "message": str(e)}}
