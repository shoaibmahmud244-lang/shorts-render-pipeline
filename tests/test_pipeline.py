from __future__ import annotations

from pathlib import Path

import pytest

from shorts_engine.audio_engine import build_loudnorm_cmd, parse_whisper_json
from shorts_engine.composer import build_filtergraph, parse_trailing_black_cut
from shorts_engine.ingest import IngestError, parse_script
from shorts_engine.preflight import validate_stream_metrics, validate_video_seo
from shorts_engine.schemas import StreamMetrics

VALID_SCRIPT = """
[beat id=b1 hold=2.8 action=zoom_in asset=p1.png]
First comic beat holds for two point eight seconds.

[beat id=b2 hold=3.2 action=static asset=p2.png]
Second comic beat holds for three point two seconds.
"""


def test_parse_script_enforces_2_5_to_3_5_comic_hold() -> None:
    beats = parse_script(VALID_SCRIPT)
    assert len(beats) == 2
    assert beats[0].hold == 2.8
    assert beats[1].action == "static"

    too_fast = "[beat id=b1 hold=1.5 action=static asset=p1.png]\nToo fast."
    with pytest.raises(IngestError, match="violates comic pacing bounds"):
        parse_script(too_fast)


def test_build_loudnorm_cmd_targets_minus_18_5_lufs() -> None:
    cmd = build_loudnorm_cmd(Path("in.wav"), Path("out.wav"))
    assert "loudnorm=I=-18.5:TP=-1.5:LRA=11.0" in cmd


def test_parse_whisper_json_extracts_word_cues() -> None:
    sample = {
        "transcription": [
            {"offsets": {"from": 100, "to": 450}, "text": " deterministic "},
            {"offsets": {"from": 450, "to": 900}, "text": "pipeline"},
        ]
    }
    cues = parse_whisper_json(sample)
    assert len(cues) == 2
    assert cues[0].word == "deterministic"
    assert cues[0].start_sec == 0.1
    assert cues[1].end_sec == 0.9


def test_build_filtergraph_enforces_1080x1920_vertical_canvas() -> None:
    beats = parse_script(VALID_SCRIPT)
    fg = build_filtergraph(beats)
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in fg
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2" in fg
    assert "concat=n=2:v=1:a=0,format=yuv420p[vout]" in fg


def test_parse_trailing_black_cut_ignores_mid_scene_fade() -> None:
    # Mid-video black transition (5.0s -> 5.2s) in a 15.0s video must NOT truncate video
    mid_log = "[blackdetect @ 0x1] black_start:5.000 black_end:5.200 black_duration:0.200"
    assert parse_trailing_black_cut(mid_log, total_duration=15.0) is None

    # Trailing black frame (14.75s -> 15.00s) MUST return 14.75s cut point
    tail_log = (
        "[blackdetect @ 0x1] black_start:14.750 black_end:15.000 black_duration:0.250"
    )
    assert parse_trailing_black_cut(tail_log, total_duration=15.0) == 14.75


def test_preflight_seo_and_stream_gates() -> None:
    bad_metrics = StreamMetrics(
        width=1920, height=1080, duration_sec=61.2, codec_name="h264", has_audio=True
    )
    stream_errs = validate_stream_metrics(bad_metrics)
    assert any("1920x1080" in e for e in stream_errs)
    assert any("61.20s" in e for e in stream_errs)

    bad_seo = {
        "youtube": {
            "primary_keyword": "ffmpeg",
            "title": (
                "A Very Long Title Where The Keyword Appears Way Past Character Forty ffmpeg"
            ),
            "description": "Short description without keyword.",
            "hashtags": ["#fyp", "#shorts", "#viral"],
            "tags": ["only-one-tag"],
            "links": ["https://example.com/watch?utm_source=test"],
        }
    }
    seo_errs = validate_video_seo(bad_seo)
    assert any("first 40 chars" in e for e in seo_errs)
    assert any("exceeds 60 chars" in e for e in seo_errs)
    assert any("Banned trope '#fyp'" in e for e in seo_errs)
    assert any("utm_source" in e for e in seo_errs)
