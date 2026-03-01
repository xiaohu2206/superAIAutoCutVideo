import math
import os
import time
import threading
from typing import Callable, Optional

import numpy as np


class _TorchNetNotAvailable(RuntimeError):
    pass


def _import_torch():
    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        import torch.nn.functional as functional  # type: ignore
    except Exception as e:
        raise _TorchNetNotAvailable(str(e))
    return torch, nn, functional


torch, nn, functional = _import_torch()


class _TransNetV2Net(nn.Module):
    def __init__(
        self,
        F=16,
        L=3,
        S=2,
        D=1024,
        use_many_hot_targets=True,
        use_frame_similarity=True,
        use_color_histograms=True,
        use_mean_pooling=False,
        dropout_rate=0.5,
        use_convex_comb_reg=False,
        use_resnet_features=False,
        use_resnet_like_top=False,
        frame_similarity_on_last_layer=False,
    ):
        super().__init__()

        if use_resnet_features or use_resnet_like_top or use_convex_comb_reg or frame_similarity_on_last_layer:
            raise RuntimeError("Some options not implemented in Pytorch version of Transnet!")

        self.SDDCNN = nn.ModuleList(
            [_StackedDDCNNV2(in_filters=3, n_blocks=S, filters=F, stochastic_depth_drop_prob=0.0)]
            + [
                _StackedDDCNNV2(in_filters=(F * 2 ** (i - 1)) * 4, n_blocks=S, filters=F * 2 ** i)
                for i in range(1, L)
            ]
        )

        self.frame_sim_layer = (
            _FrameSimilarity(
                sum([(F * 2 ** i) * 4 for i in range(L)]),
                lookup_window=101,
                output_dim=128,
                similarity_dim=128,
                use_bias=True,
            )
            if use_frame_similarity
            else None
        )
        self.color_hist_layer = _ColorHistograms(lookup_window=101, output_dim=128) if use_color_histograms else None

        self.dropout = nn.Dropout(dropout_rate) if dropout_rate is not None else None

        output_dim = ((F * 2 ** (L - 1)) * 4) * 3 * 6
        if use_frame_similarity:
            output_dim += 128
        if use_color_histograms:
            output_dim += 128

        self.fc1 = nn.Linear(output_dim, D)
        self.cls_layer1 = nn.Linear(D, 1)
        self.cls_layer2 = nn.Linear(D, 1) if use_many_hot_targets else None

        self.use_mean_pooling = use_mean_pooling
        self.eval()

    def forward(self, inputs):
        assert isinstance(inputs, torch.Tensor) and list(inputs.shape[2:]) == [27, 48, 3] and inputs.dtype == torch.uint8

        x = inputs.permute([0, 4, 1, 2, 3]).float()
        x = x.div_(255.0)

        block_features = []
        for block in self.SDDCNN:
            x = block(x)
            block_features.append(x)

        if self.use_mean_pooling:
            x = torch.mean(x, dim=[3, 4])
            x = x.permute(0, 2, 1)
        else:
            x = x.permute(0, 2, 3, 4, 1)
            x = x.reshape(x.shape[0], x.shape[1], -1)

        if self.frame_sim_layer is not None:
            x = torch.cat([self.frame_sim_layer(block_features), x], 2)

        if self.color_hist_layer is not None:
            x = torch.cat([self.color_hist_layer(inputs), x], 2)

        x = self.fc1(x)
        x = functional.relu(x)

        if self.dropout is not None:
            x = self.dropout(x)

        one_hot = self.cls_layer1(x)
        if self.cls_layer2 is not None:
            return one_hot, {"many_hot": self.cls_layer2(x)}
        return one_hot


class _StackedDDCNNV2(nn.Module):
    def __init__(
        self,
        in_filters,
        n_blocks,
        filters,
        shortcut=True,
        use_octave_conv=False,
        pool_type="avg",
        stochastic_depth_drop_prob=0.0,
    ):
        super().__init__()

        if use_octave_conv:
            raise RuntimeError("Octave convolution not implemented in Pytorch version of Transnet!")

        assert pool_type == "max" or pool_type == "avg"

        self.shortcut = shortcut
        self.DDCNN = nn.ModuleList(
            [
                _DilatedDCNNV2(
                    in_filters if i == 1 else filters * 4,
                    filters,
                    octave_conv=use_octave_conv,
                    activation=functional.relu if i != n_blocks else None,
                )
                for i in range(1, n_blocks + 1)
            ]
        )
        self.pool = nn.MaxPool3d(kernel_size=(1, 2, 2)) if pool_type == "max" else nn.AvgPool3d(kernel_size=(1, 2, 2))
        self.stochastic_depth_drop_prob = stochastic_depth_drop_prob

    def forward(self, inputs):
        x = inputs
        shortcut = None
        for block in self.DDCNN:
            x = block(x)
            if shortcut is None:
                shortcut = x

        x = functional.relu(x)

        if self.shortcut is not None:
            if self.stochastic_depth_drop_prob != 0.0:
                if self.training:
                    if random.random() < self.stochastic_depth_drop_prob:
                        x = shortcut
                    else:
                        x = x + shortcut
                else:
                    x = (1 - self.stochastic_depth_drop_prob) * x + shortcut
            else:
                x += shortcut

        x = self.pool(x)
        return x


class _DilatedDCNNV2(nn.Module):
    def __init__(self, in_filters, filters, batch_norm=True, activation=None, octave_conv=False):
        super().__init__()
        if octave_conv:
            raise RuntimeError("Octave convolution not implemented in Pytorch version of Transnet!")
        assert not (octave_conv and batch_norm)

        self.Conv3D_1 = _Conv3DConfigurable(in_filters, filters, 1, use_bias=not batch_norm)
        self.Conv3D_2 = _Conv3DConfigurable(in_filters, filters, 2, use_bias=not batch_norm)
        self.Conv3D_4 = _Conv3DConfigurable(in_filters, filters, 4, use_bias=not batch_norm)
        self.Conv3D_8 = _Conv3DConfigurable(in_filters, filters, 8, use_bias=not batch_norm)

        self.bn = nn.BatchNorm3d(filters * 4, eps=1e-3) if batch_norm else None
        self.activation = activation

    def forward(self, inputs):
        conv1 = self.Conv3D_1(inputs)
        conv2 = self.Conv3D_2(inputs)
        conv3 = self.Conv3D_4(inputs)
        conv4 = self.Conv3D_8(inputs)

        x = torch.cat([conv1, conv2, conv3, conv4], dim=1)
        if self.bn is not None:
            x = self.bn(x)
        if self.activation is not None:
            x = self.activation(x)
        return x


class _Conv3DConfigurable(nn.Module):
    def __init__(self, in_filters, filters, dilation_rate, separable=True, octave=False, use_bias=True, kernel_initializer=None):
        super().__init__()
        if octave:
            raise RuntimeError("Octave convolution not implemented in Pytorch version of Transnet!")
        if kernel_initializer is not None:
            raise RuntimeError("Kernel initializers are not implemented in Pytorch version of Transnet!")
        assert not (separable and octave)

        if separable:
            conv1 = nn.Conv3d(
                in_filters,
                2 * filters,
                kernel_size=(1, 3, 3),
                dilation=(1, 1, 1),
                padding=(0, 1, 1),
                bias=False,
            )
            conv2 = nn.Conv3d(
                2 * filters,
                filters,
                kernel_size=(3, 1, 1),
                dilation=(dilation_rate, 1, 1),
                padding=(dilation_rate, 0, 0),
                bias=use_bias,
            )
            self.layers = nn.ModuleList([conv1, conv2])
        else:
            conv = nn.Conv3d(
                in_filters,
                filters,
                kernel_size=3,
                dilation=(dilation_rate, 1, 1),
                padding=(dilation_rate, 1, 1),
                bias=use_bias,
            )
            self.layers = nn.ModuleList([conv])

    def forward(self, inputs):
        x = inputs
        for layer in self.layers:
            x = layer(x)
        return x


class _FrameSimilarity(nn.Module):
    def __init__(self, in_filters, similarity_dim=128, lookup_window=101, output_dim=128, stop_gradient=False, use_bias=False):
        super().__init__()
        if stop_gradient:
            raise RuntimeError("Stop gradient not implemented in Pytorch version of Transnet!")

        self.projection = nn.Linear(in_filters, similarity_dim, bias=use_bias)
        self.fc = nn.Linear(lookup_window, output_dim)

        self.lookup_window = lookup_window
        assert lookup_window % 2 == 1

    def forward(self, inputs):
        x = torch.cat([torch.mean(x, dim=[3, 4]) for x in inputs], dim=1)
        x = torch.transpose(x, 1, 2)

        x = self.projection(x)
        x = functional.normalize(x, p=2, dim=2)

        batch_size, time_window = x.shape[0], x.shape[1]
        similarities = torch.bmm(x, x.transpose(1, 2))
        similarities_padded = functional.pad(similarities, [(self.lookup_window - 1) // 2, (self.lookup_window - 1) // 2])

        batch_indices = torch.arange(0, batch_size, device=x.device).view([batch_size, 1, 1]).repeat(
            [1, time_window, self.lookup_window]
        )
        time_indices = torch.arange(0, time_window, device=x.device).view([1, time_window, 1]).repeat(
            [batch_size, 1, self.lookup_window]
        )
        lookup_indices = (
            torch.arange(0, self.lookup_window, device=x.device).view([1, 1, self.lookup_window]).repeat([batch_size, time_window, 1])
            + time_indices
        )

        similarities = similarities_padded[batch_indices, time_indices, lookup_indices]
        return functional.relu(self.fc(similarities))


class _ColorHistograms(nn.Module):
    def __init__(self, lookup_window=101, output_dim=None):
        super().__init__()
        self.fc = nn.Linear(lookup_window, output_dim) if output_dim is not None else None
        self.lookup_window = lookup_window
        assert lookup_window % 2 == 1

    @staticmethod
    def compute_color_histograms(frames):
        frames = frames.int()

        def get_bin(frames_):
            R, G, B = frames_[:, :, 0], frames_[:, :, 1], frames_[:, :, 2]
            R, G, B = R >> 5, G >> 5, B >> 5
            return (R << 6) + (G << 3) + B

        batch_size, time_window, height, width, no_channels = frames.shape
        assert no_channels == 3
        frames_flatten = frames.view(batch_size * time_window, height * width, 3)

        binned_values = get_bin(frames_flatten)
        frame_bin_prefix = (torch.arange(0, batch_size * time_window, device=frames.device) << 9).view(-1, 1)
        binned_values = (binned_values + frame_bin_prefix).view(-1)

        histograms = torch.zeros(batch_size * time_window * 512, dtype=torch.int32, device=frames.device)
        histograms.scatter_add_(0, binned_values, torch.ones(len(binned_values), dtype=torch.int32, device=frames.device))

        histograms = histograms.view(batch_size, time_window, 512).float()
        histograms_normalized = functional.normalize(histograms, p=2, dim=2)
        return histograms_normalized

    def forward(self, inputs):
        x = self.compute_color_histograms(inputs)

        batch_size, time_window = x.shape[0], x.shape[1]
        similarities = torch.bmm(x, x.transpose(1, 2))
        similarities_padded = functional.pad(similarities, [(self.lookup_window - 1) // 2, (self.lookup_window - 1) // 2])

        batch_indices = torch.arange(0, batch_size, device=x.device).view([batch_size, 1, 1]).repeat(
            [1, time_window, self.lookup_window]
        )
        time_indices = torch.arange(0, time_window, device=x.device).view([1, time_window, 1]).repeat(
            [batch_size, 1, self.lookup_window]
        )
        lookup_indices = (
            torch.arange(0, self.lookup_window, device=x.device).view([1, 1, self.lookup_window]).repeat([batch_size, time_window, 1])
            + time_indices
        )

        similarities = similarities_padded[batch_indices, time_indices, lookup_indices]
        if self.fc is not None:
            return functional.relu(self.fc(similarities))
        return similarities


import random


class TransNetV2Torch:
    def __init__(self, model_dir: str, device: Optional[str] = None):
        self._device = self._resolve_device(device)
        self._lock = threading.Lock()
        self._model = _TransNetV2Net()

        weights_path = os.environ.get("TRANSNETV2_PYTORCH_WEIGHTS")
        if weights_path:
            w = weights_path
        else:
            w = os.path.join(model_dir, "transnetv2-pytorch-weights.pth")
        state = torch.load(w, map_location="cpu")
        if isinstance(state, dict) and ("state_dict" in state) and isinstance(state["state_dict"], dict):
            state = state["state_dict"]
        self._model.load_state_dict(state)
        self._model.eval()
        self._model.to(self._device)

    def _resolve_device(self, device: Optional[str]) -> torch.device:
        raw = str(device or os.environ.get("TRANSNETV2_DEVICE") or "auto").strip().lower()
        if raw in {"auto", ""}:
            return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        if raw.startswith("cuda") and not torch.cuda.is_available():
            return torch.device("cpu")
        try:
            return torch.device(raw)
        except Exception:
            return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

    def get_backend_info(self) -> dict:
        return {"backend": "torch", "device": str(self._device)}

    def predict_raw(self, frames: np.ndarray):
        if not isinstance(frames, np.ndarray):
            raise ValueError("frames must be numpy array")
        if frames.dtype != np.uint8:
            frames = frames.astype(np.uint8, copy=False)
        if len(frames.shape) != 5 or list(frames.shape[2:]) != [27, 48, 3]:
            raise ValueError("frames shape must be [B, T, 27, 48, 3]")

        x = torch.from_numpy(frames)
        if not x.is_contiguous():
            x = x.contiguous()
        x = x.to(device=self._device, non_blocking=True)
        with self._lock:
            with torch.no_grad():
                out = self._model(x)

        if isinstance(out, tuple):
            logits, d = out
            many = d.get("many_hot")
        else:
            logits = out
            many = None

        single = torch.sigmoid(logits).detach().cpu().numpy()
        if many is not None:
            many_hot = torch.sigmoid(many).detach().cpu().numpy()
        else:
            many_hot = None
        return single, many_hot

    def predict_frames(self, frames: np.ndarray, progress_callback: Optional[Callable[[float], None]] = None):
        if not isinstance(frames, np.ndarray):
            raise ValueError("frames must be numpy array")
        if frames.dtype != np.uint8:
            frames = frames.astype(np.uint8, copy=False)
        if len(frames.shape) != 4 or list(frames.shape[1:]) != [27, 48, 3]:
            raise ValueError("frames shape must be [T, 27, 48, 3]")
        if len(frames) == 0:
            empty = np.zeros((0,), dtype=np.float32)
            return empty, empty

        no_padded_frames_start = 25
        no_padded_frames_end = 25 + 50 - (len(frames) % 50 if len(frames) % 50 != 0 else 50)
        start_frame = np.expand_dims(frames[0], 0)
        end_frame = np.expand_dims(frames[-1], 0)
        padded_inputs = np.concatenate(
            [start_frame] * no_padded_frames_start + [frames] + [end_frame] * no_padded_frames_end, 0
        )

        batch = max(1, int(os.environ.get("TRANSNETV2_TORCH_BATCH") or 4))
        preds_single = []
        preds_all = []
        window = 0
        total_windows = ((len(padded_inputs) - 100) // 50) + 1 if len(padded_inputs) >= 100 else 0

        ptr = 0
        buf = []
        while ptr + 100 <= len(padded_inputs):
            buf.append(padded_inputs[ptr:ptr + 100][np.newaxis])
            ptr += 50
            if len(buf) >= batch:
                inp = np.concatenate(buf, axis=0)
                single, many_hot = self.predict_raw(inp)
                for i in range(single.shape[0]):
                    preds_single.append(single[i, 25:75, 0])
                    if many_hot is not None:
                        preds_all.append(many_hot[i, 25:75, 0])
                    window += 1
                    if progress_callback:
                        current = min(window * 50, len(frames))
                        pct = (current / len(frames)) * 100.0 if len(frames) else 100.0
                        progress_callback(pct)
                buf = []

        if buf:
            inp = np.concatenate(buf, axis=0)
            single, many_hot = self.predict_raw(inp)
            for i in range(single.shape[0]):
                preds_single.append(single[i, 25:75, 0])
                if many_hot is not None:
                    preds_all.append(many_hot[i, 25:75, 0])
                window += 1
                if progress_callback:
                    current = min(window * 50, len(frames))
                    pct = (current / len(frames)) * 100.0 if len(frames) else 100.0
                    progress_callback(pct)

        single_frame_pred = np.concatenate(preds_single) if preds_single else np.zeros((0,), dtype=np.float32)
        all_frames_pred = np.concatenate(preds_all) if preds_all else np.zeros((0,), dtype=np.float32)
        return single_frame_pred[:len(frames)], all_frames_pred[:len(frames)]

    def predict_video(self, video_fn: str, progress_callback: Optional[Callable[[float], None]] = None, start_time: Optional[float] = None, duration: Optional[float] = None):
        try:
            import ffmpeg  # type: ignore
        except ModuleNotFoundError:
            raise ModuleNotFoundError("For `predict_video` function `ffmpeg` needs to be installed.")

        if progress_callback:
            progress_callback(1.0)

        inp = ffmpeg.input(video_fn, ss=start_time, t=duration) if (start_time is not None or duration is not None) else ffmpeg.input(video_fn)
        video_stream, _ = inp.output("pipe:", format="rawvideo", pix_fmt="rgb24", s="48x27").run(
            capture_stdout=True, capture_stderr=True
        )
        video = np.frombuffer(video_stream, np.uint8).reshape([-1, 27, 48, 3])

        def wrapped_callback(pct: float):
            if progress_callback:
                final_pct = 10.0 + (pct * 0.9)
                progress_callback(final_pct)

        return (video, *self.predict_frames(video, progress_callback=wrapped_callback))

    @staticmethod
    def predictions_to_scenes(predictions: np.ndarray, threshold: float = 0.5):
        if predictions is None or len(predictions) == 0:
            return np.zeros((0, 2), dtype=np.int32)
        predictions = (predictions > threshold).astype(np.uint8)
        scenes = []
        t, t_prev, start = -1, 0, 0
        for i, t in enumerate(predictions):
            if t_prev == 1 and t == 0:
                start = i
            if t_prev == 0 and t == 1 and i != 0:
                scenes.append([start, i])
            t_prev = t
        if t == 0:
            scenes.append([start, i])
        if len(scenes) == 0:
            return np.array([[0, len(predictions) - 1]], dtype=np.int32)
        return np.array(scenes, dtype=np.int32)
