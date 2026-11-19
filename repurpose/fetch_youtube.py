"""Fetch a YouTube video's transcript — or its audio as a fallback.

Order of attempts (all free, no paid API):
  1. youtube-transcript-api — captions supplied by YouTube, no download.
  2. yt-dlp audio download + local faster-whisper transcription.

If (1) fails the error is kept and reported; the caller must tell the user
exactly why and offer the transcript-file path. Never silently return an
empty transcript.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .transcribe import Segment, Transcript, TranscriptionUnavailable

YOUTUBE_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|live/|embed/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> str | None:
    match = YOUTUBE_RE.search(url or "")
    return match.group(1) if match else None


def is_youtube_url(value: str) -> bool:
    return extract_video_id(value) is not None


def _segments_from_api_entries(entries) -> list[Segment]:
    """Normalise caption entries from EITHER youtube-transcript-api version.

    - 0.6.x returns a list of dicts: {"text": ..., "start": ..., "duration": ...}
    - 1.x returns a FetchedTranscript whose .snippets are objects with
      .text / .start / .duration attributes.
    Treating 1.x objects as dicts was a real bug in the first version: it
    raised AttributeError, which the fallback then masked as "no captions".
    """
    items = getattr(entries, "snippets", entries)  # 1.x FetchedTranscript
    segments: list[Segment] = []
    for entry in items:
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).replace("\n", " ").strip()
            start = float(entry.get("start", 0.0))
            duration = float(entry.get("duration", 0.0) or 0.0)
        else:
            text = str(getattr(entry, "text", "")).replace("\n", " ").strip()
            start = float(getattr(entry, "start", 0.0))
            duration = float(getattr(entry, "duration", 0.0) or 0.0)
        if not text:
            continue
        segments.append(Segment(start=start, end=start + max(duration, 1.0), text=text))
    return segments


def fetch_youtube_transcript(url: str, languages: tuple[str, ...] = ("en",)) -> Transcript:
    """Fetch captions for a YouTube URL.

    Raises RuntimeError with a clear reason when no captions are available
    (disabled captions, private video, no transcript in the requested
    language, network blocked). The message always names the fallback:
    download the audio yourself or paste a transcript file.
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(
            f"Not a YouTube URL I can parse: {url}\n"
            "Expected a watch/shorts/youtu.be link, e.g. "
            "https://www.youtube.com/watch?v=VIDEO_ID"
        )
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "youtube-transcript-api is not installed.\n"
            "Install it with: pip install -r requirements.txt\n"
            "Or use a transcript file instead: "
            "python -m repurpose --transcript your_transcript.txt --no-key"
        ) from exc

    entries = None
    last_error: Exception | None = None
    # 1.x API (tested, pinned in requirements.txt): instance methods
    # .list() / .fetch(). 0.6.x had static methods instead. Try 1.x first;
    # fall back to 0.6.x ONLY when the 1.x methods do not exist at all
    # (AttributeError on the API itself) — never when the video itself
    # fails, or the real reason (e.g. captions disabled) gets masked by
    # the legacy call's own error, as happened in the first version.
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript = None
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue
        if transcript is None:
            transcript = transcript_list.find_generated_transcript(list(languages))
        entries = transcript.fetch()
    except AttributeError as exc:
        # Old 0.6.x install: no instance API. Use the static API.
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        except Exception as exc2:  # noqa: BLE001
            last_error = exc2
    except Exception as exc:  # noqa: BLE001 — video-level failure, report it
        last_error = exc

    if entries is None:
        detail = f" ({last_error})" if last_error else ""
        raise RuntimeError(
            "Could not fetch a transcript for this YouTube video" + detail + ".\n"
            "Common reasons: captions are disabled for this video, the video is "
            "private/age-restricted, or no English captions exist.\n"
            "What to do instead:\n"
            "  1. Try --transcribe-audio (downloads the audio and transcribes locally), or\n"
            "  2. Use a transcript file: python -m repurpose --transcript transcript.txt --no-key"
        )
    segments = _segments_from_api_entries(entries)
    if not segments:
        raise RuntimeError(
            "YouTube returned a transcript, but it contained no text. "
            "Try --transcribe-audio, or use a transcript file instead."
        )
    text = " ".join(s.text for s in segments)
    return Transcript(text=text, segments=segments, source=url)


def fetch_youtube_title(url: str) -> str:
    """Best-effort video title via yt-dlp; returns '' on any failure."""
    import shutil
    import sys

    command = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]
    try:
        result = subprocess.run(
            command + ["--no-warnings", "--get-title", url],
            capture_output=True, text=True, timeout=60, check=False,
        )
        title = (result.stdout or "").strip().splitlines()
        return title[0].strip() if title else ""
    except Exception:
        return ""


def download_youtube_audio(url: str, out_dir: str | Path) -> Path:
    """Download best audio with yt-dlp into out_dir. Raises RuntimeError on failure."""
    import shutil
    import sys

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "%(id)s.%(ext)s"
    # Run yt-dlp as a module of THIS Python first: the `yt-dlp` binary is
    # only on PATH if the venv's bin dir is, and a bare `yt-dlp` call failed
    # with FileNotFoundError in testing even though the package was installed.
    if shutil.which("yt-dlp"):
        command = ["yt-dlp"]
    else:
        command = [sys.executable, "-m", "yt_dlp"]
    try:
        result = subprocess.run(
            command + ["--no-warnings", "-x", "--audio-format", "mp3",
                       "-o", str(target), url],
            capture_output=True, text=True, timeout=900, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "yt-dlp is not installed in this Python environment.\n"
            "Install it with: pip install -r requirements.txt\n"
            "Or use a transcript file instead: "
            "python -m repurpose --transcript transcript.txt --no-key"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp could not download this video's audio.\n"
            f"yt-dlp said: {(result.stderr or result.stdout or '').strip()[-500:]}\n"
            "Check the URL is public and yt-dlp is up to date (pip install -U yt-dlp), "
            "or use a transcript file instead."
        )
    files = sorted(out_dir.glob("*.mp3"))
    if not files:
        raise RuntimeError("yt-dlp finished but no audio file was created.")
    return files[-1]


def fetch_youtube_via_audio(url: str, model: str = "tiny") -> Transcript:
    """Fallback: download audio, transcribe locally with faster-whisper."""
    from .transcribe import transcribe_audio

    with tempfile.TemporaryDirectory(prefix="repurpose-yt-") as tmp:
        audio = download_youtube_audio(url, tmp)
        result = transcribe_audio(audio, model=model)
        result.source = url
        return result
