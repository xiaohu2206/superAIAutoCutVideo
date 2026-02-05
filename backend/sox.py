import numpy as np


class Transformer:
    def __init__(self) -> None:
        self._db_level = None

    def norm(self, db_level: float = -6, **_kwargs):
        try:
            self._db_level = float(db_level)
        except Exception:
            self._db_level = None
        return self

    def build_array(self, input_array, sample_rate_in: int = 16000, **_kwargs):
        x = np.asarray(input_array, dtype=np.float32)
        if x.size == 0:
            return x
        if self._db_level is None:
            return x
        peak = float(np.max(np.abs(x)))
        if not np.isfinite(peak) or peak <= 0:
            return x
        target = float(10.0 ** (self._db_level / 20.0))
        scale = target / peak
        y = x * scale
        y = np.clip(y, -1.0, 1.0)
        return y
