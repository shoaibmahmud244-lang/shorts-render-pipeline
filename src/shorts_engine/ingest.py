"""Stage 1: Markdown beat tag parser and timeline validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from shorts_engine.schemas import BeatSpec

MIN_HOLD_SEC = 2.5
MAX_HOLD_SEC = 3.5
VALID_ACTIONS = {"static", "zoom_in", "zoom_out", "pan_up", "pan_down"}

BEAT_TAG_RE = re.compile(
    r"^\[beat\s+id=(?P<id>[A-Za-z0-9_-]+)\s+"
    r"hold=(?P<hold>[0-9]+(?:\.[0-9]+)?)\s+"
    r"action=(?P<action>[A-Za-z0-9_-]+)\s+"
    r"asset=(?P<asset>[^\]]+)\]\s*$"
)


class IngestError(ValueError):
    """Raised when script violates pacing bounds or syntax."""


def parse_script(markdown_text: str) -> list[BeatSpec]:
    """Parse Markdown beat annotations and enforce pacing bounds."""
    beats: list[BeatSpec] = []
    current_meta: dict[str, str] | None = None
    narration_lines: list[str] = []
    seen_ids: set[str] = set()

    def _flush() -> None:
        if current_meta is None:
            return
        beat_id = current_meta["id"]
        if beat_id in seen_ids:
            raise IngestError(f"Duplicate beat id '{beat_id}'.")
        seen_ids.add(beat_id)

        hold = float(current_meta["hold"])
        if not (MIN_HOLD_SEC <= hold <= MAX_HOLD_SEC):
            raise IngestError(
                f"Beat '{beat_id}' hold ({hold}s) violates comic pacing bounds "
                f"({MIN_HOLD_SEC}s–{MAX_HOLD_SEC}s)."
            )
        action = current_meta["action"]
        if action not in VALID_ACTIONS:
            raise IngestError(
                f"Beat '{beat_id}' has unsupported action '{action}'. "
                f"Allowed: {sorted(VALID_ACTIONS)}"
            )
        text = " ".join(narration_lines).strip()
        if not text:
            raise IngestError(f"Beat '{beat_id}' has empty narration text.")

        beats.append(
            BeatSpec(
                id=beat_id,
                hold=hold,
                action=action,
                asset=current_meta["asset"].strip(),
                narration=text,
            )
        )

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = BEAT_TAG_RE.match(line)
        if match:
            _flush()
            current_meta = match.groupdict()
            narration_lines = []
        elif current_meta is not None:
            narration_lines.append(line)

    _flush()
    if not beats:
        raise IngestError("No valid [beat ...] tags found in script.")

    total_duration = sum(b.hold for b in beats)
    if total_duration > 59.0:
        raise IngestError(
            f"Planned timeline duration ({total_duration:.2f}s) exceeds "
            "YouTube Shorts 59.0s ceiling."
        )
    return beats


def write_scene_plan(script_path: Path, out_path: Path) -> list[BeatSpec]:
    beats = parse_script(script_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_beats": len(beats),
        "planned_duration_sec": round(sum(b.hold for b in beats), 2),
        "beats": [b.to_dict() for b in beats],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return beats
