"""Stage 4: Stream verification and release gate validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from shorts_engine.schemas import StreamMetrics

MAX_SHORTS_DURATION_SEC = 59.0
REQUIRED_WIDTH = 1080
REQUIRED_HEIGHT = 1920

BANNED_STRINGS = (
    "😭",
    "#fyp",
    "#foryou",
    "#foryoupage",
    "#viral",
    "#trending",
    "#mindset",
    "#motivation",
)
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm",
    "si",
    "is_from_webapp",
}


def validate_video_seo(video_entry: dict[str, Any]) -> list[str]:
    """Validate title, description, keyword placement, tags, and clean URLs."""
    errors: list[str] = []
    yt: dict[str, Any] = video_entry.get("youtube", video_entry.get("seo", {}))
    primary_kw = str(yt.get("primary_keyword", "")).strip()
    title = str(yt.get("title", "")).strip()
    description = str(yt.get("description", "")).strip()
    hashtags: list[str] = list(yt.get("hashtags", []))
    tags: list[str] = list(yt.get("tags", []))
    urls: list[str] = list(yt.get("links", []))

    if not primary_kw:
        errors.append("Missing primary_keyword.")
    else:
        kw_lower = primary_kw.lower()
        t_pos = title.lower().find(kw_lower)
        if t_pos == -1 or t_pos > 40:
            errors.append(
                f"Primary keyword '{primary_kw}' must appear within first 40 chars of title."
            )
        d_pos = description.lower().find(kw_lower)
        if d_pos == -1 or d_pos > 150:
            errors.append(
                f"Primary keyword '{primary_kw}' must appear within first 150 chars of description."
            )

    if len(title) > 60:
        errors.append(f"Title length ({len(title)}) exceeds 60 chars.")
    if not (3 <= len(hashtags) <= 5):
        errors.append(f"Hashtags count ({len(hashtags)}) outside 3-5 range.")
    if not (5 <= len(tags) <= 15):
        errors.append(f"Tags count ({len(tags)}) outside 5-15 range.")

    combined_lower = f"{title} {description} {' '.join(hashtags)}".lower()
    for banned in BANNED_STRINGS:
        if banned in combined_lower:
            errors.append(f"Banned trope '{banned}' detected.")

    for url in urls:
        parsed = urlparse(url)
        query_keys = set(parse_qs(parsed.query).keys())
        leaked = sorted(query_keys & TRACKING_PARAMS)
        if leaked:
            errors.append(f"URL '{url}' contains banned tracking params: {leaked}")

    return errors


def validate_stream_metrics(metrics: StreamMetrics) -> list[str]:
    """Verify rendered MP4 container meets 1080x1920 canvas and duration ceiling."""
    errors: list[str] = []
    if metrics.width != REQUIRED_WIDTH or metrics.height != REQUIRED_HEIGHT:
        errors.append(
            f"Invalid resolution {metrics.width}x{metrics.height}; "
            f"expected {REQUIRED_WIDTH}x{REQUIRED_HEIGHT}."
        )
    if metrics.duration_sec <= 0 or metrics.duration_sec > MAX_SHORTS_DURATION_SEC:
        errors.append(
            f"Duration ({metrics.duration_sec:.2f}s) exceeds YouTube Shorts "
            f"ceiling ({MAX_SHORTS_DURATION_SEC:.2f}s)."
        )
    if not metrics.has_audio:
        errors.append("Rendered container is missing an audio stream.")
    return errors


def probe_video(video_path: Path) -> StreamMetrics:
    """Inspect rendered MP4 container via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info: dict[str, Any] = json.loads(proc.stdout)

    video_stream: dict[str, Any] | None = None
    has_audio = False
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio":
            has_audio = True

    if video_stream is None:
        raise RuntimeError(f"No video stream found in {video_path}")

    duration = float(
        info.get("format", {}).get("duration")
        or video_stream.get("duration")
        or 0.0
    )
    return StreamMetrics(
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        duration_sec=duration,
        codec_name=str(video_stream.get("codec_name", "unknown")),
        has_audio=has_audio,
    )
