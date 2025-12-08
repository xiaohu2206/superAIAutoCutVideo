import argparse
import sys
from loguru import logger
import voice_manager

def main():
    parser = argparse.ArgumentParser(description="Edge TTS Standalone Generator")
    parser.add_argument("--text", "-t", type=str, help="Text to convert to speech", required=False)
    parser.add_argument("--file", "-f", type=str, help="File containing text to convert", required=False)
    parser.add_argument("--voice", "-v", type=str, default="zh-CN-XiaoxiaoNeural", help="Voice name (default: zh-CN-XiaoxiaoNeural)")
    parser.add_argument("--output", "-o", type=str, default="output.mp3", help="Output audio file path")
    parser.add_argument("--list-voices", "-l", action="store_true", help="List available voices")
    parser.add_argument("--rate", "-r", type=float, default=1.0, help="Voice rate (default: 1.0)")
    parser.add_argument("--pitch", "-p", type=float, default=1.0, help="Voice pitch (default: 1.0)")
    parser.add_argument("--proxy", type=str, help="HTTP Proxy (e.g., http://127.0.0.1:7890)")

    args = parser.parse_args()

    if args.list_voices:
        voices = voice_manager.get_all_azure_voices()
        print(f"Found {len(voices)} voices:")
        for v in voices:
            print(v)
        return

    text = args.text
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return

    if not text:
        # Check if piped input
        if not sys.stdin.isatty():
            text = sys.stdin.read().strip()
        
    if not text:
        logger.error("Please provide text using --text, --file, or piped input")
        return

    logger.info(f"Generating audio for text: {text[:50]}...")
    logger.info(f"Voice: {args.voice}, Rate: {args.rate}, Pitch: {args.pitch}")

    sub_maker = voice_manager.generate_audio(
        text=text,
        voice_name=args.voice,
        voice_file=args.output,
        voice_rate=args.rate,
        voice_pitch=args.pitch,
        proxy=args.proxy
    )

    if sub_maker:
        logger.success(f"Audio generated successfully: {args.output}")
        # Optionally generate subtitle
        subtitle_file = args.output.rsplit('.', 1)[0] + ".srt"
        try:
            voice_manager.create_subtitle(sub_maker, text, subtitle_file)
            logger.info(f"Subtitle generated: {subtitle_file}")
        except Exception as e:
            logger.error(f"Failed to generate subtitle: {e}")
    else:
        logger.error("Failed to generate audio")

if __name__ == "__main__":
    main()
