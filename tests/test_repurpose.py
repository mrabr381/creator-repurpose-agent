"""Tests for the repurpose guarantees that matter:

- every X post is <= 280 characters (checked by code, verified here)
- pull quotes are verbatim sentences from the transcript
- chapters use real timestamps when the transcript has them, and say
  APPROXIMATE when it does not

The offline fixture is the old synthetic transcript
(sample_data/sample_transcript_synthetic_fixture.txt); the live demo
sample is the real Eisenhower inaugural address.
"""

from pathlib import Path

from repurpose.generate import generate_local
from repurpose.outputs import ALL_OUTPUTS, slugify
from repurpose.transcribe import load_transcript_file

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
FIXTURE = SAMPLE_DIR / "sample_transcript_synthetic_fixture.txt"
REAL_SAMPLE = SAMPLE_DIR / "sample_transcript.txt"


def _generate(transcript_path):
    transcript = load_transcript_file(transcript_path)
    result = generate_local(transcript, title="Test episode", selected=set(ALL_OUTPUTS))
    return transcript, result


def test_x_thread_posts_all_within_280_chars():
    _, result = _generate(FIXTURE)
    posts = [p for p in result.outputs["x_thread"].strip().split("\n\n") if p.strip()]
    assert len(posts) >= 5, f"expected a real thread, got {len(posts)} posts"
    for post in posts:
        assert len(post) <= 280, f"post over 280 chars ({len(post)}): {post!r}"
        assert "/" in post.split()[-1], f"post missing n/N suffix: {post!r}"


def test_x_thread_real_sample_within_280_chars():
    _, result = _generate(REAL_SAMPLE)
    posts = [p for p in result.outputs["x_thread"].strip().split("\n\n") if p.strip()]
    assert len(posts) >= 5
    assert all(len(p) <= 280 for p in posts)


def test_pull_quotes_are_verbatim_from_transcript():
    transcript, result = _generate(FIXTURE)
    quotes = [line[2:].strip() for line in
              result.outputs["pull_quotes"].splitlines() if line.startswith("> ")]
    assert len(quotes) >= 3
    for quote in quotes:
        assert quote in transcript.text, f"quote not verbatim from transcript: {quote!r}"


def test_pull_quotes_real_sample_are_verbatim():
    transcript, result = _generate(REAL_SAMPLE)
    quotes = [line[2:].strip() for line in
              result.outputs["pull_quotes"].splitlines() if line.startswith("> ")]
    assert len(quotes) >= 3
    for quote in quotes:
        assert quote in transcript.text, f"quote not verbatim: {quote!r}"


def test_chapters_use_real_timestamps_when_present():
    _, result = _generate(FIXTURE)
    chapters = result.outputs["chapters"]
    assert "APPROXIMATE" not in chapters
    assert "[00:00]" in chapters
    assert "[02:48]" in chapters
    assert "[13:15]" in chapters


def test_chapters_labelled_approximate_without_timestamps():
    _, result = _generate(REAL_SAMPLE)
    chapters = result.outputs["chapters"]
    assert "APPROXIMATE" in chapters


def test_show_notes_key_points_come_from_transcript():
    transcript, result = _generate(FIXTURE)
    bullets = [line[2:].strip() for line in
               result.outputs["show_notes"].splitlines() if line.startswith("- ")]
    assert len(bullets) >= 3
    for point in bullets:
        assert point in transcript.text, f"key point not from transcript: {point!r}"


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("Eisenhower First Inaugural Address 1953") == "eisenhower-first-inaugural-address-1953"
    assert slugify("") == "episode"
