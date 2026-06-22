#!/usr/bin/env python3
"""
Generate an ATS-friendly PDF resume from a JSON resume data file.

JSON schema expected:
{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "555-000-0000",
  "location": "City, State",
  "linkedin": "linkedin.com/in/handle",   // optional
  "summary": "Professional summary text",
  "skills": ["Python", "AWS", ...],
  "experience": [
    {
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Jan 2020 ΓÇô Present",
      "bullets": ["Did X", "Achieved Y by Z%", ...]
    }
  ],
  "education": [
    {
      "degree": "B.S. Computer Science",
      "school": "University Name",
      "dates": "2014 ΓÇô 2018",
      "details": "GPA 3.8, Dean's List"  // optional
    }
  ],
  "certifications": ["AWS Solutions Architect", ...]   // optional
}
"""

import sys
import json
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

def sanitize(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica with ASCII equivalents."""
    if not text:
        return text
    replacements = {
        'ΓÇô': '-',   # en dash
        'ΓÇö': '-',   # em dash
        'ΓÇÿ': "'",   # left single quote
        'ΓÇÖ': "'",   # right single quote / apostrophe
        'ΓÇ£': '"',   # left double quote
        'ΓÇ¥': '"',   # right double quote
        'ΓÇó': '*',   # bullet
        '├ó┬Ç┬ô': '-',  # mangled en dash
        '├ó┬Ç┬ö': '-',  # mangled em dash
        '┬á': ' ',   # non-breaking space
        'ΓÇª': '...',  # ellipsis
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-latin1 characters Helvetica can't handle
    text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text


def s(text) -> str:
    """Sanitize a value that may be None."""
    return sanitize(str(text)) if text else ''


ACCENT = colors.HexColor("#1a3a5c")
BODY_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"
FONT_BODY = 10
FONT_SMALL = 9
FONT_SECTION = 11
FONT_NAME = 18


def build_styles():
    styles = getSampleStyleSheet()

    def add(name, **kw):
        if name not in styles:
            styles.add(ParagraphStyle(name=name, **kw))
        return styles[name]

    add("ResumeName",    fontName=BOLD_FONT, fontSize=FONT_NAME,
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=2)
    add("ResumeContact", fontName=BODY_FONT, fontSize=FONT_SMALL,
        textColor=colors.HexColor("#444444"), alignment=TA_CENTER, spaceAfter=6)
    add("SectionHeader", fontName=BOLD_FONT, fontSize=FONT_SECTION,
        textColor=ACCENT, spaceBefore=10, spaceAfter=2)
    add("SummaryText",   fontName=BODY_FONT, fontSize=FONT_BODY,
        leading=14, spaceAfter=4)
    add("JobTitle",      fontName=BOLD_FONT, fontSize=FONT_BODY,
        textColor=colors.black, spaceBefore=6, spaceAfter=0)
    add("JobMeta",       fontName=BODY_FONT, fontSize=FONT_SMALL,
        textColor=colors.HexColor("#555555"), spaceAfter=2)
    add("Bullet",        fontName=BODY_FONT, fontSize=FONT_BODY,
        leading=13, leftIndent=12, spaceAfter=1)
    add("SkillText",     fontName=BODY_FONT, fontSize=FONT_BODY,
        leading=14, spaceAfter=4)
    add("EduLine",       fontName=BOLD_FONT, fontSize=FONT_BODY,
        spaceBefore=4, spaceAfter=0)
    add("EduDetail",     fontName=BODY_FONT, fontSize=FONT_SMALL,
        textColor=colors.HexColor("#555555"), spaceAfter=2)
    add("CertText",      fontName=BODY_FONT, fontSize=FONT_BODY,
        leading=14, spaceAfter=2)
    return styles


def divider():
    return HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=4)


def section_header(title, styles):
    return [Paragraph(title.upper(), styles["SectionHeader"]), divider()]


def build_pdf(data: dict, output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = build_styles()
    story = []

    # Header
    story.append(Paragraph(s(data["name"]), styles["ResumeName"]))
    contact_parts = [s(p) for p in [
        data.get("email"), data.get("phone"),
        data.get("location"), data.get("linkedin")
    ] if p]
    story.append(Paragraph("  |  ".join(contact_parts), styles["ResumeContact"]))
    story.append(Spacer(1, 4))

    # Summary
    if data.get("summary"):
        story += section_header("Professional Summary", styles)
        story.append(Paragraph(s(data["summary"]), styles["SummaryText"]))

    # Skills
    if data.get("skills"):
        story += section_header("Core Skills", styles)
        story.append(Paragraph(
            " | ".join(s(sk) for sk in data["skills"]), styles["SkillText"]
        ))

    # Experience
    if data.get("experience"):
        story += section_header("Experience", styles)
        for job in data["experience"]:
            story.append(Paragraph(s(job["title"]), styles["JobTitle"]))
            meta = s(job["company"])
            if job.get("dates"):
                meta += f"  |  {s(job['dates'])}"
            story.append(Paragraph(meta, styles["JobMeta"]))
            for bullet in job.get("bullets", []):
                story.append(Paragraph(f"- {s(bullet)}", styles["Bullet"]))

    # Education
    if data.get("education"):
        story += section_header("Education", styles)
        for edu in data["education"]:
            line = s(edu["degree"])
            if edu.get("dates"):
                line += f"  |  {s(edu['dates'])}"
            story.append(Paragraph(line, styles["EduLine"]))
            detail_parts = [edu.get("school"), edu.get("details")]
            detail = "  |  ".join(s(p) for p in detail_parts if p)
            if detail:
                story.append(Paragraph(detail, styles["EduDetail"]))

    # Certifications
    if data.get("certifications"):
        story += section_header("Certifications", styles)
        for cert in data["certifications"]:
            story.append(Paragraph(f"- {s(cert)}", styles["CertText"]))

    doc.build(story)
    print(f"PDF saved: {output_path}")


def build_pdf_bytes(data: dict) -> bytes:
    """Generate PDF in memory and return as bytes (used by Vercel/web deployments)."""
    import io
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = build_styles()
    story = []

    story.append(Paragraph(s(data["name"]), styles["ResumeName"]))
    contact_parts = [s(p) for p in [
        data.get("email"), data.get("phone"),
        data.get("location"), data.get("linkedin")
    ] if p]
    story.append(Paragraph("  |  ".join(contact_parts), styles["ResumeContact"]))
    story.append(Spacer(1, 4))

    if data.get("summary"):
        story += section_header("Professional Summary", styles)
        story.append(Paragraph(s(data["summary"]), styles["SummaryText"]))

    if data.get("skills"):
        story += section_header("Core Skills", styles)
        story.append(Paragraph(" | ".join(s(sk) for sk in data["skills"]), styles["SkillText"]))

    if data.get("experience"):
        story += section_header("Experience", styles)
        for job in data["experience"]:
            story.append(Paragraph(s(job["title"]), styles["JobTitle"]))
            meta = s(job["company"]) + (f"  |  {s(job['dates'])}" if job.get("dates") else "")
            story.append(Paragraph(meta, styles["JobMeta"]))
            for bullet in job.get("bullets", []):
                story.append(Paragraph(f"- {s(bullet)}", styles["Bullet"]))

    if data.get("education"):
        story += section_header("Education", styles)
        for edu in data["education"]:
            line = s(edu["degree"]) + (f"  |  {s(edu['dates'])}" if edu.get("dates") else "")
            story.append(Paragraph(line, styles["EduLine"]))
            detail = "  |  ".join(s(p) for p in [edu.get("school"), edu.get("details")] if p)
            if detail:
                story.append(Paragraph(detail, styles["EduDetail"]))

    if data.get("certifications"):
        story += section_header("Certifications", styles)
        for cert in data["certifications"]:
            story.append(Paragraph(f"- {s(cert)}", styles["CertText"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_pdf.py <resume.json> <output.pdf>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], "r") as f:
        resume_data = json.load(f)
    build_pdf(resume_data, sys.argv[2])
