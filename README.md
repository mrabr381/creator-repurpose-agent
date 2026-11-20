![Creator Repurpose Agent — Turn one long recording into a week's worth of posts.](assets/hero.svg)

# Creator Repurpose Agent 🎙️

[![CI](https://github.com/mrabr381/creator-repurpose-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/mrabr381/creator-repurpose-agent/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![No API key required](https://img.shields.io/badge/API%20key-not%20required-brightgreen.svg)](#quickstart)

**Turn one long recording into a week's worth of posts.**

Free and open source. One recording in — show notes, a blog post, LinkedIn + X posts, a newsletter, chapters and pull quotes out. No paid API is required: the local fallback works with **zero key**, and the optional AI rewrite uses your own free-tier Gemini key.

## Try it now

**Live sample pack:** [see a real pack, generated from a real speech](https://mrabr381.github.io/creator-repurpose-agent/sample_data/sample_output/) — Dwight D. Eisenhower's First Inaugural Address (20 January 1953, public domain). No server needed.

**Web app — 1-click deploy (repo owner):** [share.streamlit.io](https://share.streamlit.io) → Create app → repo `mrabr381/creator-repurpose-agent`, branch `main`, file `app.py` → Deploy. Optional `GEMINI_API_KEY` under Secrets — the app works without it, using the local fallback.

## Quickstart

```bash
git clone https://github.com/mrabr381/creator-repurpose-agent.git
cd creator-repurpose-agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# ffmpeg is needed only for audio/video transcription:
#   Ubuntu/Debian: sudo apt install ffmpeg | macOS: brew install ffmpeg

# Demo — no key, no audio, no network needed:
python -m repurpose --transcript sample_data/sample_transcript.txt --no-key
# → output/<slug>/ with all 8 files
```

## What it produces

| File | What it is |
|---|---|
| `show_notes.md` | Overview + key points + key topics |
| `blog_post.md` | A full blog post drawn from the episode |
| `linkedin_post.txt` | Hook + 3 concrete takeaways + a question |
| `x_thread.txt` | Numbered thread, every post ≤ 280 characters (checked by code) |
| `newsletter.md` | Big idea + 3 keepers + verbatim quote + one practical step |
| `chapters.md` | Chapters with timestamps from the transcript |
| `pull_quotes.md` | Exact sentences copied from the transcript |
| `repurpose_pack.md` | All of the above in one file |

**Before:** one 14-minute episode, used once — then the transcript sits in a folder, unused. **After:** the same episode, one command, 8 files (see the [live sample pack](https://mrabr381.github.io/creator-repurpose-agent/sample_data/sample_output/)). From the sample speech:

> We are called as a people to give testimony in the sight of the world to our faith that the future shall belong to the free.

## Usage

```bash
# A YouTube video (fetches captions; no download)
python -m repurpose --source https://www.youtube.com/watch?v=VIDEO_ID
# Same video, but transcribe the audio locally instead of using captions
python -m repurpose --source https://www.youtube.com/watch?v=VIDEO_ID --transcribe-audio
# A local audio / video file (local Whisper transcription)
python -m repurpose --source episode.mp3 --model base
# A transcript file you already have
python -m repurpose --transcript transcript.txt --no-key
python -m repurpose --transcript captions.srt
# Only some outputs, into a named folder
python -m repurpose --transcript transcript.txt --outputs blog_post x_thread --out output --slug my-episode
# With AI rewriting (optional — needs your own free-tier key)
cp .env.example .env   # then put your key in .env
python -m repurpose --transcript transcript.txt
```

Get a free Gemini key at <https://aistudio.google.com/apikey>. The key is **bring-your-own**: it lives only in your local `.env`, is never committed (`.env` is gitignored), and is never sent anywhere except Google's API.

**When things go wrong:** no Gemini key → local fallback, never a crash. YouTube has no captions → the exact reason is printed, plus the two fixes (`--transcribe-audio`, or a transcript file). Missing file / bad URL / empty transcript → exit code 1 with a plain-English message. No silent empty outputs: every written file is checked non-empty.

## Web app

```bash
streamlit run app.py
```

Upload a file, paste a YouTube URL, or paste a transcript. Tick the outputs you want, hit **Generate pack**, and download each file (or the whole pack). Pasting a key in the sidebar is optional and is not stored.

## Comparison with Castmagic

| | Creator Repurpose Agent (this repo) | Castmagic |
|---|---|---|
| Price | Free, open source (MIT) | No free plan. Hobby $23.75/mo, 160 min/mo cap. |
| Transcript → multi-format pack | Yes | Yes |
| Local transcription (no upload) | Yes — faster-whisper, on your machine | No |
| Works with no API key at all | Yes — local fallback | No |
| Pull quotes / chapters guaranteed verbatim | Yes, by construction | Not verifiable from outside |

> Castmagic facts above are the ones verified in market research in November 2026 (no free plan, Hobby $23.75/mo, 160 min/mo cap). Prices change — check Castmagic's pricing page before quoting them elsewhere.

## Quality promise — no invented content

- **Pull quotes are exact sentences from your transcript.** The code picks them; it never writes a quote and attributes it to you.
- **Chapter timestamps come from real timestamps** — `[MM:SS]` markers, `.srt` cues, or YouTube caption timings. If your transcript has no timing, chapters are labelled **approximate** (estimated from word count) and the file says so.
- **The blog post, show notes and newsletter only use points that appear in the transcript.** The local generator is extractive: it ranks your own sentences and reuses them.
- **The Gemini path is held to the same rule:** every prompt instructs the model to quote verbatim and not to invent facts, numbers, or quotes. Chapters and quotes bypass the AI entirely, even when a key is set.

## Sample source

The demo transcript is Dwight D. Eisenhower's First Inaugural Address, 20 January 1953 — a real public-domain speech. It is a work of the United States federal government (public domain under 17 U.S.C. § 105), printed as a U.S. Senate document by the Government Printing Office. Full source note: [`sample_data/SAMPLE_SOURCE.md`](sample_data/SAMPLE_SOURCE.md). The old synthetic transcript is kept as the offline test fixture (`sample_data/sample_transcript_synthetic_fixture.txt`).

## Honest limitations

- **Whisper accuracy is not perfect.** Accents, crosstalk, music and low-quality audio produce errors, and those errors flow into every output. The `base` model is noticeably more accurate than `tiny`; `small` is better still but slower. Always skim the transcript for names and numbers before publishing.
- **Gemini's free tier changes.** Model names, rate limits and quotas have rotated before and will again. If a Gemini call fails, the tool falls back to local generation and tells you why. A successful Gemini call was not testable in the build sandbox (Google's API endpoint is blocked there by a proxy TLS error), so the live AI rewrite is verified by code path, not by a live call — try it with your own free key.
- **YouTube transcripts are not guaranteed.** Some videos have captions disabled, are private/age-restricted, or have no English captions. When that happens the CLI prints the exact reason and tells you to use `--transcribe-audio` or a transcript file instead.
- **The local fallback does not "write" like a human.** It extracts and reorders your own sentences. That is deliberate — it cannot invent — but the AI path (with a key) reads more naturally. Use the local pack as a draft and the Gemini pack as the polish.
- **X posts are length-checked, not style-checked.** The code guarantees ≤ 280 characters per post; it cannot guarantee a post will perform well.

## Editing the prompts

Every output type has an editable template in `prompts/` (`blog.md`, `linkedin.md`, `x_thread.md`, `newsletter.md`, `show_notes.md`, `chapters.md`, `quotes.md`). Edit the wording there — no Python needed. Chapters and quotes are always built locally from the transcript, so their prompt files only control selection style, never the words or timestamps themselves.

## How it works

```
YouTube URL ──▶ youtube-transcript-api (captions)
                  └─ fallback: yt-dlp audio + faster-whisper
Local audio/video ──▶ faster-whisper (local, tiny/base/small)
Transcript .txt/.srt ──▶ parsed directly (timestamps kept)
        │
        ▼
  generate.py ──▶ Gemini (if GEMINI_API_KEY set)
              └─▶ local extractive fallback (if no key, or Gemini fails)
        │
        ▼
  outputs.py ──▶ output/<slug>/*.md + *.txt + repurpose_pack.md
```

Tests: `python -m pytest tests/ -q` — thread length, verbatim quotes, real vs. approximate chapters. CI runs them on every push (see `.github/workflows/ci.yml`).

## Project structure

```
creator-repurpose-agent/
├── app.py                  # Streamlit web app (deploy-ready, repo root)
├── repurpose/              # cli.py, transcribe.py, fetch_youtube.py, generate.py, outputs.py
├── prompts/                # editable templates, one per output type
├── sample_data/
│   ├── sample_transcript.txt            # Eisenhower inaugural address, 1953 (public domain)
│   ├── sample_transcript_synthetic_fixture.txt  # old synthetic transcript, offline test fixture
│   ├── SAMPLE_SOURCE.md                 # source + public-domain note
│   └── sample_output/      # expected output from the demo run + index.html demo page
├── tests/                  # pytest — thread length, verbatim quotes/chapters
├── .github/workflows/ci.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
└── LICENSE (MIT)
```

## License

MIT — see [LICENSE](LICENSE).
