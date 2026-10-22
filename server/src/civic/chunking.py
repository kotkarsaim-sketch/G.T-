"""Chunking utilities: article-boundary aware splitting (ADR-004).

Pure functions, no I/O — unit tested without services.
"""

import re
from dataclasses import dataclass, field

DEFAULT_ARTICLE_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<heading>.+)$")

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?:;])\s+")


@dataclass
class ArticleDraft:
    number: str
    heading: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.heading:
            return f"Section {self.number} - {self.heading}"
        return f"Section {self.number}"


def estimate_tokens(text: str) -> int:
    """Cheap heuristic (~4 chars/token); consistent because it is the only counter."""
    return max(1, len(text) // 4)


def split_articles(text: str, pattern: str | None = None) -> list[ArticleDraft]:
    """Split raw instrument text into articles.

    Lines matching the heading pattern start a new article. Text before the
    first match becomes the 'Preamble' article. Blank lines separate paragraphs.
    """
    rx = re.compile(pattern) if pattern else DEFAULT_ARTICLE_RE
    articles: list[ArticleDraft] = []
    current: ArticleDraft | None = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph and current is not None:
            joined = " ".join(part.strip() for part in paragraph if part.strip())
            if joined:
                current.paragraphs.append(joined)
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        m = rx.match(line)
        if m:
            flush_paragraph()
            current = ArticleDraft(number=m.group("num").strip(), heading=m.group("heading").strip())
            articles.append(current)
        else:
            paragraph.append(line)
            if current is None:
                # preamble accumulates before any heading exists
                current = ArticleDraft(number="Preamble", heading="")
                articles.append(current)
    flush_paragraph()
    return articles


def _pack(sentences: list[str], max_tokens: int) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sentence in sentences:
        t = estimate_tokens(sentence)
        if buf and buf_tokens + t > max_tokens:
            chunks.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(sentence)
        buf_tokens += t
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def chunk_article(
    article: ArticleDraft,
    max_tokens: int = 320,
    min_tail_tokens: int = 60,
) -> list[str]:
    """Split one article into ordered chunk texts. Never crosses article bounds."""
    if not article.paragraphs:
        return []
    full_text = "\n".join(article.paragraphs)
    if estimate_tokens(full_text) <= max_tokens:
        return [full_text]

    packed_paragraphs: list[str] = []
    for para in article.paragraphs:
        if estimate_tokens(para) <= max_tokens:
            packed_paragraphs.append(para)
        else:
            packed_paragraphs.extend(_pack(SENTENCE_SPLIT_RE.split(para), max_tokens))

    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for para in packed_paragraphs:
        t = estimate_tokens(para)
        if buf and buf_tokens + t > max_tokens:
            chunks.append("\n".join(buf))
            buf, buf_tokens = [], 0
        buf.append(para)
        buf_tokens += t
    if buf:
        tail = "\n".join(buf)
        if chunks and estimate_tokens(tail) < min_tail_tokens:
            chunks[-1] = chunks[-1] + "\n" + tail
        else:
            chunks.append(tail)
    return chunks
