"""Text extraction from uploaded artifact files -- no live Gemini
credentials needed, this is pure file parsing."""

import io

import pytest
from docx import Document
from fastapi import UploadFile
from starlette.datastructures import Headers

from bulwark.api.document_extraction import (
    EmptyExtractionError,
    UnsupportedFileError,
    extension_of,
    extract_text,
)


def _upload(filename: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data), headers=Headers({"content-type": content_type}))


def _make_minimal_pdf(text: str) -> bytes:
    """A hand-built, minimally-valid one-page PDF with a real text stream --
    avoids pulling in a PDF-writing dependency just to test the reader."""
    content = f"BT /F1 24 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = buf.tell()
    n = len(objects) + 1
    buf.write(f"xref\n0 {n}\n".encode() + b"0000000000 65535 f \n")
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())
    return buf.getvalue()


def _make_docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extension_of_handles_missing_and_present_extensions():
    assert extension_of("report.pdf") == ".pdf"
    assert extension_of("Report.PDF") == ".pdf"
    assert extension_of("no-extension") == ""
    assert extension_of(None) == ""


async def test_extract_text_reads_a_real_pdf():
    pdf_bytes = _make_minimal_pdf("We enforce multi-factor authentication for all employees")
    text = await extract_text(_upload("soc2.pdf", pdf_bytes, "application/pdf"))
    assert "multi-factor authentication" in text


async def test_extract_text_reads_a_real_docx():
    docx_bytes = _make_docx(["Data Processing Agreement", "Vendor will notify Buyer within 30 days of a breach."])
    text = await extract_text(_upload("dpa.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
    assert "Data Processing Agreement" in text
    assert "30 days" in text


async def test_extract_text_reads_plain_text():
    text = await extract_text(_upload("notes.txt", b"Plain evidence notes."))
    assert text == "Plain evidence notes."


async def test_extract_text_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileError):
        await extract_text(_upload("malware.exe", b"whatever"))


async def test_extract_text_rejects_oversized_file():
    from bulwark.api import document_extraction

    with pytest.raises(UnsupportedFileError):
        await extract_text(_upload("huge.txt", b"x" * (document_extraction.MAX_UPLOAD_BYTES + 1)))


async def test_extract_text_raises_on_empty_pdf_with_no_text_layer():
    # A page with no /Contents stream at all -- the "scanned image" case.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = buf.tell()
    n = len(objects) + 1
    buf.write(f"xref\n0 {n}\n".encode() + b"0000000000 65535 f \n")
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())

    with pytest.raises(EmptyExtractionError):
        await extract_text(_upload("scanned.pdf", buf.getvalue(), "application/pdf"))
