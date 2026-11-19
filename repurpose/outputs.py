"""Write a generated pack to disk.

Filenames are fixed so the CLI, the Streamlit app and the sample output
all agree. Every file is checked after writing: it must exist and be
non-empty, otherwise writing raises — a silent empty output is a bug.
"""

from __future__ import annotations

import re
from pathlib import Path

from .generate import GenerationResult

FILE_NAMES = {
    "show_notes": "show_notes.md",
    "blog_post": "blog_post.md",
    "linkedin_post": "linkedin_post.txt",
    "x_thread": "x_thread.txt",
    "newsletter": "newsletter.md",
    "chapters": "chapters.md",
    "pull_quotes": "pull_quotes.md",
}

ALL_OUTPUTS = set(FILE_NAMES)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "episode").lower()).strip("-")
    return slug or "episode"


def write_pack(result: GenerationResult, out_dir: str | Path, title: str) -> list[Path]:
    """Write all generated outputs + a combined pack. Returns written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key, filename in FILE_NAMES.items():
        if key not in result.outputs:
            continue
        content = result.outputs[key].strip() + "\n"
        if not content.strip():
            raise ValueError(f"Refusing to write an empty output file: {filename}")
        path = out_dir / filename
        path.write_text(content, encoding="utf-8")
        if path.stat().st_size == 0:
            raise ValueError(f"Wrote an empty output file: {filename}")
        written.append(path)

    # Combined pack, in reading order, with the engine note up front.
    combined = [
        f"# Repurpose pack — {title}",
        "",
        f"_Engine: {result.engine}. {result.note}_",
        "",
    ]
    section_titles = {
        "show_notes": "Show notes", "blog_post": "Blog post",
        "linkedin_post": "LinkedIn post", "x_thread": "X thread",
        "newsletter": "Newsletter", "chapters": "Chapters",
        "pull_quotes": "Pull quotes",
    }
    for key in FILE_NAMES:
        if key not in result.outputs:
            continue
        combined.append(f"---\n\n## {section_titles[key]}\n")
        combined.append(result.outputs[key].strip())
        combined.append("")
    combined_path = out_dir / "repurpose_pack.md"
    combined_path.write_text("\n".join(combined), encoding="utf-8")
    written.append(combined_path)
    return written
