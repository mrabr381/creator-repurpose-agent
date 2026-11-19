"""Command-line interface.

Examples:
  python -m repurpose --transcript sample_data/sample_transcript.txt --no-key
  python -m repurpose --source https://www.youtube.com/watch?v=VIDEO_ID
  python -m repurpose --source episode.mp3 --model base
  python -m repurpose --source transcript.txt --out output/my-episode --outputs blog_post x_thread

Exit codes: 0 = pack written. 1 = input problem (missing file, no transcript,
empty transcript). 2 = argument problem (argparse). Generation never fails
just because Gemini is unavailable — it falls back to local and says so.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv not installed: .env is optional, env vars still work
    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        return False

from .fetch_youtube import (
    fetch_youtube_transcript,
    fetch_youtube_title,
    fetch_youtube_via_audio,
    is_youtube_url,
)
from .generate import generate
from .outputs import ALL_OUTPUTS, slugify, write_pack
from .transcribe import (
    Transcript,
    TranscriptionUnavailable,
    load_transcript_file,
    transcribe_audio,
)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm", ".mov", ".mkv"}
TRANSCRIPT_EXTS = {".txt", ".srt"}


def _load_source(source: str, model: str, transcribe_audio_flag: bool,
                 title_hint: str = "") -> tuple[Transcript, str]:
    """Resolve --source / --transcript / --url / --file into a Transcript.

    Raises SystemExit-style ValueError/RuntimeError with a message that names
    the fallback. Callers print it and exit 1.
    """
    source = (source or "").strip()
    if not source:
        raise ValueError(
            "No input given. Use one of:\n"
            "  --transcript sample_data/sample_transcript.txt --no-key\n"
            "  --source https://www.youtube.com/watch?v=VIDEO_ID\n"
            "  --source episode.mp3\n"
            "  --source \"paste your transcript text here\""
        )
    if is_youtube_url(source):
        title = fetch_youtube_title(source) or title_hint or "YouTube episode"
        if transcribe_audio_flag:
            transcript = fetch_youtube_via_audio(source, model=model)
        else:
            transcript = fetch_youtube_transcript(source)
        transcript.title = title
        return transcript, title
    path = Path(source)
    if path.exists():
        suffix = path.suffix.lower()
        if suffix in TRANSCRIPT_EXTS:
            transcript = load_transcript_file(path)
            return transcript, title_hint or path.stem.replace("-", " ").replace("_", " ").title()
        if suffix in AUDIO_EXTS:
            transcript = transcribe_audio(path, model=model)
            return transcript, title_hint or path.stem.replace("-", " ").replace("_", " ").title()
        raise ValueError(
            f"Unsupported file type: {path.suffix}\n"
            "Supported: transcript .txt/.srt, audio/video .mp3/.wav/.m4a/.mp4/.ogg/.flac/.webm/.mov/.mkv"
        )
    # Not a file and not a URL: treat the argument itself as pasted transcript text.
    if len(source.split()) < 20:
        raise ValueError(
            f"Could not find a file named {source!r}, and it is not a YouTube URL "
            "or a transcript (too short to be one).\n"
            "Check the path, or paste the full transcript text as --source \"...\", "
            "or use --transcript <file>."
        )
    from .transcribe import parse_bracketed_transcript

    transcript = parse_bracketed_transcript(source)
    return transcript, title_hint or "Pasted transcript"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repurpose",
        description="Turn one long recording into show notes, a blog post, LinkedIn/X posts, "
                    "a newsletter, chapters and pull quotes. Free — local fallback needs no API key.",
    )
    parser.add_argument("--source", help="YouTube URL, audio/video file, transcript file, or pasted transcript text")
    parser.add_argument("--transcript", help="Path to a .txt or .srt transcript file")
    parser.add_argument("--url", help="YouTube URL (same as --source with a URL)")
    parser.add_argument("--file", help="Local audio/video/transcript file (same as --source with a path)")
    parser.add_argument("--title", default="", help="Episode title (defaults to the video title or file name)")
    parser.add_argument("--out", default="output", help="Output directory (default: output)")
    parser.add_argument("--model", default="tiny",
                        help="Whisper model for local transcription: tiny, base, small, medium (default: tiny)")
    parser.add_argument("--transcribe-audio", action="store_true",
                        help="For YouTube URLs: download audio and transcribe locally instead of fetching captions")
    parser.add_argument("--no-key", action="store_true",
                        help="Force the local fallback (no Gemini call, even if GEMINI_API_KEY is set)")
    parser.add_argument("--api-key", default="", help="Gemini API key (or set GEMINI_API_KEY in .env)")
    parser.add_argument("--gemini-model", default="gemini-2.5-flash", help="Gemini model name")
    parser.add_argument("--outputs", nargs="+", choices=sorted(ALL_OUTPUTS), default=None,
                        help="Only generate these outputs (default: all 7)")
    parser.add_argument("--slug", default="", help="Output folder name (default: slugified title)")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    source = args.transcript or args.url or args.file or args.source
    if not source:
        parser.print_help()
        print("\nTry the demo first:\n  python -m repurpose --transcript sample_data/sample_transcript.txt --no-key",
              file=sys.stderr)
        return 2

    # --- Load input -----------------------------------------------------
    try:
        transcript, title = _load_source(source, model=args.model,
                                         transcribe_audio_flag=args.transcribe_audio,
                                         title_hint=args.title)
    except (ValueError, FileNotFoundError, RuntimeError, TranscriptionUnavailable) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not transcript.text.strip():
        print("ERROR: The transcript is empty — nothing to repurpose.", file=sys.stderr)
        return 1
    if args.title:
        title = args.title

    # --- Generate -------------------------------------------------------
    selected = set(args.outputs) if args.outputs else set(ALL_OUTPUTS)
    api_key = "" if args.no_key else (args.api_key or os.environ.get("GEMINI_API_KEY", "").strip())
    if api_key:
        print("Using Google Gemini (bring-your-own free-tier key) for rewritten outputs.")
        print("Chapters and pull-quotes still come from the transcript verbatim.")
    else:
        print("No Gemini API key found — using the LOCAL fallback.")
        print("All outputs are extracted from the transcript itself; nothing is invented.")
        print("To get AI-rewritten versions, set GEMINI_API_KEY in .env (free tier) and re-run without --no-key.")
    try:
        result = generate(transcript, title=title, selected=selected,
                          api_key=api_key or None, model=args.gemini_model)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Engine: {result.engine}")
    print(f"Note: {result.note}")

    # --- Write ----------------------------------------------------------
    slug = args.slug or slugify(title)
    out_dir = Path(args.out) / slug
    try:
        written = write_pack(result, out_dir, title)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone — {transcript.word_count} words in, {len(written)} files out, in {out_dir}/:")
    for path in written:
        print(f"  - {path.name} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
