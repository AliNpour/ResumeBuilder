#!/usr/bin/env python3
"""Extract plain text from a resume file (PDF, DOCX, or TXT)."""

import sys
import os


def parse_pdf(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        pass
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        raise RuntimeError("Install pdfplumber or PyMuPDF: pip install pdfplumber")


def parse_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def parse_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext in (".docx", ".doc"):
        return parse_docx(path)
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_resume.py <resume_file>", file=sys.stderr)
        sys.exit(1)
    text = parse_file(sys.argv[1])
    print(text)
