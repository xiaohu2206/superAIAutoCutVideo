# Edge TTS Standalone Generator

This project extracts the Edge TTS generation logic from NarratoAI into a standalone Python script.

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Command Line Interface

Run `main.py` to generate audio from text.

**List available voices:**

```bash
python main.py --list-voices
```

**Generate audio from text:**

```bash
python main.py --text "Hello, this is a test." --output output.mp3
python main.py --text "你好，这是一个测试音频。" --output hello.mp3 --voice zh-CN-XiaoxiaoNeural
```

**Generate audio from file:**

```bash
python main.py --file input.txt --output output.mp3
```

**Specify voice, rate, and pitch:**

```bash
python main.py --text "Hello" --voice en-US-AriaNeural --rate 1.2 --pitch 1.1
```

**Use Proxy:**

```bash
python main.py --text "Hello" --proxy http://127.0.0.1:7890
```

## File Structure

- `main.py`: Entry point and CLI interface.
- `voice_manager.py`: Core TTS logic (extracted from `app/services/voice.py`).
- `utils.py`: Helper functions for time conversion and text processing.
- `requirements.txt`: Project dependencies.
