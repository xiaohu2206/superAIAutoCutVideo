import argparse
import concurrent.futures
import os
import shutil
import subprocess
from pathlib import Path
from typing import List


VIDEO_FILE = "b日m想j.2013.BD1080p.中文字幕.mp4"
OUTPUT_ROOT = Path("output")
CONCURRENT_DIR = OUTPUT_ROOT / "frames_concurrent"
FRAME_COUNT = 1000
DEFAULT_MAX_WORKERS = min(16, (os.cpu_count() or 4))
IMAGE_QUALITY = 2
PROGRESS_INTERVAL = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="并发视频抽帧")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"并发抽帧的并发数，默认 {DEFAULT_MAX_WORKERS}",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=FRAME_COUNT,
        help=f"需要抽取的帧数，默认 {FRAME_COUNT}",
    )
    parser.add_argument(
        "--video",
        default=VIDEO_FILE,
        help=f"视频文件路径，默认 {VIDEO_FILE}",
    )
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers 必须大于等于 1")
    if args.frames < 1:
        parser.error("--frames 必须大于等于 1")

    return args


def run_command(command: List[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_video_duration(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    output = subprocess.check_output(command, text=True).strip()
    return float(output)


def prepare_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def build_timestamps(duration: float, frame_count: int) -> List[float]:
    step = duration / frame_count
    return [min(index * step, max(duration - 0.001, 0)) for index in range(frame_count)]


def extract_one_frame(video_path: Path, timestamp: float, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        str(IMAGE_QUALITY),
        str(output_path),
    ]
    run_command(command)


def extract_frames_concurrent(video_path: Path, timestamps: List[float], output_dir: Path, max_workers: int) -> List[Path]:
    frame_paths = [output_dir / f"frame_{index:04d}.jpg" for index in range(1, len(timestamps) + 1)]
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(extract_one_frame, video_path, timestamp, frame_path): frame_path
            for timestamp, frame_path in zip(timestamps, frame_paths)
        }
        for future in concurrent.futures.as_completed(future_map):
            future.result()
            completed += 1
            if completed % PROGRESS_INTERVAL == 0:
                print(f"[concurrent] 已抽帧 {completed}/{len(frame_paths)}")

    return frame_paths


def main() -> None:
    args = parse_args()
    video_path = Path(args.video)
    if not video_path.exists():
        raise FileNotFoundError(f"未找到视频文件: {video_path}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    prepare_directory(CONCURRENT_DIR)
    duration = get_video_duration(video_path)
    timestamps = build_timestamps(duration, args.frames)

    print("开始执行并发抽帧...")
    frame_paths = extract_frames_concurrent(video_path, timestamps, CONCURRENT_DIR, args.workers)
    print(f"并发抽帧完成，共生成 {len(frame_paths)} 张图片，输出目录: {CONCURRENT_DIR}")


if __name__ == "__main__":
    main()
