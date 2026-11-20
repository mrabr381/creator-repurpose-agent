"""Content generation: Gemini (BYO free-tier key) or a local fallback.

Quality contract (this is the whole point of the tool):
- Every pull-quote is an EXACT sentence copied from the transcript.
  The fallback never invents a quote, a fact, or a number.
- Every chapter timestamp comes from a real timestamp in the transcript
  (``[MM:SS]`` markers, .srt cues, or YouTube caption timings). When the
  transcript has no timing at all, chapters are labelled honestly as
  approximate, estimated from word count at ~150 wpm — and the file says so.
- The blog post, show notes and newsletter only use points that actually
  appear in the transcript. The fallback is extractive: it ranks the
  transcript's own sentences and reuses them, with light connective wording
  clearly marked as framing, not as claims from the speaker.
- The Gemini path uses the same rule: prompts instruct the model to quote
  verbatim and not to invent facts, numbers, or quotes.

If no GEMINI_API_KEY is set (or the google-generativeai package / API call
fails), generation falls back to the local path and says so in the output
and on stdout — the user always knows which engine produced the pack.
"""

from __future__ import annotations

import math
import os
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .transcribe import Segment, Transcript, format_timestamp

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

STOPWORDS = set(
    "a an the and or but if then else when while of to in on for with at by from as is are "
    "was were be been being have has had do does did will would shall should can could may "
    "might must i you he she it we they this that these those there here what which who whom "
    "how why not no yes so very just really actually basically literally like get got gets "
    "getting make makes made take takes took taking know knows knew think thinks thought "
    "feel feels felt want wants wanted need needs needed say says said see sees saw go goes "
    "going gone come comes came thing things lot lots way ways part parts one two three "
    "first second third every each all also still even back around over under into out up "
    "down off about between through after before during without within upon per via etc "
    "really kinda sorta um uh yeah okay right most more less much many few "
    "own same other another any some no nor".split()
)

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

# Minimum words for a sentence to be usable as a quote / takeaway.
MIN_QUOTE_WORDS = 8
MAX_QUOTE_WORDS = 38


@dataclass
class GenerationResult:
    engine: str  # "gemini" or "local-fallback"
    note: str
    outputs: dict[str, str]


def load_prompt(name: str) -> str:
    """Load an editable prompt template from prompts/<name>.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _sentences(text: str) -> list[str]:
    """Split transcript text into clean, de-duplicated sentences."""
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    parts = SENTENCE_RE.split(clean)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        sentence = part.strip()
        if len(sentence.split()) < 4:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
    return out


def _score_sentences(sentences: list[str]) -> list[tuple[float, str]]:
    """Rank sentences by content-word frequency (extractive summarisation)."""
    words: Counter[str] = Counter()
    for sentence in sentences:
        for word in re.findall(r"[a-z][a-z\-']+", sentence.lower()):
            if word not in STOPWORDS:
                words[word] += 1
    # Meta/framing openers ("Here is the system…", "Welcome back…") are not
    # substance: in the first run one ranked #1 and became the hook, the blog
    # opener and X post 1 all at once. Demote them hard.
    META_STARTS = (
        "here is", "welcome", "today i", "today we", "in this episode",
        "in this video", "let me", "if you take one thing",
        "that is the entire", "that is the whole",
    )
    scored: list[tuple[float, str]] = []
    for i, sentence in enumerate(sentences):
        tokens = [w for w in re.findall(r"[a-z][a-z\-']+", sentence.lower()) if w not in STOPWORDS]
        if not tokens:
            continue
        # Average word frequency, lightly favouring mid-document sentences
        # (openers and closers are usually framing, not substance).
        score = sum(words[t] for t in tokens) / len(tokens)
        position_bonus = 0.1 if 0.1 < (i / max(len(sentences), 1)) < 0.9 else 0.0
        score += position_bonus
        if re.search(r"\d", sentence):
            score += 0.5  # concrete numbers are usually the memorable points
        if sentence.lower().startswith(META_STARTS):
            score *= 0.25
        scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _top_sentences(text: str, count: int) -> list[str]:
    """Top `count` sentences by score, returned in original transcript order."""
    sentences = _sentences(text)
    if not sentences:
        return []
    scored = _score_sentences(sentences)
    chosen = {sentence for _score, sentence in scored[:count]}
    return [s for s in sentences if s in chosen]


def _key_phrases(text: str, count: int = 6) -> list[str]:
    """Top two-word topics (bigrams) — far more meaningful than single words.

    Single-word topics came out as junk ("every, gets, takes") in testing;
    bigrams like "short clips" or "text posts" actually name what the
    episode is about. Only bigrams of two content words are counted.
    """
    # Bigrams are counted WITHIN sentences only: counting across the whole
    # text produced junk like "change published" from "...the change, I
    # published..." spanning a sentence boundary.
    bigrams: Counter[str] = Counter()
    for sentence in _sentences(text):
        # NOTE: the regex must match 1-letter words ("I", "a") too — dropping
        # them made non-adjacent words look adjacent and produced the junk
        # bigram "change published" from "...the change, I published...".
        words = [w for w in re.findall(r"[a-z][a-z']*", sentence.lower())]
        # Drop possessives ("world's" -> "world"): title-casing a possessive
        # produced junk topics like "Free World'S" in the sample output.
        words = [w[:-2] if w.endswith("'s") else w for w in words]
        for first, second in zip(words, words[1:]):
            if first in STOPWORDS or second in STOPWORDS:
                continue
            if len(first) < 4 or len(second) < 4:
                continue
            bigrams[f"{first} {second}"] += 1
    ranked = [phrase for phrase, _ in bigrams.most_common(count)]
    if ranked:
        return ranked
    # Fallback: single content words, if the transcript is too short for bigrams.
    all_words = [w for w in re.findall(r"[a-z][a-z\-']+", text.lower())]
    singles = Counter(w for w in all_words if w not in STOPWORDS and len(w) > 4)
    return [word for word, _ in singles.most_common(count)]


def _short_heading(sentence: str, max_words: int = 5) -> str:
    """A short section heading from a sentence's opening words.

    Never truncates mid-word and never repeats the whole sentence: the
    heading is the first clause (up to a comma) or the first `max_words`
    words, title-cased, with trailing prepositions/articles stripped so it
    never ends on a dangling "In" / "By" / "Of" (a real bug in the first run:
    "Subscribers Grew By 3100 In").
    """
    clean = re.sub(r"[^\w\s'\-]", "", sentence).strip()
    first_clause = clean.split(",")[0].strip()
    words = first_clause.split()
    if len(words) > max_words:
        words = clean.split()[:max_words]
    while words and words[-1].lower() in {"in", "by", "of", "to", "for", "with", "the", "a", "an", "and", "on", "at"}:
        words.pop()
    heading = " ".join(words).strip()
    return heading.title() if heading else "Key Point"


def _following_sentences(sentences: list[str], anchor: str, count: int = 2) -> list[str]:
    """The sentences that follow `anchor` in the transcript (supporting detail)."""
    try:
        idx = sentences.index(anchor)
    except ValueError:
        return []
    return sentences[idx + 1: idx + 1 + count]


def _chapters_from_segments(segments: list[Segment], target: int = 6) -> list[tuple[str, str]]:
    """Group timed segments into ~`target` chapters.

    Each chapter title is the first substantive sentence (or its opening
    words) of that group, and its timestamp is the group's real start time.
    """
    if not segments:
        return []
    # Group consecutive segments into `target` roughly equal chunks.
    chunk_size = max(1, math.ceil(len(segments) / target))
    chapters: list[tuple[str, str]] = []
    for i in range(0, len(segments), chunk_size):
        group = segments[i:i + chunk_size]
        first_text = group[0].text.strip()
        first_sentence = SENTENCE_RE.split(first_text)[0].strip()
        words = first_sentence.split()
        title = " ".join(words[:9])
        if len(words) > 9:
            title += "…"
        # Capitalise first letter; keep the speaker's own words otherwise.
        title = title[:1].upper() + title[1:] if title else "Opening"
        chapters.append((format_timestamp(group[0].start), title))
    return chapters


def _chapters_estimated(text: str, target: int = 5) -> tuple[list[tuple[str, str]], str]:
    """Fallback chapters when the transcript has NO timing information.

    Duration is estimated from word count at ~150 wpm and the chapters are
    explicitly labelled approximate in the output — never presented as real.
    """
    sentences = _sentences(text)
    if not sentences:
        return [], "No chapters could be built: the transcript has no usable sentences."
    total_words = len(text.split())
    est_seconds = max(60.0, total_words / 150.0 * 60.0)
    chunk = max(1, math.ceil(len(sentences) / target))
    chapters: list[tuple[str, str]] = []
    for i in range(0, len(sentences), chunk):
        group = sentences[i:i + chunk]
        start = (i / len(sentences)) * est_seconds
        words = group[0].split()
        title = " ".join(words[:9])
        if len(words) > 9:
            title += "…"
        chapters.append((format_timestamp(start), title[:1].upper() + title[1:]))
    note = (
        "Note: these timestamps are APPROXIMATE — estimated from word count "
        "(~150 words per minute) because this transcript had no [MM:SS] markers, "
        ".srt timings, or YouTube caption timings. Use a timestamped transcript "
        "for exact chapters."
    )
    return chapters, note


def _best_quotes(text: str, count: int = 5) -> list[str]:
    """Pick exact transcript sentences that work as standalone quotes.

    A good quote is self-contained, 8–38 words, and contains a concrete
    claim or contrast (numbers, 'because', 'instead', 'most', 'only', etc.)
    rather than filler. Returned verbatim, punctuation included.
    """
    sentences = _sentences(text)
    candidates: list[tuple[float, str]] = []
    for sentence in sentences:
        word_count = len(sentence.split())
        if not (MIN_QUOTE_WORDS <= word_count <= MAX_QUOTE_WORDS):
            continue
        if sentence.lower().startswith(("so ", "and ", "but ", "well ", "you know")):
            continue
        score = 0.0
        lowered = sentence.lower()
        for marker in ("because", "instead", "most", "only", "never", "always",
                       "first", "secret", "mistake", "percent", "%", "free",
                       "every day", "every week"):
            if marker in lowered:
                score += 1.0
        if re.search(r"\d", sentence):
            score += 1.5
        score += min(word_count, 25) / 25.0
        candidates.append((score, sentence))
    candidates.sort(key=lambda item: item[0], reverse=True)
    # Keep them in transcript order so the file reads like the episode.
    chosen = {s for _score, s in candidates[:count]}
    ordered = [s for s in sentences if s in chosen]
    # Fallback: if scoring found too few, take the longest substantive sentences.
    if len(ordered) < 3:
        long_sentences = sorted(sentences, key=len, reverse=True)
        for sentence in long_sentences:
            if MIN_QUOTE_WORDS <= len(sentence.split()) <= MAX_QUOTE_WORDS and sentence not in ordered:
                ordered.append(sentence)
            if len(ordered) >= 3:
                break
    return ordered[:count]


def _clean_title(title: str, transcript: Transcript) -> str:
    if title:
        return title.strip()
    # Derive a title from the first substantive sentence, not from thin air.
    sentences = _sentences(transcript.text)
    if sentences:
        words = sentences[0].split()
        derived = " ".join(words[:10])
        return derived[:1].upper() + derived[1:]
    return "Untitled episode"


def _split_x_posts(sentences: list[str], hook: str, max_chars: int = 280) -> list[str]:
    """Build a numbered X thread where EVERY post is <= 280 chars including its 'n/N' suffix.

    Posts are built sentence by sentence; a sentence that alone would exceed
    the limit is hard-split on word boundaries. Numbering is applied last,
    after the final post count is known, and every post is re-checked.
    """
    # One idea per post: each sentence is its own post (a thread of merged
    # multi-sentence posts tested badly — 3 long posts instead of a thread).
    # Only a single sentence longer than 240 chars is split on word boundaries.
    body: list[str] = []
    for sentence in sentences:
        current = sentence
        while len(current) > 240:
            cut = current[:240].rsplit(" ", 1)[0]
            body.append(cut)
            current = current[len(cut):].strip()
        if current:
            body.append(current)
    posts = [hook] + body
    # Final pass: enforce the limit with the real suffix.
    total = len(posts)
    final: list[str] = []
    for i, post in enumerate(posts, start=1):
        suffix = f" {i}/{total}"
        allowed = max_chars - len(suffix)
        text = post if len(post) <= allowed else post[:allowed].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
        final.append(f"{text}{suffix}")
    # Defensive re-check: no post may exceed 280 chars, ever.
    assert all(len(p) <= max_chars for p in final), "X post exceeded 280 chars"
    return final


def generate_local(transcript: Transcript, title: str, selected: set[str]) -> GenerationResult:
    """Zero-key fallback: extractive generation from the transcript only."""
    title = _clean_title(title, transcript)
    sentences = _sentences(transcript.text)
    if not sentences:
        raise ValueError("Cannot generate from an empty transcript.")
    key_points = _top_sentences(transcript.text, 6)
    quotes = _best_quotes(transcript.text, 5)
    phrases = _key_phrases(transcript.text)
    if transcript.segments:
        chapters, chapter_note = _chapters_from_segments(transcript.segments), ""
    else:
        chapters, chapter_note = _chapters_estimated(transcript.text)
    hook = key_points[0] if key_points else sentences[0]
    if len(hook) > 200:
        hook = hook[:200].rsplit(" ", 1)[0] + "…"
    word_count = transcript.word_count
    # Episode length: real timestamps win. The sample transcript spans 13:15
    # but has only 674 words — word-count alone would claim "4 minutes",
    # contradicting the chapter timestamps. Use the last segment end when
    # timing exists, and word-count only when it does not.
    if transcript.segments:
        est_minutes = max(1, round(max(s.end for s in transcript.segments) / 60))
    else:
        est_minutes = max(1, round(word_count / 150))
    closing_line = sentences[-1]
    source_line = f"Source: {transcript.source or 'transcript provided by the user'}"
    outputs: dict[str, str] = {}

    if "show_notes" in selected:
        lines = [
            f"# Show notes — {title}",
            "",
            f"**{word_count} words · about {est_minutes} minutes · {source_line}**",
            "",
            "## In this episode",
            "",
        ]
        for point in key_points:
            lines.append(f"- {point}")
        lines += ["", "## Key topics", "", ", ".join(p.title() for p in phrases) if phrases else "—", ""]
        if quotes:
            lines += ["## Standout line", "", f"> {quotes[0]}", ""]
        lines += [
            "---",
            "_Generated locally (no AI key used). Every point above is taken from the transcript._",
            "",
        ]
        outputs["show_notes"] = "\n".join(lines)

    if "blog_post" in selected:
        lines = [
            f"# {title}",
            "",
            f"_A {est_minutes}-minute read, drawn entirely from the episode transcript._",
            "",
            "## The idea in one paragraph",
            "",
            (key_points[0] if key_points else sentences[0]),
            "",
            "## What actually came up",
            "",
        ]
        for point in key_points[1:]:
            # Heading = short phrase from the point; body = the point PLUS
            # the sentences that actually follow it in the transcript, so a
            # section adds detail instead of repeating its own heading.
            lines.append(f"### {_short_heading(point)}")
            lines.append("")
            lines.append(point)
            for extra in _following_sentences(sentences, point, count=1):
                if extra not in key_points:
                    lines.append(extra)
            lines.append("")
        if quotes:
            lines += ["## Worth remembering", ""]
            for quote in quotes[:3]:
                lines.append(f"> {quote}")
                lines.append("")
        lines += [
            "## Bottom line",
            "",
            closing_line,
            "",
            "---",
            "_This post is a faithful retelling of the transcript — no new facts were added._",
            "",
        ]
        outputs["blog_post"] = "\n".join(lines)

    if "linkedin_post" in selected:
        # Takeaways start AFTER the hook — key_points[0] is the hook, and
        # repeating it as the first takeaway was a real bug in the first run.
        takeaways = key_points[1:4]
        lines = [
            hook,
            "",
            "Here's what stood out:",
            "",
        ]
        for point in takeaways:
            lines.append(f"→ {point}")
            lines.append("")
        lines += [
            "What's the one part you'd steal for your own workflow?",
            "",
            "#ContentCreation #CreatorEconomy #Podcast",
            "",
            f"({word_count} words in the full episode — link in comments.)",
        ]
        outputs["linkedin_post"] = "\n".join(lines)

    if "x_thread" in selected:
        # Thread body excludes the hook (it is post 1) and uses the top 8
        # ranked sentences so the thread has 5+ posts instead of 3.
        thread_sentences = [s for s in _top_sentences(transcript.text, 8) if s != hook]
        if len(thread_sentences) < 3:
            thread_sentences = [s for s in sentences if s != hook][:6]
        posts = _split_x_posts(thread_sentences, hook)
        outputs["x_thread"] = "\n\n".join(posts) + "\n"

    if "newsletter" in selected:
        lines = [
            f"# {title}",
            "",
            f"Hi — this week, one episode, distilled. ({est_minutes} min to read the source.)",
            "",
            "## The big idea",
            "",
            (key_points[0] if key_points else sentences[0]),
            "",
            "## 3 things worth keeping",
            "",
        ]
        for i, point in enumerate(key_points[1:4], start=1):
            lines.append(f"{i}. {point}")
        lines.append("")
        if quotes:
            lines += ["## Quote of the week", "", f"> {quotes[0]}", ""]
        lines += ["## Try this", "", closing_line, ""]
        outputs["newsletter"] = "\n".join(lines)

    if "chapters" in selected:
        lines = [f"# Chapters — {title}", ""]
        if chapter_note:
            lines += [chapter_note, ""]
        for timestamp, chapter_title in chapters:
            lines.append(f"- [{timestamp}] {chapter_title}")
        lines.append("")
        outputs["chapters"] = "\n".join(lines)

    if "pull_quotes" in selected:
        lines = [f"# Pull quotes — {title}", "",
                 "Every quote below is copied word-for-word from the transcript.", ""]
        for quote in quotes:
            lines.append(f"> {quote}")
            lines.append("")
        outputs["pull_quotes"] = "\n".join(lines)

    note = (
        "Generated with the LOCAL fallback (no Gemini API key was used). "
        "All points and quotes are extracted from the transcript itself — "
        "nothing was invented. For rewritten, AI-polished versions of the same "
        "outputs, set GEMINI_API_KEY (free tier, bring-your-own-key) and re-run."
    )
    return GenerationResult(engine="local-fallback", note=note, outputs=outputs)


def generate_with_gemini(transcript: Transcript, title: str, selected: set[str],
                         api_key: str, model: str = "gemini-2.5-flash") -> GenerationResult:
    """Gemini path. Prompts require verbatim quotes and no invented facts.

    Any failure (missing package, bad key, quota, network) raises RuntimeError
    with the real reason, so the caller can fall back to local generation
    and tell the user exactly what happened.
    """
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "google-generativeai is not installed. Run: pip install -r requirements.txt"
        ) from exc
    genai.configure(api_key=api_key)
    gemini = genai.GenerativeModel(model)
    title = _clean_title(title, transcript)
    outputs: dict[str, str] = {}
    # Gemini rewrites; the local extractive results are the safety net for
    # quotes/chapters, which must stay exact even in the AI path.
    local = generate_local(transcript, title, selected)
    prompt_map = {
        "show_notes": "show_notes", "blog_post": "blog", "linkedin_post": "linkedin",
        "x_thread": "x_thread", "newsletter": "newsletter",
    }
    for key, prompt_name in prompt_map.items():
        if key not in selected:
            continue
        template = load_prompt(prompt_name)
        prompt = (
            f"{template}\n\n---\nTITLE: {title}\n\nTRANSCRIPT:\n{transcript.text}\n\n"
            "RULES: Only use facts, numbers and quotes that appear in the "
            "transcript above. Quote verbatim — do not paraphrase inside "
            "quotation marks. Do not invent names, statistics, or claims."
        )
        try:
            # 60s timeout per call: without it, a blocked network / bad key
            # makes the client retry with backoff for minutes before the
            # caller can fall back to local generation (found in testing:
            # the first version hung past 90s on a sandbox proxy SSL error).
            response = gemini.generate_content(prompt, request_options={"timeout": 60})
            text = (response.text or "").strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed for {key}: {exc}") from exc
        if not text:
            raise RuntimeError(f"Gemini returned an empty response for {key}.")
        if key == "x_thread":
            # Re-enforce the 280-char rule on AI output: split/trim posts.
            raw_posts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            sentences = []
            for post in raw_posts:
                sentences.append(re.sub(r"^\d+/\d+\s*", "", post))
            hook = sentences[0] if sentences else title
            outputs[key] = "\n\n".join(_split_x_posts(sentences[1:], hook)) + "\n"
        else:
            outputs[key] = text + "\n"
    # Chapters and quotes always come from the local (exact) path.
    for key in ("chapters", "pull_quotes"):
        if key in selected and key in local.outputs:
            outputs[key] = local.outputs[key]
    note = (
        f"Generated with Google Gemini ({model}, bring-your-own free-tier key). "
        "Chapters and pull-quotes are taken verbatim from the transcript by the "
        "local extractor, so timestamps and quotes are exact even in the AI path."
    )
    return GenerationResult(engine="gemini", note=note, outputs=outputs)


def _try_gemini_boxed(transcript: Transcript, title: str, selected: set[str],
                      key: str, model: str, timeout: float = 120.0
                      ) -> tuple[GenerationResult | None, str | None]:
    """Run the Gemini attempt in a daemon thread, time-boxed to `timeout`.

    Why a thread: the per-call `request_options={"timeout": 60}` does NOT
    bound a transport-level failure — in testing, a sandbox proxy that
    breaks TLS made generate_content retry the handshake past 75s despite
    a 15s timeout. A daemon thread lets us abandon a stuck call after 120s
    wall-clock and fall back to local generation instead of hanging the CLI
    indefinitely. (The thread is a daemon, so it cannot block process exit.)
    Returns (result, error_message); exactly one is None on failure, and
    (None, "timed out") when the box expires.
    """
    import threading

    box: dict[str, object] = {}

    def work() -> None:
        try:
            box["result"] = generate_with_gemini(transcript, title, selected, key, model=model)
        except Exception as exc:  # noqa: BLE001 — reported back to the caller
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None, (
            f"timed out after {int(timeout)}s (the Gemini API endpoint did not "
            "answer — network blocked, or the API is unreachable from here)"
        )
    if "error" in box:
        return None, str(box["error"])
    return box["result"], None  # type: ignore[return-value]


def generate(transcript: Transcript, title: str = "", selected: set[str] | None = None,
             api_key: str | None = None, model: str = "gemini-2.5-flash") -> GenerationResult:
    """Main entry point. Tries Gemini when a key is available; otherwise local.

    Returns (result, used_fallback, fallback_reason) semantics via the
    GenerationResult.engine field — callers must surface it to the user.
    """
    selected = selected or {"show_notes", "blog_post", "linkedin_post", "x_thread",
                            "newsletter", "chapters", "pull_quotes"}
    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        result, error = _try_gemini_boxed(transcript, title, selected, key, model=model)
        if result is not None:
            return result
        # Never crash the run because the AI call failed or hung: fall back
        # and say so, with the real reason attached.
        local = generate_local(transcript, title, selected)
        local.note = (
            f"Gemini was tried but failed ({error}). Fell back to the LOCAL "
            "generator so you still get a complete pack. " + local.note
        )
        local.engine = "local-fallback-after-gemini-error"
        return local
    return generate_local(transcript, title, selected)
