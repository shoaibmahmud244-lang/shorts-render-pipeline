"""Stage 3: Vertical video filtergraph synthesis and trailing black-frame detection."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from shorts_engine.schemas import BeatSpec

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 30
BLACKDETECT_RE = re.compile(
    r"black_start:(?P<start>\d+(?:\.\d+)?)\s+black_end:(?P<end>\d+(?:\.\d+)?)"
)


def build_beat_filter(beat: BeatSpec, index: int) -> str:
    """Build deterministic 1080x1920 scale/pad + micro-action filter chain for one beat."""
    frames = round(beat.hold * FPS)
    base = (
        f"[{index}:v]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,"
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    if beat.action == "zoom_in":
        motion = (
            f"zoompan=z='min(zoom+0.0015,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
        )
    elif beat.action == "zoom_out":
        motion = (
            f"zoompan=z='max(1.15-0.0015*on,1.0)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
        )
    elif beat.action == "pan_up":
        motion = (
            f"zoompan=z='1.1':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{frames})':s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
        )
    elif beat.action == "pan_down":
        motion = (
            f"zoompan=z='1.1':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{frames})':s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
        )
    else:
        motion = (
            f"loop=loop=-1:size=1:start=0,fps={FPS},"
            f"trim=duration={beat.hold},setpts=PTS-STARTPTS"
        )

    return f"{base},{motion}[v{index}]"


def build_filtergraph(beats: list[BeatSpec]) -> str:
    """Assemble full FFmpeg filtergraph across all beats."""
    if not beats:
        raise ValueError("Cannot build filtergraph for empty beat list.")
    chains = [build_beat_filter(b, idx) for idx, b in enumerate(beats)]
    concat_inputs = "".join(f"[v{idx}]" for idx in range(len(beats)))
    concat_chain = f"{concat_inputs}concat=n={len(beats)}:v=1:a=0,format=yuv420p[vout]"
    return ";".join([*chains, concat_chain])


def parse_trailing_black_cut(
    stderr_log: str, total_duration: float, tolerance: float = 0.15
) -> float | None:
    """Return clean cut timestamp if a black segment extends to the end of the video."""
    matches = list(BLACKDETECT_RE.finditer(stderr_log))
    if not matches:
        return None
    last = matches[-1]
    black_start = float(last.group("start"))
    black_end = float(last.group("end"))
    if abs(total_duration - black_end) <= tolerance and black_start > 0.0:
        return round(black_start, 3)
    return None


def detect_non_black_end(
    video_path: Path, total_duration: float, luminance_threshold: int = 18
) -> float | None:
    """Probe rendered video with FFmpeg blackdetect and return trim point if needed."""
    pix_th = f"{luminance_threshold / 255.0:.3f}"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-vf",
        f"blackdetect=d=0.08:pix_th={pix_th}",
        "-an",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, check=False)
    return parse_trailing_black_cut(proc.stderr, total_duration)


def render_vertical_video(
    beats: list[BeatSpec],
    assets_dir: Path,
    master_audio_path: Path,
    output_mp4: Path,
) -> Path:
    """Render 1080x1920 H.264/AAC vertical video master."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = build_filtergraph(beats)

    cmd: list[str] = ["ffmpeg", "-v", "error", "-y"]
    for beat in beats:
        asset_path = assets_dir / beat.asset
        if not asset_path.exists():
            raise FileNotFoundError(
                f"Missing visual asset for beat '{beat.id}': {asset_path}"
            )
        cmd.extend(["-i", str(asset_path)])

    audio_idx = len(beats)
    cmd.extend(["-i", str(master_audio_path)])
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            f"{audio_idx}:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_mp4),
        ]
    )
    subprocess.run(cmd, check=True)
    return output_mp4
