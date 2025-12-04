import streamlit as st
from .voice_utils import get_all_azure_voices

def render_edge_tts_settings(tr=None):
    """渲染 Edge TTS 引擎设置"""
    if tr is None:
        tr = lambda x: x

    # 获取支持的语音列表
    support_locales = ["zh-CN", "en-US"]
    all_voices = get_all_azure_voices(filter_locals=support_locales)

    # 只保留标准版本的语音（Edge TTS专用，不包含V2）
    edge_voices = [v for v in all_voices if "-V2" not in v]

    # 创建友好的显示名称
    friendly_names = {}
    for v in edge_voices:
        friendly_names[v] = v.replace("Female", tr("Female")).replace("Male", tr("Male")).replace("Neural", "")

    # 获取保存的语音设置
    # 优先从 session_state 获取，如果没有则使用默认值
    saved_voice_name = st.session_state.get("edge_voice_name", "zh-CN-XiaoxiaoNeural-Female")

    # 确保保存的音色在可用列表中
    if saved_voice_name not in friendly_names:
        # 选择与UI语言匹配的第一个语音
        ui_lang = st.session_state.get("ui_language", "zh-CN")
        for v in edge_voices:
            if v.lower().startswith(ui_lang.lower()):
                saved_voice_name = v
                break
        else:
            # 如果没找到匹配的，使用第一个
            saved_voice_name = edge_voices[0] if edge_voices else ""

    # 音色选择下拉框（Edge TTS音色相对较少，保留下拉框）
    # 为了正确显示当前选中的项，我们需要找到它在 options 中的索引
    options = list(friendly_names.values())
    try:
        current_index = list(friendly_names.keys()).index(saved_voice_name)
    except ValueError:
        current_index = 0

    selected_friendly_name = st.selectbox(
        "音色选择",
        options=options,
        index=current_index,
        help="选择Edge TTS音色"
    )

    # 获取实际的语音名称
    voice_name = list(friendly_names.keys())[
        list(friendly_names.values()).index(selected_friendly_name)
    ]

    # 显示音色信息
    with st.expander("💡 Edge TTS 音色说明", expanded=False):
        st.write("**中文音色：**")
        zh_voices = [v for v in edge_voices if v.startswith("zh-CN")]
        for v in zh_voices:
            gender = "女声" if "Female" in v else "男声"
            name = v.replace("-Female", "").replace("-Male", "").replace("zh-CN-", "").replace("Neural", "")
            st.write(f"• {name} ({gender})")

        st.write("")
        st.write("**英文音色：**")
        en_voices = [v for v in edge_voices if v.startswith("en-US")][:5]  # 只显示前5个
        for v in en_voices:
            gender = "女声" if "Female" in v else "男声"
            name = v.replace("-Female", "").replace("-Male", "").replace("en-US-", "").replace("Neural", "")
            st.write(f"• {name} ({gender})")

        if len([v for v in edge_voices if v.startswith("en-US")]) > 5:
            st.write("• ... 更多英文音色")

    # 更新设置到 session_state
    st.session_state["edge_voice_name"] = voice_name
    st.session_state["voice_name"] = voice_name  # 兼容性

    # 音量调节
    default_volume = st.session_state.get("edge_volume", 80)
    voice_volume = st.slider(
        "音量调节",
        min_value=0,
        max_value=100,
        value=int(default_volume),
        step=1,
        help="调节语音音量 (0-100)"
    )
    st.session_state["edge_volume"] = voice_volume
    st.session_state['voice_volume'] = voice_volume / 100.0

    # 语速调节
    default_rate = st.session_state.get("edge_rate", 1.0)
    voice_rate = st.slider(
        "语速调节",
        min_value=0.5,
        max_value=2.0,
        value=float(default_rate),
        step=0.1,
        help="调节语音速度 (0.5-2.0倍速)"
    )
    st.session_state["edge_rate"] = voice_rate
    st.session_state['voice_rate'] = voice_rate

    # 语调调节
    default_pitch = st.session_state.get("edge_pitch", 0)
    voice_pitch = st.slider(
        "语调调节",
        min_value=-50,
        max_value=50,
        value=int(default_pitch),
        step=5,
        help="调节语音音调 (-50%到+50%)"
    )
    st.session_state["edge_pitch"] = voice_pitch
    # 转换为比例值
    st.session_state['voice_pitch'] = 1.0 + (voice_pitch / 100.0)
