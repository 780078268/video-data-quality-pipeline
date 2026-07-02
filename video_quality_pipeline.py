#!/usr/bin/env python3
"""Video training-data quality scanner.

The scanner intentionally uses only Python's standard library plus ffmpeg, so it
is easy to run on a laptop or server without a heavy ML environment.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


@dataclass
class VideoQuality:
    path: str
    duration_sec: float
    width: int
    height: int
    fps: float
    sampled_frames: int
    brightness: float
    contrast: float
    sharpness: float
    black_ratio: float
    overexposed_ratio: float
    motion_score: float
    duplicate_rate: float
    quality_score: float
    decision: str
    issues: str


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def parse_rate(rate: str) -> float:
    if not rate or rate == "0/0":
        return 0.0
    if "/" in rate:
        num, den = rate.split("/", 1)
        return float(num) / float(den) if float(den) else 0.0
    return float(rate)


def probe(path: Path) -> dict:
    data = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    stream = data["streams"][0]
    fmt = data.get("format", {})
    return {
        "duration": float(fmt.get("duration") or 0),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/0"),
    }


def read_token(stream: BinaryIO) -> bytes | None:
    token = bytearray()
    while True:
        ch = stream.read(1)
        if not ch:
            return bytes(token) if token else None
        if ch == b"#":
            stream.readline()
            continue
        if ch.isspace():
            if token:
                return bytes(token)
            continue
        token.extend(ch)


def iter_ppm_frames(path: Path, sample_fps: float, max_frames: int, scale_width: int):
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps={sample_fps},scale={scale_width}:-2",
        "-frames:v",
        str(max_frames),
        "-f",
        "image2pipe",
        "-vcodec",
        "ppm",
        "-",
    ]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
        assert proc.stdout is not None
        while True:
            magic = read_token(proc.stdout)
            if magic is None:
                break
            if magic != b"P6":
                raise RuntimeError(f"Unexpected PPM magic in {path}: {magic!r}")
            width = int(read_token(proc.stdout) or b"0")
            height = int(read_token(proc.stdout) or b"0")
            maxval = int(read_token(proc.stdout) or b"0")
            if maxval != 255:
                raise RuntimeError(f"Unsupported PPM max value: {maxval}")
            payload = proc.stdout.read(width * height * 3)
            if len(payload) != width * height * 3:
                break
            yield width, height, payload
        proc.wait()


def frame_luma(rgb: bytes) -> list[int]:
    luma: list[int] = []
    for i in range(0, len(rgb), 3):
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        luma.append((77 * r + 150 * g + 29 * b) >> 8)
    return luma


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def std(values: list[int], avg: float) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


def sharpness_proxy(luma: list[int], width: int, height: int) -> float:
    if width < 2 or height < 2:
        return 0.0
    diffs: list[int] = []
    for y in range(height - 1):
        row = y * width
        next_row = (y + 1) * width
        for x in range(width - 1):
            idx = row + x
            diffs.append(abs(luma[idx] - luma[idx + 1]))
            diffs.append(abs(luma[idx] - luma[next_row + x]))
    return mean(diffs)


def mean_abs_diff(a: list[int], b: list[int]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def score_video(metrics: dict, probe_info: dict) -> tuple[float, list[str], str]:
    score = 100.0
    issues: list[str] = []

    def penalize(condition: bool, points: float, issue: str) -> None:
        nonlocal score
        if condition:
            score -= points
            issues.append(issue)

    penalize(probe_info["duration"] < 2.0, 12, "too_short")
    penalize(probe_info["width"] < 480 or probe_info["height"] < 270, 10, "low_resolution")
    penalize(metrics["brightness"] < 35, 18, "too_dark")
    penalize(metrics["brightness"] > 220, 18, "too_bright")
    penalize(metrics["contrast"] < 18, 12, "low_contrast")
    penalize(metrics["sharpness"] < 3.5, 14, "blurry_or_flat")
    penalize(metrics["black_ratio"] > 0.35, 18, "black_frame_risk")
    penalize(metrics["overexposed_ratio"] > 0.30, 15, "overexposed")
    penalize(metrics["motion_score"] < 3.0, 10, "low_motion")
    penalize(metrics["duplicate_rate"] > 0.45, 10, "duplicate_frames")
    penalize(metrics["sampled_frames"] < 3, 8, "insufficient_samples")

    score = max(0.0, min(100.0, score))
    decision = "accept" if not issues else "review"
    if score < 60:
        decision = "reject"
    elif score < 78:
        decision = "review"
    return round(score, 2), issues, decision


def analyze_video(path: Path, sample_fps: float, max_frames: int, scale_width: int) -> VideoQuality:
    info = probe(path)
    brightness_values: list[float] = []
    contrast_values: list[float] = []
    sharpness_values: list[float] = []
    black_values: list[float] = []
    over_values: list[float] = []
    motion_values: list[float] = []
    duplicate_count = 0
    previous_luma: list[int] | None = None
    sampled = 0

    for width, height, rgb in iter_ppm_frames(path, sample_fps, max_frames, scale_width):
        luma = frame_luma(rgb)
        avg = mean(luma)
        brightness_values.append(avg)
        contrast_values.append(std(luma, avg))
        sharpness_values.append(sharpness_proxy(luma, width, height))
        black_values.append(sum(1 for value in luma if value < 16) / len(luma))
        over_values.append(sum(1 for value in luma if value > 245) / len(luma))
        if previous_luma is not None:
            diff = mean_abs_diff(luma, previous_luma)
            motion_values.append(diff)
            if diff < 1.2:
                duplicate_count += 1
        previous_luma = luma
        sampled += 1

    transitions = max(sampled - 1, 1)
    metrics = {
        "sampled_frames": sampled,
        "brightness": mean(brightness_values),
        "contrast": mean(contrast_values),
        "sharpness": mean(sharpness_values),
        "black_ratio": mean(black_values),
        "overexposed_ratio": mean(over_values),
        "motion_score": mean(motion_values),
        "duplicate_rate": duplicate_count / transitions,
    }
    quality_score, issues, decision = score_video(metrics, info)
    return VideoQuality(
        path=str(path),
        duration_sec=round(info["duration"], 2),
        width=info["width"],
        height=info["height"],
        fps=round(info["fps"], 2),
        sampled_frames=sampled,
        brightness=round(metrics["brightness"], 2),
        contrast=round(metrics["contrast"], 2),
        sharpness=round(metrics["sharpness"], 2),
        black_ratio=round(metrics["black_ratio"], 4),
        overexposed_ratio=round(metrics["overexposed_ratio"], 4),
        motion_score=round(metrics["motion_score"], 2),
        duplicate_rate=round(metrics["duplicate_rate"], 4),
        quality_score=quality_score,
        decision=decision,
        issues=";".join(issues) if issues else "none",
    )


def find_videos(input_dir: Path) -> list[Path]:
    if input_dir.is_file() and input_dir.suffix.lower() in VIDEO_EXTS:
        return [input_dir]
    return sorted(path for path in input_dir.rglob("*") if path.suffix.lower() in VIDEO_EXTS)


def write_csv(rows: list[VideoQuality], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))


def write_jsonl(rows: list[VideoQuality], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def write_html(rows: list[VideoQuality], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    accepted = sum(1 for row in rows if row.decision == "accept")
    review = sum(1 for row in rows if row.decision == "review")
    rejected = sum(1 for row in rows if row.decision == "reject")
    avg_score = mean([row.quality_score for row in rows])

    table_rows = []
    for row in rows:
        issue_text = html.escape(row.issues)
        cls = row.decision
        table_rows.append(
            f"<tr class='{cls}'><td>{html.escape(Path(row.path).name)}</td>"
            f"<td>{row.quality_score}</td><td>{row.decision}</td>"
            f"<td>{row.duration_sec}s</td><td>{row.width}x{row.height}</td>"
            f"<td>{row.brightness}</td><td>{row.sharpness}</td>"
            f"<td>{row.motion_score}</td><td>{issue_text}</td></tr>"
        )

    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Video Data Quality Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2933; }}
    h1 {{ margin-bottom: 8px; }}
    .summary {{ display: flex; gap: 16px; margin: 24px 0; }}
    .card {{ border: 1px solid #d8dee9; border-radius: 6px; padding: 14px 18px; min-width: 130px; }}
    .metric {{ font-size: 26px; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e5e9f0; padding: 9px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fb; }}
    tr.accept td:nth-child(3) {{ color: #0b7a3b; font-weight: 700; }}
    tr.review td:nth-child(3) {{ color: #a15c00; font-weight: 700; }}
    tr.reject td:nth-child(3) {{ color: #b42318; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Video Data Quality Report</h1>
  <p>Automated screening report for video-generation training data candidates.</p>
  <section class="summary">
    <div class="card"><div class="metric">{total}</div><div>Total videos</div></div>
    <div class="card"><div class="metric">{avg_score:.1f}</div><div>Average score</div></div>
    <div class="card"><div class="metric">{accepted}</div><div>Accepted</div></div>
    <div class="card"><div class="metric">{review}</div><div>Needs review</div></div>
    <div class="card"><div class="metric">{rejected}</div><div>Rejected</div></div>
  </section>
  <table>
    <thead>
      <tr><th>Video</th><th>Score</th><th>Decision</th><th>Duration</th><th>Resolution</th><th>Brightness</th><th>Sharpness</th><th>Motion</th><th>Issues</th></tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan videos for training-data quality issues.")
    parser.add_argument("input", type=Path, help="Input video file or directory")
    parser.add_argument("--out", type=Path, default=Path("outputs"), help="Output directory")
    parser.add_argument("--sample-fps", type=float, default=1.0, help="Frames per second sampled for metrics")
    parser.add_argument("--max-frames", type=int, default=40, help="Maximum sampled frames per video")
    parser.add_argument("--scale-width", type=int, default=160, help="Frame width used for lightweight metrics")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg and ffprobe are required. Install ffmpeg first.", file=sys.stderr)
        return 2

    videos = find_videos(args.input)
    if not videos:
        print(f"No videos found in {args.input}", file=sys.stderr)
        return 1

    rows: list[VideoQuality] = []
    for video in videos:
        print(f"Scanning {video}")
        try:
            rows.append(analyze_video(video, args.sample_fps, args.max_frames, args.scale_width))
        except Exception as exc:  # keep batch runs useful even with a corrupt file
            print(f"Failed to scan {video}: {exc}", file=sys.stderr)

    write_csv(rows, args.out / "quality_report.csv")
    write_jsonl(rows, args.out / "quality_report.jsonl")
    write_html(rows, args.out / "quality_report.html")
    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
