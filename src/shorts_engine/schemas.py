"""Data models and contracts for video pipeline stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BeatSpec:
    id: str
    hold: float
    action: str
    asset: str
    narration: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WordCue:
    word: str
    start_sec: float
    end_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StreamMetrics:
    width: int
    height: int
    duration_sec: float
    codec_name: str
    has_audio: bool
