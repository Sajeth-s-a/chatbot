import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass
class DocBlock:
    text: str
    heading_path: list[str] = field(default_factory=list)
    kind: str = "paragraph"  # "paragraph" | "table" | "heading"


def _iter_block_items(doc: Document):
    """Yield paragraphs and tables in document order."""
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _heading_level(p: Paragraph) -> int | None:
    style = (p.style.name or "").strip() if p.style else ""
    if style.startswith("Heading "):
        try:
            return int(style.split()[1])
        except (IndexError, ValueError):
            return None
    if style == "Title":
        return 0
    return None


def _table_to_text(tbl: Table) -> str:
    rows = []
    for row in tbl.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(r for r in rows if r.strip())


def _repair_docx_bytes(path: Path) -> io.BytesIO:
    """Strip relationships pointing to parts that don't exist in the archive.

    Some exported .docx files leave dangling refs (e.g. to word/comments.xml)
    even after the underlying part was removed. python-docx is strict about
    this, so we rewrite the .rels files in memory before opening.
    """
    with zipfile.ZipFile(path, "r") as zin:
        names = set(zin.namelist())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(".rels"):
                    text = data.decode("utf-8", errors="ignore")
                    base = item.filename.rsplit("/", 1)[0].replace("_rels", "").strip("/")

                    def _keep(match: re.Match) -> str:
                        tag = match.group(0)
                        tm = re.search(r'Target="([^"]+)"', tag)
                        if not tm:
                            return tag
                        target = tm.group(1)
                        resolved = f"{base}/{target}" if base else target
                        resolved = re.sub(r"/+", "/", resolved)
                        return "" if resolved not in names else tag

                    text = re.sub(r"<Relationship\b[^>]*/>", _keep, text)
                    data = text.encode("utf-8")
                zout.writestr(item, data)
    buf.seek(0)
    return buf


def load_docx(path: Path) -> list[DocBlock]:
    """Parse a .docx into ordered blocks, tagging each with its heading path."""
    try:
        doc = Document(str(path))
    except KeyError:
        doc = Document(_repair_docx_bytes(path))
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    blocks: list[DocBlock] = []

    for item in _iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            level = _heading_level(item)
            if level is not None:
                heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
                heading_stack.append((level, text))
                blocks.append(
                    DocBlock(
                        text=text,
                        heading_path=[t for _, t in heading_stack],
                        kind="heading",
                    )
                )
            else:
                blocks.append(
                    DocBlock(
                        text=text,
                        heading_path=[t for _, t in heading_stack],
                        kind="paragraph",
                    )
                )
        elif isinstance(item, Table):
            text = _table_to_text(item)
            if text:
                blocks.append(
                    DocBlock(
                        text=text,
                        heading_path=[t for _, t in heading_stack],
                        kind="table",
                    )
                )

    return blocks
