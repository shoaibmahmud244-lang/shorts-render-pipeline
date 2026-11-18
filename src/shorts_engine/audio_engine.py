"""Stage 2: EBU R128 loudness mastering and whisper.cpp alignment adapter."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from shorts_engine.schemas import WordCue

TARGET_I_LUFS = -18.5
TARGET_TP_DB = -1.5
TARGET_LRA = 11.0


def build_loudnorm_cmd(
    input_wav: Path,
    output_wav: Path,
    target_lufs: float = TARGET_I_LUFS,
    true_peak: float = TARGET_TP_DB,
    lra: float = TARGET_LRA,
) -> list[str]:
    """Construct FFmpeg command for broadcast loudness mastering."""
    filter_str = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
    return [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(input_wav),
        "-af",
        filter_str,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]


def master_audio(input_wav: Path, output_wav: Path) -> Path:
    """Normalize input narration to broadcast standard."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_loudnorm_cmd(input_wav, output_wav)
    subprocess.run(cmd, check=True)
    return output_wav


def parse_whisper_json(data: dict[str, Any]) -> list[WordCue]:
    """Extract normalized word-level timestamp cues from whisper output."""
    cues: list[WordCue] = []
    for segment in data.get("transcription", []):
        offsets = segment.get("offsets", {})
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start_sec = round(float(offsets.get("from", 0)) / 1000.0, 3)
        end_sec = round(float(offsets.get("to", 0)) / 1000.0, 3)
        cues.append(WordCue(word=text, start_sec=start_sec, end_sec=end_sec))
    return cues


def align_words(
    audio_path: Path,
    out_cues_path: Path,
    fixture_path: Path | None = None,
) -> list[WordCue]:
    """Run local whisper.cpp alignment or load deterministic fixture."""
    out_cues_path.parent.mkdir(parents=True, exist_ok=True)

    if fixture_path is not None and fixture_path.exists():
        raw_data: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
        cues = parse_whisper_json(raw_data)
        out_cues_path.write_text(
            json.dumps([c.to_dict() for c in cues], indent=2), encoding="utf-8"
        )
        return cues

    cli_bin = Path(os.environ.get("WHISPER_CPP_BIN", "whisper-cli"))
    model_path = Path(
        os.environ.get("WHISPER_MODEL_PATH", "models/ggml-large-v3-turbo.bin")
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        pcm_16k = tmp / "input_16k.wav"
        raw_prefix = tmp / "whisper_out"

        # Downmix to 16kHz mono PCM for whisper.cpp
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(audio_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(pcm_16k),
            ],
            check=True,
        )

        subprocess.run(
            [
                str(cli_bin),
                "-m",
                str(model_path),
                "-f",
                str(pcm_16k),
                "-l",
                "en",
                "-ml",
                "1",
                "-sow",
                "-oj",
                "-of",
                str(raw_prefix),
                "-np",
            ],
            check=True,
        )

        whisper_json_file = Path(f"{raw_prefix}.json")
        raw_data = json.loads(whisper_json_file.read_text(encoding="utf-8"))

    cues = parse_whisper_json(raw_data)
    out_cues_path.write_text(
        json.dumps([c.to_dict() for c in cues], indent=2), encoding="utf-8"
    )
    return cues
