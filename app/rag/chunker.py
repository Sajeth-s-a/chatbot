from dataclasses import dataclass

from app.rag.loader import DocBlock


@dataclass
class Chunk:
    text: str
    doc_name: str
    section: str
    chunk_index: int


TARGET_CHARS = 1400
OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 120


def _section_label(heading_path: list[str]) -> str:
    return " > ".join(heading_path) if heading_path else "(root)"


def _split_long(text: str, target: int, overlap: int) -> list[str]:
    if len(text) <= target:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            window = text.rfind(". ", start + target // 2, end)
            if window != -1:
                end = window + 1
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


def chunk_blocks(blocks: list[DocBlock], doc_name: str) -> list[Chunk]:
    """Group blocks under their section, split anything too large, emit Chunks."""
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for b in blocks:
        if b.kind == "heading":
            continue
        section = _section_label(b.heading_path)
        if section not in grouped:
            grouped[section] = []
            order.append(section)
        grouped[section].append(b.text)

    chunks: list[Chunk] = []
    idx = 0
    for section in order:
        body = "\n\n".join(grouped[section]).strip()
        if len(body) < MIN_CHUNK_CHARS:
            if chunks and chunks[-1].doc_name == doc_name:
                chunks[-1] = Chunk(
                    text=chunks[-1].text + "\n\n" + body,
                    doc_name=doc_name,
                    section=chunks[-1].section,
                    chunk_index=chunks[-1].chunk_index,
                )
                continue
        for piece in _split_long(body, TARGET_CHARS, OVERLAP_CHARS):
            chunks.append(
                Chunk(
                    text=f"[{section}]\n{piece}",
                    doc_name=doc_name,
                    section=section,
                    chunk_index=idx,
                )
            )
            idx += 1
    return chunks
