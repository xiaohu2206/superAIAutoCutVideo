# Edge TTS Component

此文件夹包含从 NarratoAI 提取的 Edge TTS 设置组件，可轻松集成到其他 Streamlit 项目中。

## 文件结构

- `component.py`: 包含 `render_edge_tts_settings` 函数，用于渲染 UI。
- `voice_utils.py`: 包含 `get_all_azure_voices` 函数和硬编码的语音列表。
- `__init__.py`: 导出主要函数。

## 使用方法

1. 将 `edge_tts_component` 文件夹复制到你的 Streamlit 项目中。
2. 在你的代码中导入并使用：

```python
import streamlit as st
from edge_tts_component import render_edge_tts_settings

st.title("Edge TTS 设置示例")

# 简单的翻译函数示例（可选）
def tr(key):
    translations = {
        "Female": "女声",
        "Male": "男声"
    }
    return translations.get(key, key)

# 渲染组件
render_edge_tts_settings(tr)

# 获取设置值
st.write("---")
st.write("当前的设置值：")
st.write(f"音色名称 (edge_voice_name): {st.session_state.get('edge_voice_name')}")
st.write(f"音量 (edge_volume): {st.session_state.get('edge_volume')}")
st.write(f"语速 (edge_rate): {st.session_state.get('edge_rate')}")
st.write(f"语调 (edge_pitch): {st.session_state.get('edge_pitch')}")
st.write(f"计算后的音量 (voice_volume): {st.session_state.get('voice_volume')}")
st.write(f"计算后的语调 (voice_pitch): {st.session_state.get('voice_pitch')}")
```

## 依赖

- `streamlit`

无需额外的 `config` 或 `voice` 模块依赖，所有必要的数据都包含在 `voice_utils.py` 中。
