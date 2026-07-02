#!/usr/bin/env python3
"""Create tiny demo videos for the quality pipeline."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


DEMOS = [
    (
        "good_motion.mp4",
        "testsrc2=size=640x360:rate=24:duration=5",
    ),
    (
        "dark_static.mp4",
        "color=c=black:size=640x360:rate=24:duration=5",
    ),
    (
        "bright_static.mp4",
        "color=c=white:size=640x360:rate=24:duration=5",
    ),
    (
        "low_resolution_motion.mp4",
        "testsrc2=size=256x144:rate=24:duration=5",
    ),
]


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is required to create demo videos.", file=sys.stderr)
        return 2

    out_dir = Path("demo_videos")
    out_dir.mkdir(exist_ok=True)
    for name, source in DEMOS:
        target = out_dir / name
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            source,
            "-pix_fmt",
            "yuv420p",
            str(target),
        ]
        subprocess.run(cmd, check=True)
        print(f"created {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
