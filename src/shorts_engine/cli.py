"""CLI orchestrator with offline 15-second synthetic demo generation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from shorts_engine.audio_engine import align_words, master_audio
from shorts_engine.composer import detect_non_black_end, render_vertical_video
from shorts_engine.ingest import write_scene_plan
from shorts_engine.preflight import (
    probe_video,
    validate_stream_metrics,
    validate_video_seo,
)

DEMO_SCRIPT = """# 15-Second Deterministic Pipeline Demo
[beat id=b1 hold=3.0 action=zoom_in asset=panel_1.png]
Every automated media pipeline needs deterministic build contracts.

[beat id=b2 hold=3.0 action=static asset=panel_2.png]
First we parse Markdown beat tags and enforce comic hold pacing.

[beat id=b3 hold=3.0 action=zoom_out asset=panel_3.png]
Next we normalize narration to minus eighteen point five LUFS.

[beat id=b4 hold=3.0 action=zoom_in asset=panel_4.png]
Finally we verify stream dimensions, black frames, and SEO gates.
"""

DEMO_METADATA = {
    "youtube": {
        "primary_keyword": "media pipeline",
        "title": "Deterministic Media Pipeline Architecture in Python",
        "description": (
            "How a deterministic media pipeline validates beat pacing, EBU R128 "
            "loudness, whisper.cpp word cues, and FFmpeg filtergraphs."
        ),
        "hashtags": ["#shorts", "#python", "#ffmpeg"],
        "tags": [
            "media pipeline",
            "python automation",
            "ffmpeg",
            "ebu r128",
            "whisper cpp",
        ],
        "links": ["https://github.com/shoaibmahmud244-lang/shorts-render-pipeline"],
    }
}

DEMO_WHISPER_FIXTURE = {
    "transcription": [
        {"offsets": {"from": 0, "to": 650}, "text": "Every"},
        {"offsets": {"from": 650, "to": 1400}, "text": "automated"},
        {"offsets": {"from": 1400, "to": 2100}, "text": "media"},
        {"offsets": {"from": 2100, "to": 3000}, "text": "pipeline"},
    ]
}


def generate_demo_project(project_dir: Path) -> None:
    """Generate synthetic 1080x1920 panels and 12s WAV audio via FFmpeg lavfi."""
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "script.md").write_text(DEMO_SCRIPT, encoding="utf-8")
    (project_dir / "metadata.json").write_text(
        json.dumps(DEMO_METADATA, indent=2), encoding="utf-8"
    )
    (project_dir / "cues.fixture.json").write_text(
        json.dumps(DEMO_WHISPER_FIXTURE, indent=2), encoding="utf-8"
    )

    colors = ["#1e3a8a", "#1e293b", "#0369a1", "#0f766e"]
    for idx, color in enumerate(colors, start=1):
        panel = assets_dir / f"panel_{idx}.png"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1080x1920:d=1",
                "-frames:v",
                "1",
                str(panel),
            ],
            check=True,
        )

    raw_wav = project_dir / "narration.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=12.0",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(raw_wav),
        ],
        check=True,
    )


def run_pipeline(project_dir: Path, out_dir: Path, use_fixture: bool = False) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    beats = write_scene_plan(project_dir / "script.md", out_dir / "scene-plan.json")
    master_wav = master_audio(project_dir / "narration.wav", out_dir / "master.wav")

    fixture = (project_dir / "cues.fixture.json") if use_fixture else None
    cues = align_words(master_wav, out_dir / "cues.json", fixture_path=fixture)

    output_mp4 = render_vertical_video(
        beats, project_dir / "assets", master_wav, out_dir / "render.mp4"
    )

    metrics = probe_video(output_mp4)
    trailing_cut = detect_non_black_end(output_mp4, metrics.duration_sec)
    stream_errors = validate_stream_metrics(metrics)
    metadata = json.loads((project_dir / "metadata.json").read_text(encoding="utf-8"))
    seo_errors = validate_video_seo(metadata)

    all_errors = [*stream_errors, *seo_errors]
    report = {
        "ok": len(all_errors) == 0,
        "beats_count": len(beats),
        "word_cues_count": len(cues),
        "resolution": f"{metrics.width}x{metrics.height}",
        "duration_sec": round(metrics.duration_sec, 2),
        "trailing_black_cut_sec": trailing_cut,
        "errors": all_errors,
    }
    report_path = out_dir / "preflight-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic vertical video render pipeline."
    )
    parser.add_argument("--project-dir", type=Path, help="Input project directory")
    parser.add_argument("--out-dir", type=Path, default=Path("build/output"))
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate synthetic 12s demo project and run full pipeline",
    )
    args = parser.parse_args()

    if args.demo:
        demo_proj = args.out_dir / "demo_project"
        generate_demo_project(demo_proj)
        return run_pipeline(demo_proj, args.out_dir, use_fixture=True)

    if not args.project_dir:
        parser.error("--project-dir is required unless --demo is passed")
    return run_pipeline(args.project_dir, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
