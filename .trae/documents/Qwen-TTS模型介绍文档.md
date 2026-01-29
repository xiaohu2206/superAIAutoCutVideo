### 自定义语音生成
对于自定义语音模型（Qwen3-TTS-12Hz-1.7B/0.6B-CustomVoice），你只需调用 generate_custom_voice，传入单个字符串或一批字符串列表，以及 language、speaker 和可选的 instruct 参数。你也可以调用 model.get_supported_speakers() 和 model.get_supported_languages() 查看当前模型支持的说话人和语言。

```python
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

# single inference
wavs, sr = model.generate_custom_voice(
    text="其实我真的有发现，我是一个特别善于观察别人情绪的人。",
    language="Chinese", # Pass `Auto` (or omit) for auto language adaptive; if the target language is known, set it explicitly.
    speaker="Vivian",
    instruct="用特别愤怒的语气说", # Omit if not needed.
)
sf.write("output_custom_voice.wav", wavs[0], sr)

# batch inference
wavs, sr = model.generate_custom_voice(
    text=[
        "其实我真的有发现，我是一个特别善于观察别人情绪的人。", 
        "She said she would be here by noon."
    ],
    language=["Chinese", "English"],
    speaker=["Vivian", "Ryan"],
    instruct=["", "Very happy."]
)
sf.write("output_custom_voice_1.wav", wavs[0], sr)
sf.write("output_custom_voice_2.wav", wavs[1], sr)
```

对于 Qwen3-TTS-12Hz-1.7B/0.6B-CustomVoice 模型，支持的说话人列表及其语音描述如下所示。我们建议使用每位说话人的母语以获得最佳音质。当然，每位说话人都可以说出该模型支持的任何语言。

说话人	语音描述	母语
Vivian	明亮、略带锐利感的年轻女声。	中文
Serena	温暖柔和的年轻女声。	中文
Uncle_Fu	音色低沉醇厚的成熟男声。	中文
Dylan	清晰自然的北京青年男声。	中文（北京方言）
Eric	略带沙哑但明亮活泼的成都男声。	中文（四川方言）
Ryan	富有节奏感的动态男声。	英语
Aiden	清晰中频、阳光的美式男声。	英语
Ono_Anna	轻快灵动的俏皮日语女声。	日语
Sohee	情感丰富的温暖韩语女声。	韩语
语音设计
对于语音设计模型（Qwen3-TTS-12Hz-1.7B-VoiceDesign），你可以使用 generate_voice_design 提供目标文本和自然语言形式的 instruct 描述。

```python
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

# single inference
wavs, sr = model.generate_voice_design(
    text="哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
    language="Chinese",
    instruct="体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显，营造出黏人、做作又刻意卖萌的听觉效果。",
)
sf.write("output_voice_design.wav", wavs[0], sr)

# batch inference
wavs, sr = model.generate_voice_design(
    text=[
      "哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
      "It's in the top drawer... wait, it's empty? No way, that's impossible! I'm sure I put it there!"
    ],
    language=["Chinese", "English"],
    instruct=[
      "体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显，营造出黏人、做作又刻意卖萌的听觉效果。",
      "Speak in an incredulous tone, but with a hint of panic beginning to creep into your voice."
    ]
)
sf.write("output_voice_design_1.wav", wavs[0], sr)
sf.write("output_voice_design_2.wav", wavs[1], sr)
```
### 语音克隆
对于语音克隆模型（Qwen3-TTS-12Hz-1.7B/0.6B-Base），要克隆语音并合成新内容，你只需提供一段参考音频（ref_audio）及其对应的文本（ref_text）。ref_audio 可以是本地文件路径、URL、base64 字符串，或一个 (numpy_array, sample_rate) 元组。如果设置 x_vector_only_mode=True，则仅使用说话人嵌入，此时无需提供 ref_text，但克隆质量可能会有所下降。

```python
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

ref_audio = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav"
ref_text  = "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you."

wavs, sr = model.generate_voice_clone(
    text="I am solving the equation: x = [-b ± √(b²-4ac)] / 2a? Nobody can — it's a disaster (◍•͈⌔•͈◍), very sad!",
    language="English",
    ref_audio=ref_audio,
    ref_text=ref_text,
)
sf.write("output_voice_clone.wav", wavs[0], sr)
```

如果你需要在多次生成中复用相同的参考提示（避免重复计算提示特征），请先使用 create_voice_clone_prompt 构建一次提示，并通过 voice_clone_prompt 传入。
```python
prompt_items = model.create_voice_clone_prompt(
    ref_audio=ref_audio,
    ref_text=ref_text,
    x_vector_only_mode=False,
)
wavs, sr = model.generate_voice_clone(
    text=["Sentence A.", "Sentence B."],
    language=["English", "English"],
    voice_clone_prompt=prompt_items,
)
sf.write("output_voice_clone_1.wav", wavs[0], sr)
sf.write("output_voice_clone_2.wav", wavs[1], sr)
```
有关可复用语音克隆提示、批量克隆和批量推理的更多示例，请参阅 示例代码。结合这些示例和 generate_voice_clone 函数的说明，你可以探索更高级的使用方式。

### 语音设计后克隆
如果你想获得一个可像克隆说话人一样复用的设计语音，一个实用的工作流程是：(1) 使用 VoiceDesign 模型合成一段符合目标角色特征的短参考音频；(2) 将该音频输入 create_voice_clone_prompt 以构建可复用的提示；(3) 在后续生成新内容时，通过 voice_clone_prompt 调用 generate_voice_clone，无需每次都重新提取特征。当你希望在多段文本中保持一致的角色语音时，这种方法尤其有用。

```python

import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

# create a reference audio in the target style using the VoiceDesign model
design_model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

ref_text = "H-hey! You dropped your... uh... calculus notebook? I mean, I think it's yours? Maybe?"
ref_instruct = "Male, 17 years old, tenor range, gaining confidence - deeper breath support now, though vowels still tighten when nervous"
ref_wavs, sr = design_model.generate_voice_design(
    text=ref_text,
    language="English",
    instruct=ref_instruct
)
sf.write("voice_design_reference.wav", ref_wavs[0], sr)

# build a reusable clone prompt from the voice design reference
clone_model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

voice_clone_prompt = clone_model.create_voice_clone_prompt(
    ref_audio=(ref_wavs[0], sr),   # or "voice_design_reference.wav"
    ref_text=ref_text,
)

sentences = [
    "No problem! I actually... kinda finished those already? If you want to compare answers or something...",
    "What? No! I mean yes but not like... I just think you're... your titration technique is really precise!",
]

# reuse it for multiple single calls
wavs, sr = clone_model.generate_voice_clone(
    text=sentences[0],
    language="English",
    voice_clone_prompt=voice_clone_prompt,
)
sf.write("clone_single_1.wav", wavs[0], sr)

wavs, sr = clone_model.generate_voice_clone(
    text=sentences[1],
    language="English",
    voice_clone_prompt=voice_clone_prompt,
)
sf.write("clone_single_2.wav", wavs[0], sr)

# or batch generate in one call
wavs, sr = clone_model.generate_voice_clone(
    text=sentences,
    language=["English", "English"],
    voice_clone_prompt=voice_clone_prompt,
)
for i, w in enumerate(wavs):
    sf.write(f"clone_batch_{i}.wav", w, sr)

```