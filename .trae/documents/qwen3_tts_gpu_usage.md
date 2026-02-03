# Qwen3‑TTS GPU 使用与设备策略

## 总览
- 目标：在可用 GPU 的情况下，始终在 GPU 上运行 Qwen3‑TTS；禁止自动回退到 CPU；避免设备不一致导致的推理错误。
- 核心位置：
  - 设备检测与偏好：[detector.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/modules/qwen3_tts_acceleration/detector.py)
  - 模型加载与设备/精度策略：[qwen3_tts_service.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/modules/qwen3_tts_service.py)
  - 路由透传设备设置：[tts_routes.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/routes/tts_routes.py)

## 设备检测
- 通过 `get_qwen3_tts_acceleration_status()` 获取当前系统的 CUDA 支持、GPU 信息（名称、显存、算力）、Torch 版本等。
- 若 `supported=True`，`get_qwen3_tts_preferred_device()` 返回 `"cuda:0"`；否则返回 `"cpu"`。

## 设备选择优先级
- 显式配置优先：如果 TTS 配置中设置了 `Device`（如 `"cuda:0"` 或 `"cpu"`），将直接使用该设备。
- 未显式设置时：根据检测结果选择设备，GPU 可用则使用 `"cuda:0"`，否则 `"cpu"`。

## 模型加载参数与一致性保证
- 在 GPU 可用时：
  - 通过 `Qwen3TTSModel.from_pretrained(..., device_map="cuda:0", dtype=torch.float16, attn_implementation="sdpa")` 进行加载。
  - 将模型主体迁移到目标设备 `cuda:0`，确保后续推理的张量与模块创建在同一设备。
  - 选择 `sdpa` 作为注意力实现，以避免在 Windows 环境下缺少 FlashAttention 2 的兼容性问题；若已安装 FlashAttention 2，可改为 `flash_attention_2` 并使用 `torch.bfloat16`。
- 在 CPU 模式：
  - 使用 `device_map="cpu", dtype=torch.float32` 加载模型。
  - 显式确保模型 dtype 为 `float32`，避免在 CPU 上触发 Half/BFloat16 算子不支持问题（如 `replication_pad1d not implemented for 'Half'`）。

## 禁止回退到 CPU 的策略
- 当选择设备为 `"cuda:0"`（检测或配置），如果迁移到 GPU 失败，直接抛出错误（`model_to_device_failed: ...`），不再回退至 CPU。
- 这样能显式暴露环境问题（驱动、CUDA 运行库、显存不足、Torch 版本不匹配等），便于排查修复。

## 路由与配置传参
- 试听接口会从 TTS 配置读取 `extra_params.Device` 并传递到服务层：
  - 路由位置参考：[tts_routes.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/routes/tts_routes.py#L604-L611)。
  - 建议在设置中将 `Device` 显式设为 `"cuda:0"`，确保强制 GPU 模式。

## 常见错误与排查
- `"replication_pad1d not implemented for 'Half'"`：通常是 CPU 上以 Half 精度运行导致，使用 `float32` 加载/运行即可；或确保严格在 GPU 上运行，避免设备混用。
- `"Expected all tensors to be on the same device, but found ... cuda:0 and cpu"`：表示推理链路中混用了 CUDA 与 CPU 张量；需检查加载参数 `device_map/dtype/attn_implementation`、确保所有延迟初始化组件在同一设备上创建。
- `"model_to_device_failed: ..."`：表示迁移到指定设备失败；需检查显卡驱动、CUDA 运行库与 PyTorch CUDA 版本匹配、显存充足等。

## 快速验证命令（终端）
```bash
# CUDA 是否可用、设备数量
python -c "import torch; print('cuda_available=', torch.cuda.is_available()); print('device_count=', torch.cuda.device_count())"

# 查看设备属性与算力
python -c "import torch; p=torch.cuda.get_device_properties(0); c=torch.cuda.get_device_capability(0); print('name=',p.name); print('total_memory_bytes=',p.total_memory); print('compute_capability=',c)"
```

## 性能与注意事项
- GPU 模式优先使用 `torch.float16` 与 `sdpa` 注意力以兼容 Windows；如具备 FlashAttention 2，推荐使用 `torch.bfloat16 + flash_attention_2` 获取更佳性能。
- 显存较小（约 4GB）可优先选择 0.6B 模型；1.7B 模型对显存与带宽要求更高。

## 相关代码参考
- 设备检测与偏好：[detector.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/modules/qwen3_tts_acceleration/detector.py)
- 模型加载与设备/精度策略：[qwen3_tts_service.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/modules/qwen3_tts_service.py)
- 试听路由设备传参：[tts_routes.py](file:///c:/Users/Administrator/Documents/superAIAutoCutVideo/backend/routes/tts_routes.py)
