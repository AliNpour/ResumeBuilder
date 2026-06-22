import os
import io
import json
import sys
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

ROOT = Path(__file__).parent  # on Vercel, api/ is at repo root so siblings are here too
# If templates/ is not found next to api/, check one level up (local dev layout)
if not (ROOT / "templates").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "resume_agent"))

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
    static_url_path="/static",
)


# ── Helpers ────────────────────────────────────────────────────────────────

def make_client():
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set on server")
    return anthropic.Anthropic(api_key=key)


def claude_json(client, prompt: str, max_tokens: int = 2000):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/parse-resume", methods=["POST"])
def parse_resume_api():
    resume_text = ""

    if "file" in request.files and request.files["file"].filename:
        f = request.files["file"]
        suffix = Path(f.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            from parse_resume import parse_file
            resume_text = parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)
    else:
        resume_text = request.form.get("resume_text", "").strip()

    if not resume_text:
        return jsonify({"error": "No resume content found"}), 400

    try:
        client = make_client()
        profile = claude_json(client, f"""Extract the candidate's profile from this resume. Return ONLY valid JSON with no extra text:
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "555-000-0000",
  "location": "City, State",
  "linkedin": "linkedin url or empty string",
  "current_title": "Most recent job title",
  "years_experience": "e.g. 5",
  "top_skills": ["skill1", "skill2", "skill3", "skill4", "skill5"],
  "industries": ["industry1", "industry2"],
  "summary": "2-3 sentence professional summary"
}}

Resume:
{resume_text[:5000]}""", max_tokens=800)
    except Exception as e:
        return jsonify({"error": f"Failed to analyze resume: {str(e)}"}), 500

    return jsonify({"profile": profile, "resume_text": resume_text})


@app.route("/api/search-jobs", methods=["POST"])
def search_jobs_api():
    data = request.get_json()
    profile  = data.get("profile", {})
    location = data.get("location", "").strip()
    position = data.get("position", "").strip()
    salary   = data.get("salary", "").strip()

    search_term = position or profile.get("current_title", "Software Engineer")

    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=["indeed", "linkedin"],
            search_term=search_term,
            location=location,
            results_wanted=30,
            hours_old=336,
            country_indeed="USA",
        )

        jobs_raw = []
        for _, row in df.iterrows():
            mn, mx = row.get("min_amount"), row.get("max_amount")
            curr = row.get("currency", "USD") or "USD"
            sal  = f"{curr} {int(mn):,} – {int(mx):,}" if mn and mx else ("Not listed")

            jobs_raw.append({
                "title":       str(row.get("title", "")),
                "company":     str(row.get("company", "")),
                "location":    str(row.get("location", "")),
                "job_url":     str(row.get("job_url", "")),
                "description": str(row.get("description", ""))[:3000],
                "date_posted": str(row.get("date_posted", "")),
                "salary_raw":  sal,
                "is_remote":   bool(row.get("is_remote", False)),
                "site":        str(row.get("site", "")),
            })
    except Exception as e:
        return jsonify({"error": f"Job search failed: {str(e)}"}), 500

    if not jobs_raw:
        return jsonify({"error": "No jobs found. Try a different location or position."}), 404

    try:
        client = make_client()
        for_scoring = [
            {"index": i, "title": j["title"], "company": j["company"],
             "description": j["description"][:500], "salary": j["salary_raw"],
             "is_remote": j["is_remote"], "location": j["location"]}
            for i, j in enumerate(jobs_raw)
        ]

        scored = claude_json(client, f"""You are a career advisor. Score these job postings for fit with the candidate profile.
Return ONLY a JSON array of the top 10 most relevant. Each object:
{{
  "index": <original index>,
  "score": <1-10>,
  "work_type": "Remote" | "Hybrid" | "In-Office",
  "salary_display": "<salary range or Not listed>",
  "role_summary": "2-3 sentences describing what this role does day-to-day",
  "key_qualifications": ["requirement 1", "requirement 2", "requirement 3", "requirement 4"]
}}

Candidate: {json.dumps(profile)}
Target position: {position}
Expected salary: {salary or "not specified"}

Jobs:
{json.dumps(for_scoring, indent=2)}""", max_tokens=2500)
    except Exception as e:
        return jsonify({"error": f"Scoring failed: {str(e)}"}), 500

    results = []
    for s in (scored if isinstance(scored, list) else []):
        idx = s.get("index", -1)
        if 0 <= idx < len(jobs_raw):
            results.append({**jobs_raw[idx], **s})

    return jsonify({"jobs": results[:10]})


@app.route("/api/tailor-resume", methods=["POST"])
def tailor_resume_api():
    data        = request.get_json()
    resume_text = data.get("resume_text", "")
    profile     = data.get("profile", {})
    jobs        = data.get("selected_jobs", [])

    client  = make_client()
    results = []

    for job in jobs:
        try:
            tailored = claude_json(client, f"""You are an expert resume writer. Tailor this resume for the job below.
Return ONLY valid JSON — no markdown, no explanation outside JSON.

RULES:
- Mirror the job's keywords and phrases naturally
- Reorder skills so most relevant appear first
- Strengthen bullet points with quantified outcomes where the original is vague
- Rewrite the summary to address this specific role
- NEVER invent experience, companies, dates, degrees, or skills

JSON schema:
{{
  "name": "", "email": "", "phone": "", "location": "", "linkedin": "",
  "summary": "",
  "skills": [],
  "experience": [{{"title":"","company":"","dates":"","bullets":[]}}],
  "education": [{{"degree":"","school":"","dates":"","details":""}}],
  "certifications": [],
  "changes_made": ["change 1","change 2","change 3","change 4"]
}}

Original resume:
{resume_text[:4000]}

Job:
Title: {job.get("title","")}
Company: {job.get("company","")}
Description: {job.get("description","")[:2500]}""", max_tokens=3500)

            tailored.update({
                "job_title":      job.get("title", ""),
                "job_company":    job.get("company", ""),
                "job_url":        job.get("job_url", ""),
                "work_type":      job.get("work_type", ""),
                "salary_display": job.get("salary_display", ""),
            })
            results.append(tailored)
        except Exception as e:
            results.append({"error": str(e), "job_title": job.get("title", "")})

    return jsonify({"tailored_resumes": results})


@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf_api():
    data        = request.get_json()
    resume_data = data.get("resume_data", {})
    company     = data.get("company", "tailored").lower().replace(" ", "_")

    try:
        from generate_pdf import build_pdf_bytes
        pdf_bytes = build_pdf_bytes(resume_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resume_{company}.pdf",
    )
