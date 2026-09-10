"""Reading a .docx (T-85), on files this test builds itself.

The fixture files are assembled here rather than committed as binaries. They
are ours (the NDA on the foundation's material is still open, B-09), they are
readable in the diff, and a test that needs a paragraph with a broken style can
just write one.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models.panel import PanelUser
from app.schemas.documents import DocumentContentRequest
from app.services.docx_import import (
    REASON_TABLE,
    REASON_UNREADABLE,
    UnreadableDocument,
    read_document,
)
from tests.conftest import EDITOR_PASSWORD, auth_header, log_in

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
</w:styles>"""

_TABLE = (
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Komorka</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
)


def paragraph(text: str, style: str | None = None) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{properties}<w:r><w:t>{text}</w:t></w:r></w:p>"


def docx(body: str) -> bytes:
    """One .docx package holding exactly the body XML it is given."""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _PACKAGE_RELS)
        archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS)
        archive.writestr("word/styles.xml", _STYLES)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


CHAPTER = docx(
    paragraph("Dwujezycznosc w przedszkolu", "Heading1")
    + paragraph("Rodzic pyta, od kiedy zaczac.")
    + paragraph("")
    + paragraph("Co mowia badania", "Heading2")
    + paragraph("Od pierwszego dnia, konsekwentnie.")
)


class TestReadingAFile:
    def test_headings_and_text_keep_their_structure(self) -> None:
        result = read_document(CHAPTER, max_bytes=1_000_000)

        assert result.title == "Dwujezycznosc w przedszkolu"
        assert result.heading_count == 2
        assert result.paragraph_count == 2
        assert "# Dwujezycznosc w przedszkolu" in result.content
        assert "## Co mowia badania" in result.content
        assert "Od pierwszego dnia, konsekwentnie." in result.content

    def test_an_empty_paragraph_is_spacing_not_a_loss(self) -> None:
        """A report full of "blank line skipped" hides the entries that matter."""
        result = read_document(CHAPTER, max_bytes=1_000_000)

        assert result.skipped == []

    def test_the_title_falls_back_to_the_first_line_when_there_is_no_heading(self) -> None:
        result = read_document(
            docx(paragraph("Pierwsze zdanie materialu.") + paragraph("Drugie.")),
            max_bytes=1_000_000,
        )

        assert result.title == "Pierwsze zdanie materialu."

    def test_a_heading_laid_out_with_a_tab_still_makes_a_savable_title(self) -> None:
        """Word writes numbered headings as "Rozdzial<tab>Tytul", and python-docx
        reads `<w:tab/>` back as a real tab. `app.schemas.documents` refuses a
        tab in a title, so a preview that handed one over produced a proposal
        the save endpoint answered 422 to, about a character nobody can see."""
        result = read_document(
            docx(
                '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r>'
                "<w:t>Rozdzial 1</w:t><w:tab/><w:t>Kiedy zaczac</w:t>"
                "</w:r></w:p>" + paragraph("Tresc rozdzialu.")
            ),
            max_bytes=1_000_000,
        )

        assert result.title == "Rozdzial 1 Kiedy zaczac"
        DocumentContentRequest(title=result.title, content=result.content)


class TestResilience:
    def test_a_paragraph_with_a_style_the_file_never_defines_is_still_read(self) -> None:
        """Word writes these whenever a template is edited elsewhere. Losing the
        whole import to one of them is not a trade worth making."""
        result = read_document(
            docx(
                paragraph("Tytul rozdzialu", "Heading1")
                + paragraph("Akapit ze zlamanym stylem", "StylKtoregoNieMa")
                + paragraph("Zwykly akapit.")
            ),
            max_bytes=1_000_000,
        )

        assert "Akapit ze zlamanym stylem" in result.content
        assert "Zwykly akapit." in result.content
        assert result.heading_count == 1

    def test_a_table_is_reported_rather_than_silently_dropped(self) -> None:
        """An editor who cannot see that a table was left out finds it missing
        from an answer months later."""
        result = read_document(
            docx(paragraph("Rozdzial", "Heading1") + _TABLE), max_bytes=1_000_000
        )

        assert [(item.reason, item.count) for item in result.skipped] == [(REASON_TABLE, 1)]

    def test_something_that_is_not_a_docx_is_the_callers_file_being_wrong(self) -> None:
        with pytest.raises(UnreadableDocument) as refused:
            read_document(b"to nie jest dokument Worda", max_bytes=1_000_000)

        assert str(refused.value) == "not_a_docx"

    def test_a_file_with_no_text_is_refused_rather_than_saved_empty(self) -> None:
        with pytest.raises(UnreadableDocument) as refused:
            read_document(docx(paragraph("") + paragraph("   ")), max_bytes=1_000_000)

        assert str(refused.value) == "no_text_found"

    def test_the_size_limit_is_checked_before_anything_is_parsed(self) -> None:
        with pytest.raises(UnreadableDocument) as refused:
            read_document(CHAPTER, max_bytes=10)

        assert str(refused.value) == "file_too_large"

    def test_the_reason_key_for_an_unreadable_paragraph_exists(self) -> None:
        """Pinned so the frontend dictionary and the service cannot drift: the
        Polish sentence explaining this is keyed by exactly this string."""
        assert REASON_UNREADABLE == "unreadable_paragraph"


class TestTheEndpoint:
    def upload(self, client: TestClient, token: str, name: str, data: bytes):
        return client.post(
            "/api/panel/document-imports",
            headers=auth_header(token),
            files={
                "file": (
                    name,
                    data,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    def test_no_token_reads_nothing(self, panel_client: TestClient) -> None:
        response = panel_client.post(
            "/api/panel/document-imports",
            files={"file": ("rozdzial.docx", CHAPTER, "application/octet-stream")},
        )
        assert response.status_code == 401

    def test_a_readable_file_comes_back_as_a_preview_and_writes_nothing(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        """The whole point of the preview: a misread file is refused by a person,
        not discovered as a draft in the knowledge base later."""
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        response = self.upload(panel_client, token, "rozdzial.docx", CHAPTER)

        assert response.status_code == 200
        assert response.json()["title"] == "Dwujezycznosc w przedszkolu"
        assert panel_client.get("/api/panel/documents", headers=auth_header(token)).json() == []

    def test_the_extension_is_checked_on_the_server_not_only_in_the_form(
        self, panel_client: TestClient, panel_editor: PanelUser
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)

        response = self.upload(panel_client, token, "material.txt", CHAPTER)

        assert response.status_code == 422
        assert response.json()["detail"] == "not_a_docx"

    def test_an_oversized_upload_is_refused_by_size_not_by_content(
        self,
        panel_client: TestClient,
        panel_editor: PanelUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = log_in(panel_client, panel_editor.email, EDITOR_PASSWORD)
        monkeypatch.setattr(settings, "docx_import_max_bytes", 32)

        response = self.upload(panel_client, token, "rozdzial.docx", CHAPTER)

        assert response.status_code == 413
        assert response.json()["detail"] == "file_too_large"
