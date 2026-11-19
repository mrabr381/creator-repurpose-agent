# Creator Repurpose Agent 🎙️

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![No API key required](https://img.shields.io/badge/API%20key-not%20required-brightgreen.svg)](#quickstart)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B.svg)](#live-demo)
[![GitHub Pages demo](https://img.shields.io/badge/demo-live%20sample%20pack-22c55e.svg)](#live-demo)

**One long recording in — show notes, a blog post, LinkedIn + X posts, a newsletter, chapters and pull quotes out.**

Free and open source. No paid API is required: the local fallback works with **zero key**, and the optional AI rewrite uses your own free-tier Gemini key.

> **Live demo:** see a real pack generated from the sample transcript — [sample pack page](sample_data/sample_output/index.html) (works on GitHub Pages, no server needed) — or run the web app on Streamlit Community Cloud (one-click deploy, see [Live demo](#live-demo)).

## Table of contents

- [Before / after](#before--after)
- [What it produces](#what-it-produces)
- [Live demo](#live-demo)
- [Quickstart](#quickstart)
- [Usage](#usage)
- [Web app](#web-app)
- [Comparison with Castmagic](#comparison-with-castmagic)
- [Quality promise — no invented content](#quality-promise--no-invented-content)
- [Editing the prompts](#editing-the-prompts)
- [How it works](#how-it-works)
- [Honest limitations](#honest-limitations)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## Before / after

**Before — one 14-minute episode, used once:**

```
📹 1 YouTube video
🎧 1 podcast episode
😩 …and then the transcript sits in a folder, unused
```

**After — the same episode, run through one command:**

```bash
python -m repurpose --transcript sample_data/sample_transcript.txt --no-key
```

```
output/sample-episode/
├── show_notes.md       # overview + key points + topics
├── blog_post.md        # full blog post from the episode
├── linkedin_post.txt   # hook + 3 takeaways + question
├── x_thread.txt        # 8 posts, every one ≤ 280 chars
├── newsletter.md       # big idea + 3 keepers + verbatim quote
├── chapters.md         # [00:00] [02:48] [06:20] … real timestamps
├── pull_quotes.md      # exact sentences, word for word
└── repurpose_pack.md   # all of the above in one file
```

<details>
<summary><strong>👀 See the actual output (from the sample transcript — click to expand)</strong></summary>

**Chapters — timestamps taken straight from the transcript:**

```
- [00:00] Welcome back to the show.
- [02:48] Here is the system, step by step, because the…
- [06:20] The numbers made me believe in this, because I…
- [09:52] People ask me how long this takes, and I…
- [13:15] If you take one thing from today, take this:…
```

**Pull quotes — every one copied word-for-word:**

> That cycle burned me out, and my channel grew by only 400 subscribers in eighteen months.

> I do not pause to fix a mistake, because a mistake in a ninety-minute recording is one bad minute, not a ruined video.

**X thread — post 1 of 8:**

> In the six months before the change, I published twenty-four videos and gained 400 subscribers. 1/8

Full files: [`sample_data/sample_output/`](sample_data/sample_output/)

</details>

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

## Live demo

Two demos — one is already built, one is a 1-click deploy for the repo owner.

### ✅ Already built: sample pack page (GitHub Pages)

`sample_data/sample_output/index.html` is a static page that displays the full sample pack — input transcript excerpt plus all 7 outputs, with download links for each file. It has no JavaScript framework and no external requests, so it works as-is on GitHub Pages.

**To publish it (repo owner, 2 minutes):** GitHub repo → **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main`, folder `/ (root)` → Save.** The demo then opens at:

```
https://mrabr381.github.io/creator-repurpose-agent/sample_data/sample_output/
```

### 🖱️ 1-click deploy: Streamlit web app (Streamlit Community Cloud)

The web app is deploy-ready: `app.py` is at the repo root and `requirements.txt` is clean (no dev-only or local-path dependencies).

**To deploy it (repo owner, no code changes):**

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Pick repository `mrabr381/creator-repurpose-agent`, branch `main`, main file `app.py`.
4. Click **Deploy**. (Optional: add `GEMINI_API_KEY` under **Advanced settings → Secrets** — the app works without it, using the local fallback.)

That is the only step the owner has to do — nothing else is needed for the demo to go live.

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

<details>
<summary><strong>⚠️ What happens when things go wrong (error handling)</strong></summary>

- **No Gemini key** → the tool says so on stdout and runs the local fallback. It never crashes because the AI is unavailable.
- **YouTube has no captions** → the exact reason is printed, plus the two fixes: `--transcribe-audio`, or use a transcript file.
- **faster-whisper / ffmpeg missing** → a clear message tells you what to install, or to use a `.txt`/`.srt` transcript instead (that path needs neither).
- **Missing file / bad URL / empty transcript** → exit code 1 with a plain-English message. No silent empty outputs: every written file is checked non-empty.

</details>

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

This is the part that matters most:

- **Pull quotes are exact sentences from your transcript.** The code picks them; it never writes a quote and attributes it to you.
- **Chapter timestamps come from real timestamps** — `[MM:SS]` markers, `.srt` cues, or YouTube caption timings. If your transcript has no timing, chapters are labelled **approximate** (estimated from word count) and the file says so.
- **The blog post, show notes and newsletter only use points that appear in the transcript.** The local generator is extractive: it ranks your own sentences and reuses them.
- **The Gemini path is held to the same rule:** every prompt instructs the model to quote verbatim and not to invent facts, numbers, or quotes. Chapters and quotes bypass the AI entirely, even when a key is set.

If an output ever looks generic, the cause is almost always a thin transcript — feed it a real, substantive recording and the pack is substantive.

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

## Honest limitations

- **Whisper accuracy is not perfect.** Accents, crosstalk, music and low-quality audio produce errors, and those errors flow into every output. The `base` model is noticeably more accurate than `tiny`; `small` is better still but slower. Always skim the transcript for names and numbers before publishing.
- **Gemini's free tier changes.** Model names, rate limits and quotas have rotated before and will again. If a Gemini call fails, the tool falls back to local generation and tells you why — but the AI-rewritten version depends on Google's current free tier, which this repo does not control. The Gemini attempt is time-boxed to 120 seconds wall-clock: if the API endpoint does not answer at all (blocked network, outage), the tool gives up on AI and falls back instead of hanging. A successful Gemini call was not testable in the build sandbox (Google's API endpoint is blocked there by a proxy TLS error), so the live AI rewrite is verified by code path, not by a live call — try it with your own free key.
- **YouTube transcripts are not guaranteed.** Some videos have captions disabled, are private/age-restricted, or have no English captions. When that happens the CLI prints the exact reason and tells you to use `--transcribe-audio` or a transcript file instead. It never silently returns an empty pack.
- **The local fallback does not "write" like a human.** It extracts and reorders your own sentences. That is deliberate — it cannot invent — but the AI path (with a key) reads more naturally. For the best result, use the local pack as a draft and the Gemini pack as the polish.
- **X posts are length-checked, not style-checked.** The code guarantees ≤ 280 characters per post; it cannot guarantee a post will perform well.
- **Sample numbers are sample numbers.** The demo transcript's figures (400 subscribers, 3,100 subscribers, etc.) belong to that fictional sample episode. They are not claims about this tool.

## Project structure

```
creator-repurpose-agent/
├── app.py                  # Streamlit web app (deploy-ready, repo root)
├── repurpose/
│   ├── __init__.py
│   ├── __main__.py         # python -m repurpose
│   ├── cli.py              # argument parsing, input routing, exit codes
│   ├── transcribe.py       # faster-whisper + .txt/.srt parsing
│   ├── fetch_youtube.py    # captions, yt-dlp audio fallback, titles
│   ├── generate.py         # Gemini + local extractive fallback
│   └── outputs.py          # file writing + combined pack
├── prompts/                # editable templates, one per output type
├── sample_data/
│   ├── sample_transcript.txt
│   └── sample_output/      # expected output from the demo run + index.html demo page
├── requirements.txt
├── pyproject.toml
├── .env.example
└── LICENSE (MIT)
```

## Contributing

Issues and pull requests are welcome — especially better extractive ranking, more output templates, and support for more transcript formats. Please do not add any dependency that needs a paid API key to run the demo.

## License

MIT — see [LICENSE](LICENSE).
