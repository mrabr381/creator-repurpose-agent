"""Local transcription and transcript-file parsing.

Transcription uses faster-whisper (local, free, no API key, no upload).
If faster-whisper is not installed, or ffmpeg is missing for an audio/video
file, this module raises :class:`TranscriptionUnavailable` with a clear,
actionable message — it never silently returns an empty transcript.

Transcript files (.txt / .srt) are parsed without any model at all, so the
``--transcript`` path always works, even on a machine with no Whisper.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]")
SRT_BLOCK_RE = re.compile(
    r"(\d+)\s*\n(\d{2}):(\d{2}):(\d{2}),\d{3}\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2}),\d{3}\s*\n(.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


class TranscriptionUnavailable(Exception):
    """Raised when local transcription cannot run. Message tells the user why
    and what to do instead (install faster-whisper / ffmpeg, or use a
    transcript file)."""


@dataclass
class Segment:
    """One timed chunk of transcript text."""

    start: float  # seconds
    end: float  # seconds
    text: str

    def timestamp(self) -> str:
        return format_timestamp(self.start)


@dataclass
class Transcript:
    text: str
    segments: list[Segment] = field(default_factory=list)
    source: str = ""
    title: str = ""

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def has_timestamps(self) -> bool:
        return bool(self.segments)


def format_timestamp(seconds: float) -> str:
    """Seconds -> MM:SS or HH:MM:SS (always valid, zero-padded)."""
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp(value: str) -> float:
    """Parse MM:SS or HH:MM:SS into seconds. Raises ValueError on bad input."""
    parts = [int(p) for p in value.strip().split(":")]
    if len(parts) == 2:
        minutes, secs = parts
        return minutes * 60 + secs
    if len(parts) == 3:
        hours, minutes, secs = parts
        return hours * 3600 + minutes * 60 + secs
    raise ValueError(f"Bad timestamp: {value!r}")


def parse_bracketed_transcript(text: str) -> Transcript:
    """Parse a transcript containing [MM:SS] markers.

    Returns segments split at each marker. Text before the first marker
    (if any) becomes a segment starting at 0:00. Markers are the source of
    truth for chapters — chapter timestamps always come from here, never
    from an estimate, when markers exist.
    """
    matches = list(TIMESTAMP_RE.finditer(text))
    if not matches:
        return Transcript(text=text.strip(), segments=[])
    segments: list[Segment] = []
    for i, match in enumerate(matches):
        start = parse_timestamp(match.group(0).strip("[]"))
        chunk_start = match.end()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[chunk_start:chunk_end].strip()
        # Drop a trailing marker-less line that is just whitespace.
        if not chunk:
            continue
        end = (
            parse_timestamp(matches[i + 1].group(0).strip("[]"))
            if i + 1 < len(matches)
            else start + max(30.0, len(chunk.split()) / 2.5)
        )
        segments.append(Segment(start=start, end=max(end, start + 1), text=chunk))
    # Leading text before the first marker.
    leading = text[: matches[0].start()].strip()
    if leading:
        segments.insert(
            0, Segment(start=0.0, end=matches[0].start() and parse_timestamp(matches[0].group(0).strip("[]")) or 30.0, text=leading)
        )
    clean = re.sub(r"\s+", " ", TIMESTAMP_RE.sub(" ", text)).strip()
    return Transcript(text=clean, segments=segments)


def parse_srt(text: str) -> Transcript:
    """Parse SubRip (.srt) content into text + timed segments."""
    segments: list[Segment] = []
    for match in SRT_BLOCK_RE.finditer(text):
        start = int(match.group(2)) * 3600 + int(match.group(3)) * 60 + int(match.group(4))
        end = int(match.group(5)) * 3600 + int(match.group(6)) * 60 + int(match.group(7))
        chunk = re.sub(r"<[^>]+>", "", match.group(8)).replace("\n", " ").strip()
        if chunk:
            segments.append(Segment(start=float(start), end=float(end), text=chunk))
    if not segments:
        raise ValueError("No subtitle cues found — is this a valid .srt file?")
    full = " ".join(s.text for s in segments)
    return Transcript(text=full, segments=segments)


def load_transcript_file(path: str | Path) -> Transcript:
    """Load a .txt or .srt transcript file. No model needed."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ValueError(f"Transcript file is empty: {path}")
    if path.suffix.lower() == ".srt":
        result = parse_srt(text)
    else:
        result = parse_bracketed_transcript(text)
    result.source = str(path)
    return result


def check_ffmpeg() -> str | None:
    """Return None if ffmpeg is on PATH, else an install hint."""
    if shutil.which("ffmpeg"):
        return None
    return (
        "ffmpeg was not found on PATH. faster-whisper needs ffmpeg to decode "
        "mp3/m4a/mp4 audio. Install it (e.g. `sudo apt install ffmpeg` on "
        "Ubuntu/Debian, `brew install ffmpeg` on macOS), or use a .txt/.srt "
        "transcript instead — that path needs no ffmpeg at all."
    )


def transcribe_audio(path: str | Path, model: str = "tiny") -> Transcript:
    """Transcribe a local audio/video file with faster-whisper (local).

    Raises TranscriptionUnavailable with a plain-English reason if the
    model library or ffmpeg is missing — the caller must surface that
    message and point at the transcript-file fallback.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio/video file not found: {path}")
    ffmpeg_hint = check_ffmpeg()
    if ffmpeg_hint:
        raise TranscriptionUnavailable(ffmpeg_hint)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionUnavailable(
            "faster-whisper is not installed, so local transcription cannot run.\n"
            "Install it with: pip install -r requirements.txt\n"
            "Or skip transcription entirely: pass a transcript instead, e.g.\n"
            f"  python -m repurpose --transcript sample_data/sample_transcript.txt --no-key\n"
            "That path needs no model and no audio file."
        ) from exc
    try:
        whisper = WhisperModel(model, device="cpu", compute_type="int8")
        segments_iter, _info = whisper.transcribe(str(path), beam_size=5)
        segments: list[Segment] = []
        parts: list[str] = []
        for seg in segments_iter:
            text = seg.text.strip()
            if text:
                segments.append(Segment(start=float(seg.start), end=float(seg.end), text=text))
                parts.append(text)
    except Exception as exc:  # model download failure, corrupt file, etc.
        raise TranscriptionUnavailable(
            f"faster-whisper failed on {path}: {exc}\n"
            "Check the file plays normally, try --model tiny (smallest), and "
            "if it still fails, use a .txt/.srt transcript instead."
        ) from exc
    if not parts:
        raise TranscriptionUnavailable(
            f"No speech was detected in {path}. The file may be silent, music-only, "
            "or too quiet. Use a transcript file instead if you have one."
        )
    result = Transcript(text=" ".join(parts), segments=segments, source=str(path))
    return result
