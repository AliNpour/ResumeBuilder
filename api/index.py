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


# ΓöÇΓöÇ Helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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

    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith(("{", "[")):
                text = part
                break

    # Extract first JSON object or array even if surrounded by prose
    import re
    if not text.startswith(("{", "[")):
        m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if m:
            text = m.group(1)

    return json.loads(text.strip())


# ΓöÇΓöÇ Routes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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


def jsearch_jobs(query, location, num=5):
    """Fetch real job listings from JSearch (RapidAPI) ΓÇö returns LinkedIn & Indeed URLs."""
    import urllib.request
    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")
    if not rapidapi_key:
        raise RuntimeError("RAPIDAPI_KEY not set")

    url = (
        "https://jsearch.p.rapidapi.com/search"
        f"?query={urllib.parse.quote(query + ' ' + location)}"
        "&num_pages=1"
        "&date_posted=week"
        "&results_per_page=" + str(num)
    )
    req = urllib.request.Request(url, headers={
        "X-RapidAPI-Key":  rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read())

    results = []
    for j in raw.get("data", [])[:num]:
        mn = j.get("job_min_salary")
        mx = j.get("job_max_salary")
        sal_raw = f"USD {int(mn):,} - {int(mx):,}" if mn and mx else "Not listed"
        sal_disp = f"USD {int(mn)//1000}k-{int(mx)//1000}k" if mn and mx else "Not listed"
        site = "linkedin" if "linkedin" in (j.get("job_apply_link") or "").lower() else "indeed"
        results.append({
            "title":       j.get("job_title", ""),
            "company":     j.get("employer_name", ""),
            "location":    f"{j.get('job_city','')}, {j.get('job_state','')}".strip(", "),
            "job_url":     j.get("job_apply_link") or j.get("job_google_link", ""),
            "description": j.get("job_description", "")[:1500],
            "salary_raw":  sal_raw,
            "salary_display": sal_disp,
            "is_remote":   j.get("job_is_remote", False),
            "work_type":   "Remote" if j.get("job_is_remote") else "In-Office",
            "site":        site,
        })
    return results


@app.route("/api/search-jobs", methods=["POST"])
def search_jobs_api():
    import urllib.parse
    data = request.get_json()
    profile  = data.get("profile", {})
    location = data.get("location", "").strip()
    position = data.get("position", "").strip()
    salary   = data.get("salary", "").strip()

    search_term = position or profile.get("current_title", "Software Engineer")

    # ΓöÇΓöÇ Try JSearch (real LinkedIn/Indeed listings) first ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")
    if rapidapi_key:
        try:
            jobs_raw = jsearch_jobs(search_term, location, num=10)
            if jobs_raw:
                # Score & enrich with Claude
                client = make_client()
                skills_short = ", ".join((profile.get("top_skills") or [])[:5])
                for_scoring = [
                    {"index": i, "title": j["title"], "company": j["company"],
                     "description": j["description"][:300], "is_remote": j["is_remote"]}
                    for i, j in enumerate(jobs_raw)
                ]
                scored = claude_json(client, f"""Score these jobs for the candidate. Return ONLY a JSON array.
Each item: {{"index":<n>,"score":<6-10>,"work_type":"Remote|Hybrid|In-Office","role_summary":"1 sentence","key_qualifications":["X","X","X"]}}
Candidate: {profile.get("current_title","Engineer")}, skills: {skills_short}
Jobs: {json.dumps(for_scoring)}""", max_tokens=1500)

                if isinstance(scored, list):
                    results = []
                    for s in scored:
                        idx = s.get("index", -1)
                        if 0 <= idx < len(jobs_raw):
                            results.append({**jobs_raw[idx], **s})
                    results.sort(key=lambda x: x.get("score", 0), reverse=True)
                    return jsonify({"jobs": results[:5]})
        except Exception:
            pass  # Fall through to Claude fallback

    # ΓöÇΓöÇ Fallback: Claude-generated jobs ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    try:
        client = make_client()
        skills_short = ", ".join((profile.get("top_skills") or [])[:5])
        jobs = claude_json(client, f"""Return ONLY a valid JSON array of exactly 5 job postings. No explanation, no markdown, start with [ end with ].

Candidate: {profile.get("current_title","Engineer")}, skills: {skills_short}, {profile.get("years_experience","5")} yrs exp
Role: {search_term} | Location: {location} | Salary: {salary or "open"}

Each item must have these fields with SHORT values (keep description under 20 words, role_summary under 15 words):
{{"title":"X","company":"X","location":"X","job_url":"","description":"X","salary_raw":"USD 90,000 - 120,000","is_remote":false,"site":"linkedin","score":8,"work_type":"Remote","salary_display":"USD 90k-120k","role_summary":"X","key_qualifications":["X","X","X"]}}

Use real companies. Mix Remote/Hybrid/In-Office. Scores 6-10 desc.""", max_tokens=4000)
    except Exception as e:
        return jsonify({"error": f"Job search failed: {str(e)}"}), 500

    if isinstance(jobs, dict):
        for key in ("jobs", "results", "job_listings", "postings"):
            if isinstance(jobs.get(key), list):
                jobs = jobs[key]
                break

    if not isinstance(jobs, list) or not jobs:
        return jsonify({"error": "No jobs found. Try a different location or position."}), 404

    return jsonify({"jobs": jobs[:5]})


@app.route("/api/tailor-resume", methods=["POST"])
def tailor_resume_api():
    data        = request.get_json()
    resume_text = data.get("resume_text", "")
    profile     = data.get("profile", {})
    jobs        = data.get("selected_jobs", [])

    try:
        client = make_client()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []

    for job in jobs:
        try:
            tailored = claude_json(client, f"""You are an expert resume writer. Tailor this resume for the job below.
Return ONLY valid JSON ΓÇö no markdown, no explanation outside JSON.

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
