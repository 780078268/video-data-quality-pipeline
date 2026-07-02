# Video Data Quality Pipeline

面向视频生成模型训练数据的轻量级质量筛选工具。它把“肉眼感觉视频质量好不好”拆成可计算指标，适合用于训练数据验收、供应商质量对比、低质样本过滤和数据补强分析。

## What It Checks

- 基础信息：时长、分辨率、帧率
- 画质指标：亮度、对比度、黑屏比例、过曝比例、清晰度代理指标
- 时序指标：帧间运动幅度、重复帧比例
- 决策结果：`accept` / `review` / `reject`
- 结构化输出：CSV、JSONL、HTML report

## Quick Start

```bash
python3 make_demo_videos.py
python3 video_quality_pipeline.py benchmark_videos --out outputs
open outputs/quality_report.html
```

The benchmark generator creates 16 synthetic video cases, including clean motion,
low resolution, too-short clips, dark/bright/low-contrast videos, blurry videos,
static frames, and noisy motion. This keeps the project reproducible without
depending on copyrighted external videos.

## Output

- `outputs/quality_report.csv`: 便于做供应商对比和统计分析
- `outputs/quality_report.jsonl`: 便于接入后续数据平台
- `outputs/quality_report.html`: 可直接展示的质量评估报告
- `benchmark_videos/manifest.csv`: 记录每个 benchmark 视频的设计场景

## Resume Angle

这个项目对应视频大模型数据岗位里的三件事：

- 定义训练数据质量标准
- 搭建可扩展的数据生产/验收链路
- 用指标定位数据问题，而不是只靠主观判断

可以在简历中写成：

> 基于 Python、FFmpeg 构建视频训练数据质量筛选 Pipeline，实现视频元信息解析、关键帧抽样、亮度/黑屏/过曝/清晰度/重复帧/运动幅度等指标计算，并输出 CSV、JSONL 与 HTML 质量报告，辅助训练数据验收、低质样本过滤与数据补强分析。

Current benchmark scale: 16 reproducible video cases.
