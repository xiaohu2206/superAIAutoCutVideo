import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.qwen3_tts_service import _ensure_torch_cpu_half_replication_pad_patch


def main() -> None:
    import torch.nn.functional as F
    pad_alias = F.pad

    _ensure_torch_cpu_half_replication_pad_patch()

    x = torch.randn(1, 1, 8, dtype=torch.float16)
    y = torch._C._nn.replication_pad1d(x, (2, 2))
    print("cpu replication_pad1d ok", tuple(y.shape), y.dtype, y.device.type)

    y2 = pad_alias(x, (2, 2), mode="replicate")
    print("cpu F.pad alias ok", tuple(y2.shape), y2.dtype, y2.device.type)

    try:
        import torch.nn as nn

        m = nn.ReplicationPad1d((2, 2))
        y3 = m(x)
        print("cpu nn.ReplicationPad1d ok", tuple(y3.shape), y3.dtype, y3.device.type)
    except Exception as e:
        print("cpu nn.ReplicationPad1d error", repr(e))

    if torch.cuda.is_available():
        xc = x.to("cuda")
        yc = torch._C._nn.replication_pad1d(xc, (2, 2))
        print("cuda replication_pad1d ok", tuple(yc.shape), yc.dtype, yc.device.type)


if __name__ == "__main__":
    main()
