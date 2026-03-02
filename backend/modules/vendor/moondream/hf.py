import torch
from transformers import AutoModelForCausalLM

LATEST_REVISION = "2025-06-21"


def detect_device():
    if torch.backends.mps.is_available():
        return torch.device("mps"), torch.float16
    if torch.cuda.is_available():
        return torch.device("cuda"), torch.bfloat16
    return torch.device("cpu"), torch.float32


class Moondream:
    @classmethod
    def from_pretrained(cls, model_id, revision=None, torch_dtype=None, **kwargs):
        return AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            revision=revision,
            torch_dtype=torch_dtype,
            **kwargs,
        )

