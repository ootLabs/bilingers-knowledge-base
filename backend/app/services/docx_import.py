"""Reading a .docx into the shape the knowledge base stores (T-85).

The foundation writes in Word and will keep writing in Word. Retyping or
repasting a chapter at every update is a guaranteed error, so this reads the
file instead: headings and the text under them, and nothing else.

Two rules shape the whole module:

* It never fails whole because one paragraph is broken. A file that survived
  five people and three versions of Word has odd runs in it, and losing forty
  readable sections to one unreadable one is not a trade worth making. Whatever
  could not be read comes back in the report, counted and named.
* It reads bytes, never a path. The uploaded file is parsed in memory and the
  name the browser sent is used for nothing at all, least of all to build a
  filename on disk.

Nothing here corrects the material (D9) and nothing here chunks or embeds it:
that is T-21 and T-22, and they run at publication, not at import.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

from docx import Document as read_docx
from docx.opc.exceptions import PackageNotFoundError

# What the reader recognises as a heading, in the spellings Word actually
# writes. `style.name` is localised in a Polish install, and `style.style_id`
# is not, so both are tried; a trailing digit is the level.
_HEADING_STYLE = re.compile(r"^(?:heading|nag[lł][oó]wek|tytu[lł]|title)\s*(\d*)$")

# Everything a terminal would act on rather than print, except the whitespace
# that carries the text's shape. Word smuggles these in from pasted material,
# and psycopg refuses a NUL byte outright, so they are stripped at the point
# the text enters the system rather than being discovered at INSERT time.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_TITLE_LIMIT = 500

# Skip reasons. Keys, not sentences: the Polish that explains each of them to
# the editor lives in the frontend dictionary.
REASON_UNREADABLE = "unreadable_paragraph"
REASON_TABLE = "table_not_imported"


class UnreadableDocument(Exception):
    """The upload is not a .docx this can read, or holds no text at all."""


@dataclass(frozen=True)
class SkippedItem:
    """One thing that did not make it in, and why."""

    reason: str
    count: int


@dataclass(frozen=True)
class ImportedDocument:
    """What the reader understood, for the editor to accept or throw away.

    Nothing is written when this is produced. The preview exists precisely so a
    misread file is refused by a person rather than silently becoming a draft.
    """

    title: str
    content: str
    heading_count: int
    paragraph_count: int
    skipped: list[SkippedItem]


def _clean(text: str) -> str:
    return _CONTROL_CHARACTERS.sub("", text).strip()


def _style_candidates(paragraph: object) -> list[str]:
    """Every name this paragraph's style is known by, lowercased.

    Guarded, because python-docx raises when a paragraph names a style id the
    document's own styles part never defines, which Word writes whenever a
    template is edited elsewhere. A paragraph like that is still readable text;
    it just cannot be trusted to be a heading.
    """
    try:
        style = paragraph.style  # type: ignore[attr-defined]
        if style is None:
            return []
        names = [str(style.name or ""), str(style.style_id or "")]
    except (KeyError, AttributeError, ValueError):
        return []
    # "Heading1" and "Heading 1" are the same style written two ways.
    return [re.sub(r"(\d+)$", r" \1", name).strip().lower() for name in names if name]


def _heading_level(paragraph: object) -> int | None:
    for candidate in _style_candidates(paragraph):
        match = _HEADING_STYLE.match(candidate)
        if match:
            level = int(match.group(1)) if match.group(1) else 1
            # Word goes to nine; anything deeper is not a heading anybody reads
            # as one, and it keeps the marker below bounded.
            return min(max(level, 1), 6)
    return None


def read_document(data: bytes, *, max_bytes: int) -> ImportedDocument:
    """Turn an uploaded .docx into a title and a body, plus a report.

    `max_bytes` is checked here as well as at the boundary: this function is
    the one that allocates, so it is the one that must not be talked into
    allocating without a limit.
    """
    if len(data) > max_bytes:
        raise UnreadableDocument("file_too_large")

    try:
        document = read_docx(BytesIO(data))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as error:
        # A renamed .doc, a PDF with the wrong extension, a truncated upload.
        # All of them are the caller's file being wrong, not the server.
        raise UnreadableDocument("not_a_docx") from error

    lines: list[str] = []
    headings = 0
    paragraphs = 0
    unreadable = 0

    for paragraph in document.paragraphs:
        try:
            text = _clean(paragraph.text or "")
        except Exception:  # noqa: BLE001 - one bad paragraph must not end the import
            unreadable += 1
            continue
        if text == "":
            # An empty paragraph is spacing, not a loss. It is not reported,
            # because a report full of "blank line skipped" hides the entries
            # that matter.
            continue

        level = _heading_level(paragraph)
        if level is None:
            lines.append(text)
            paragraphs += 1
        else:
            lines.append(f"{'#' * level} {text}")
            headings += 1

    skipped: list[SkippedItem] = []
    if unreadable:
        skipped.append(SkippedItem(reason=REASON_UNREADABLE, count=unreadable))
    # Tables are not read. Saying so is the point: an editor who cannot see that
    # a table was left out will find it missing from an answer months later.
    table_count = len(document.tables)
    if table_count:
        skipped.append(SkippedItem(reason=REASON_TABLE, count=table_count))

    if not lines:
        raise UnreadableDocument("no_text_found")

    return ImportedDocument(
        title=_title_from(lines),
        content="\n\n".join(lines),
        heading_count=headings,
        paragraph_count=paragraphs,
        skipped=skipped,
    )


def _title_from(lines: list[str]) -> str:
    """The document's own first heading, or its first line of text.

    A proposal, not a decision: the preview screen lets the editor change it
    before anything is saved. The uploaded filename is deliberately not used,
    here or anywhere else.
    """
    for line in lines:
        if line.startswith("#"):
            return line.lstrip("#").strip()[:_TITLE_LIMIT]
    return lines[0][:_TITLE_LIMIT]
