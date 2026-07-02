#!/usr/bin/env python3
"""Create benchmark/demo videos for the quality pipeline."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


DEMOS = [
    ("good_motion_testsrc2.mp4", "testsrc2=size=640x360:rate=24:duration=5", "clean moving pattern"),
    ("good_motion_testsrc.mp4", "testsrc=size=640x360:rate=24:duration=5", "clean chart animation"),
    ("good_widescreen_motion.mp4", "testsrc2=size=854x480:rate=24:duration=5", "clean widescreen motion"),
    ("vertical_motion.mp4", "testsrc2=size=360x640:rate=24:duration=5", "vertical motion sample"),
    ("low_resolution_motion.mp4", "testsrc2=size=256x144:rate=24:duration=5", "low resolution motion"),
    ("short_motion.mp4", "testsrc2=size=640x360:rate=24:duration=1", "too short for training"),
    ("dark_motion.mp4", "testsrc2=size=640x360:rate=24:duration=5,eq=brightness=-0.35", "dark moving sample"),
    ("bright_motion.mp4", "testsrc2=size=640x360:rate=24:duration=5,eq=brightness=0.35", "bright moving sample"),
    ("low_contrast_motion.mp4", "testsrc2=size=640x360:rate=24:duration=5,eq=contrast=0.18", "low contrast motion"),
    ("blurry_motion.mp4", "testsrc2=size=640x360:rate=24:duration=5,boxblur=4:2", "blurred motion"),
    ("noisy_motion.mp4", "testsrc2=size=640x360:rate=24:duration=5,noise=alls=25:allf=t+u", "noisy moving sample"),
    ("black_static.mp4", "color=c=black:size=640x360:rate=24:duration=5", "black static frame"),
    ("white_static.mp4", "color=c=white:size=640x360:rate=24:duration=5", "white static frame"),
    ("gray_static.mp4", "color=c=gray:size=640x360:rate=24:duration=5", "gray static frame"),
    ("colorbars_static.mp4", "smptebars=size=640x360:rate=24:duration=5", "static color bars"),
    ("low_res_static.mp4", "color=c=gray:size=256x144:rate=24:duration=5", "low resolution static frame"),
]


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is required to create demo videos.", file=sys.stderr)
        return 2

    out_dir = Path("benchmark_videos")
    out_dir.mkdir(exist_ok=True)
    manifest_rows = ["file,scenario\n"]
    for name, source, scenario in DEMOS:
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
        manifest_rows.append(f"{name},{scenario}\n")
    (out_dir / "manifest.csv").write_text("".join(manifest_rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
