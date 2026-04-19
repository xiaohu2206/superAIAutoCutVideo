from .openai_compatible_base import OpenAICompatibleClientBase


class YunwuClient(OpenAICompatibleClientBase):
    """
    云雾平台（OpenAI兼容接口）调用封装：
    - /v1/chat/completions 用于视觉理解与结构化生成
    - /v1/embeddings 用于向量化
    - /v1/rerank 用于重排
    """

    provider_name = "Yunwu"
    config_section_name = "yunwu"
    default_chat_completions_url = "https://yunwu.ai/v1/chat/completions"
    default_embeddings_url = "https://yunwu.ai/v1/embeddings"
    default_rerank_url = "https://yunwu.ai/v1/rerank"
