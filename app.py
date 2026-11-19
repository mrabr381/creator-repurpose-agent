"""Streamlit web app for the Creator Repurpose Agent.

Run: streamlit run app.py
Then open the local URL Streamlit prints. Nothing is uploaded anywhere:
audio transcription runs locally with faster-whisper, and Gemini is only
called if you paste your own free-tier key into the sidebar.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from repurpose.fetch_youtube import fetch_youtube_transcript, fetch_youtube_via_audio, is_youtube_url
from repurpose.generate import generate
from repurpose.outputs import FILE_NAMES, slugify, write_pack
from repurpose.transcribe import (
    TranscriptionUnavailable,
    load_transcript_file,
    parse_bracketed_transcript,
    transcribe_audio,
)

OUTPUT_LABELS = {
    "show_notes": "Show notes",
    "blog_post": "Blog post",
    "linkedin_post": "LinkedIn post",
    "x_thread": "X thread",
    "newsletter": "Newsletter",
    "chapters": "Chapters",
    "pull_quotes": "Pull quotes",
}


def _load_input(mode: str, url: str, uploaded, pasted: str, model: str):
    """Return (transcript, title, error_message). Exactly one of transcript/error is set."""
    if mode == "YouTube URL":
        if not url.strip():
            return None, "", "Paste a YouTube URL first."
        if not is_youtube_url(url):
            return None, "", "That does not look like a YouTube watch/shorts/youtu.be URL."
        try:
            transcript = fetch_youtube_transcript(url.strip())
            return transcript, transcript.title or "YouTube episode", ""
        except Exception as exc:  # noqa: BLE001 — surfaced verbatim to the user
            return None, "", (
                f"Could not fetch YouTube captions: {exc}\n\n"
                "Try uploading the audio file instead, or paste a transcript below."
            )
    if mode == "Upload audio / video":
        if uploaded is None:
            return None, "", "Choose an audio or video file first."
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = tmp.name
        try:
            transcript = transcribe_audio(tmp_path, model=model)
        except TranscriptionUnavailable as exc:
            return None, "", str(exc)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return transcript, Path(uploaded.name).stem.replace("-", " ").replace("_", " ").title(), ""
    if mode == "Upload transcript (.txt / .srt)":
        if uploaded is None:
            return None, "", "Choose a .txt or .srt file first."
        suffix = Path(uploaded.name).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="w", encoding="utf-8") as tmp:
            tmp.write(uploaded.getvalue().decode("utf-8", errors="replace"))
            tmp_path = tmp.name
        try:
            transcript = load_transcript_file(tmp_path)
        except Exception as exc:  # noqa: BLE001
            return None, "", f"Could not read that transcript file: {exc}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return transcript, Path(uploaded.name).stem.replace("-", " ").replace("_", " ").title(), ""
    # Paste transcript
    if len(pasted.strip().split()) < 20:
        return None, "", "Paste at least a few sentences of transcript (20+ words) — a one-liner has nothing to repurpose."
    return parse_bracketed_transcript(pasted), "Pasted transcript", ""


def main() -> None:
    st.set_page_config(page_title="Creator Repurpose Agent", page_icon="🎙️", layout="wide")
    st.title("🎙️ Creator Repurpose Agent")
    st.write(
        "One long recording in — show notes, a blog post, LinkedIn + X posts, "
        "a newsletter, chapters and pull quotes out. Free and open source. "
        "No key needed for the local version."
    )

    with st.sidebar:
        st.header("Settings")
        api_key = st.text_input(
            "Gemini API key (optional, free tier, bring-your-own)",
            value=os.environ.get("GEMINI_API_KEY", ""),
            type="password",
            help="Leave blank to use the local fallback. Your key is never stored — it is only used for this run.",
        )
        model = st.selectbox("Whisper model (local transcription)", ["tiny", "base", "small"], index=0)
        st.caption("tiny = fastest, smallest download. base = noticeably more accurate.")
        if api_key:
            st.success("Gemini key provided — AI-rewritten outputs. Chapters and quotes stay verbatim.")
        else:
            st.info("No key — local fallback. Outputs are extracted from your transcript; nothing is invented.")

    mode = st.radio(
        "Input",
        ["YouTube URL", "Upload audio / video", "Upload transcript (.txt / .srt)", "Paste transcript"],
        horizontal=True,
    )
    url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...") if mode == "YouTube URL" else ""
    uploaded = None
    pasted = ""
    if mode in ("Upload audio / video", "Upload transcript (.txt / .srt)"):
        accept = ["mp3", "wav", "m4a", "mp4", "ogg", "flac", "webm"] if "audio" in mode else ["txt", "srt"]
        uploaded = st.file_uploader("Choose a file", type=accept)
    if mode == "Paste transcript":
        pasted = st.text_area("Transcript (use [MM:SS] markers if you have them — chapters use them)",
                              height=220, placeholder="[00:00] Welcome back to the show…")

    title = st.text_input("Episode title (optional)", placeholder="Leave blank to use the video / file name")
    selected_labels = st.multiselect(
        "Outputs to generate",
        options=list(OUTPUT_LABELS.values()),
        default=list(OUTPUT_LABELS.values()),
    )
    selected = {key for key, label in OUTPUT_LABELS.items() if label in selected_labels}

    if st.button("Generate pack", type="primary", disabled=not selected):
        if not selected:
            st.error("Pick at least one output.")
            return
        with st.spinner("Working…"):
            transcript, derived_title, error = _load_input(mode, url, uploaded, pasted, model)
        if error:
            st.error(error)
            return
        final_title = title.strip() or derived_title
        st.success(f"Transcript ready: {transcript.word_count} words"
                   + (" · timestamps included" if transcript.has_timestamps else " · no timestamps (chapters will be estimated and labelled as such)"))
        with st.spinner("Generating…"):
            try:
                result = generate(transcript, title=final_title, selected=selected,
                                  api_key=api_key or None)
            except ValueError as exc:
                st.error(str(exc))
                return
        st.info(f"Engine: {result.engine}. {result.note}")
        out_dir = Path("output") / slugify(final_title)
        written = write_pack(result, out_dir, final_title)
        st.success(f"Pack written to {out_dir}/")
        for key, filename in FILE_NAMES.items():
            if key not in result.outputs:
                continue
            with st.expander(OUTPUT_LABELS[key]):
                st.markdown(result.outputs[key])
                st.download_button(
                    f"Download {filename}", data=result.outputs[key],
                    file_name=filename, key=f"dl-{key}",
                )
        combined = (out_dir / "repurpose_pack.md").read_text(encoding="utf-8")
        st.download_button("Download full pack (repurpose_pack.md)", data=combined,
                           file_name="repurpose_pack.md", key="dl-pack")


if __name__ == "__main__":
    main()
