import concurrent.futures
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List


VIDEO_FILE = "b日m想j.2013.BD1080p.中文字幕.mp4"
OUTPUT_ROOT = Path("output")
SYNC_DIR = OUTPUT_ROOT / "frames_sync"
CONCURRENT_DIR = OUTPUT_ROOT / "frames_concurrent"
RESULTS_FILE = OUTPUT_ROOT / "benchmark_results.json"
FRAME_COUNT = 1000
MODEL_DELAY_SECONDS = 0.12
MAX_WORKERS = min(16, (os.cpu_count() or 4))
IMAGE_QUALITY = 2
PROGRESS_INTERVAL = 100


@dataclass
class BenchmarkResult:
    mode: str
    frame_count: int
    extraction_seconds: float
    model_seconds: float
    total_seconds: float
    average_seconds_per_frame: float
    output_dir: str
    model_delay_seconds: float
    max_workers: int


class MockVisionModel:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def analyze(self, image_path: Path) -> dict:
        time.sleep(self.delay_seconds)
        return {
            "image": image_path.name,
            "summary": f"模拟分析完成: {image_path.name}",
            "tokens": 1200,
        }


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


def extract_frames_sync(video_path: Path, timestamps: List[float], output_dir: Path) -> List[Path]:
    frame_paths = []
    for index, timestamp in enumerate(timestamps, start=1):
        output_path = output_dir / f"frame_{index:04d}.jpg"
        extract_one_frame(video_path, timestamp, output_path)
        frame_paths.append(output_path)
        if index % PROGRESS_INTERVAL == 0:
            print(f"[sync] 已抽帧 {index}/{len(timestamps)}")
    return frame_paths


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


def run_model_sync(frame_paths: List[Path], model: MockVisionModel) -> None:
    for index, frame_path in enumerate(frame_paths, start=1):
        model.analyze(frame_path)
        if index % PROGRESS_INTERVAL == 0:
            print(f"[sync] 已完成模型分析 {index}/{len(frame_paths)}")


def run_model_concurrent(frame_paths: List[Path], model: MockVisionModel, max_workers: int) -> None:
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(model.analyze, frame_path) for frame_path in frame_paths]
        for future in concurrent.futures.as_completed(futures):
            future.result()
            completed += 1
            if completed % PROGRESS_INTERVAL == 0:
                print(f"[concurrent] 已完成模型分析 {completed}/{len(frame_paths)}")


def save_partial_result(result: BenchmarkResult) -> None:
    partial_path = OUTPUT_ROOT / f"partial_{result.mode}.json"
    partial_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")


def benchmark(mode: str, video_path: Path, timestamps: List[float], output_dir: Path, max_workers: int) -> BenchmarkResult:
    prepare_directory(output_dir)
    model = MockVisionModel(MODEL_DELAY_SECONDS)

    print(f"开始执行 {mode} 模式...")
    extract_start = time.perf_counter()
    if mode == "sync":
        frame_paths = extract_frames_sync(video_path, timestamps, output_dir)
    else:
        frame_paths = extract_frames_concurrent(video_path, timestamps, output_dir, max_workers)
    extraction_seconds = time.perf_counter() - extract_start
    print(f"{mode} 抽帧完成，用时 {extraction_seconds:.3f}s")

    model_start = time.perf_counter()
    if mode == "sync":
        run_model_sync(frame_paths, model)
    else:
        run_model_concurrent(frame_paths, model, max_workers)
    model_seconds = time.perf_counter() - model_start
    print(f"{mode} 模型分析完成，用时 {model_seconds:.3f}s")

    total_seconds = extraction_seconds + model_seconds
    result = BenchmarkResult(
        mode=mode,
        frame_count=len(timestamps),
        extraction_seconds=round(extraction_seconds, 3),
        model_seconds=round(model_seconds, 3),
        total_seconds=round(total_seconds, 3),
        average_seconds_per_frame=round(total_seconds / len(timestamps), 4),
        output_dir=str(output_dir),
        model_delay_seconds=MODEL_DELAY_SECONDS,
        max_workers=max_workers,
    )
    save_partial_result(result)
    return result


def main() -> None:
    video_path = Path(VIDEO_FILE)
    if not video_path.exists():
        raise FileNotFoundError(f"未找到视频文件: {video_path}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    duration = get_video_duration(video_path)
    timestamps = build_timestamps(duration, FRAME_COUNT)

    sync_result = benchmark("sync", video_path, timestamps, SYNC_DIR, 1)
    concurrent_result = benchmark("concurrent", video_path, timestamps, CONCURRENT_DIR, MAX_WORKERS)

    summary = {
        "video_file": VIDEO_FILE,
        "video_duration_seconds": round(duration, 3),
        "frame_count": FRAME_COUNT,
        "model_delay_seconds_per_image": MODEL_DELAY_SECONDS,
        "results": [asdict(sync_result), asdict(concurrent_result)],
        "speedup_total": round(sync_result.total_seconds / concurrent_result.total_seconds, 2),
        "speedup_extraction": round(sync_result.extraction_seconds / concurrent_result.extraction_seconds, 2),
        "speedup_model": round(sync_result.model_seconds / concurrent_result.model_seconds, 2),
    }

    RESULTS_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
