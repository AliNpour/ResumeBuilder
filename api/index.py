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
  "summary": "2-3 sentence professional summary",
  "education": [{{"degree": "Diploma, Computer Systems", "school": "Lester B. Pearson", "dates": "2019-2021", "details": ""}}],
  "certifications": ["AWS Solutions Architect (2025)", "CCNA (2020)"],
  "languages": ["English (Advanced)", "Farsi (Native)"]
}}

Copy education, certifications, and languages EXACTLY as written in the resume ΓÇö do not paraphrase or omit any.

Resume:
{resume_text[:5000]}""", max_tokens=1200)
    except Exception as e:
        return jsonify({"error": f"Failed to analyze resume: {str(e)}"}), 500

    return jsonify({"profile": profile, "resume_text": resume_text})


def jsearch_jobs(query, location, num=5):
    """Fetch real job listings from JSearch (RapidAPI) ΓÇö returns LinkedIn & Indeed URLs."""
    import urllib.request
    import urllib.parse
    import re
    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")
    if not rapidapi_key:
        raise RuntimeError("RAPIDAPI_KEY not set")

    # Strip special chars that confuse JSearch (slashes, parentheses, etc.)
    clean_query = re.sub(r'[/\\|()]', ' ', query)
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
    # Use only city name for broader location match
    clean_location = location.split(',')[0].strip()
    q = urllib.parse.quote(f"{clean_query} {clean_location}")
    url = f"https://jsearch.p.rapidapi.com/search?query={q}&num_pages=1&results_per_page={num}"
    print(f"[JSearch] query string: {clean_query!r} in {clean_location!r}", flush=True)
    req = urllib.request.Request(url, headers={
        "X-RapidAPI-Key":  rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read())

    status = raw.get("status", "")
    data_count = len(raw.get("data", []))
    print(f"[JSearch] status={status} data_count={data_count} query={query!r} location={location!r}", flush=True)
    if status not in ("OK", ""):
        raise RuntimeError(f"JSearch API error: {raw.get('message', status)}")

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
            jobs_raw = jsearch_jobs(search_term, location, num=5)
            real_jobs = jobs_raw[:]
            print(f"[JSearch] got {len(real_jobs)} usable jobs", flush=True)
            if len(real_jobs) >= 3:
                # Score & enrich with Claude
                client = make_client()
                skills_short = ", ".join((profile.get("top_skills") or [])[:5])
                for_scoring = [
                    {"index": i, "title": j["title"], "company": j["company"],
                     "description": j["description"][:300], "is_remote": j["is_remote"]}
                    for i, j in enumerate(jobs_raw)
                ]
                try:
                    scored = claude_json(client, f"""Score these jobs for the candidate. Return ONLY a JSON array.
Each item: {{"index":<n>,"score":<6-10>,"work_type":"Remote|Hybrid|In-Office","role_summary":"1 sentence","key_qualifications":["X","X","X"]}}
Candidate: {profile.get("current_title","Engineer")}, skills: {skills_short}
Jobs: {json.dumps(for_scoring)}""", max_tokens=1500)
                except Exception:
                    scored = []

                if isinstance(scored, list) and scored:
                    results = []
                    for s in scored:
                        idx = s.get("index", -1)
                        if 0 <= idx < len(jobs_raw):
                            results.append({**jobs_raw[idx], **s})
                    results.sort(key=lambda x: x.get("score", 0), reverse=True)
                    if results:
                        return jsonify({"jobs": results[:5]})

                # Scoring failed ΓÇö return raw JSearch results with default score
                for j in real_jobs:
                    j.update({"score": 8, "work_type": j.get("work_type","In-Office"),
                               "role_summary": j.get("description","")[:80],
                               "key_qualifications": []})
                return jsonify({"jobs": real_jobs[:5]})
        except Exception as jsearch_err:
            print(f"[JSearch error] {type(jsearch_err).__name__}: {jsearch_err}", flush=True)
            real_jobs = []
    else:
        print("[JSearch] RAPIDAPI_KEY not set ΓÇö using Claude fallback", flush=True)
        real_jobs = []

    # ΓöÇΓöÇ Claude jobs (full fallback, or top-up if JSearch returned < 3) ΓöÇΓöÇΓöÇΓöÇ
    need = 5 - len(real_jobs)
    print(f"[Claude] generating {need} jobs to supplement {len(real_jobs)} real ones", flush=True)
    try:
        client = make_client()
        skills_short = ", ".join((profile.get("top_skills") or [])[:5])
        jobs = claude_json(client, f"""Output ONLY a JSON array of EXACTLY {need} objects. No prose, no markdown. Start with [ end with ].
Each object: {{"title":"","company":"","location":"","job_url":"","description":"1 sentence","salary_raw":"USD 80,000 - 110,000","is_remote":false,"site":"linkedin","score":8,"work_type":"Hybrid","salary_display":"USD 80k-110k","role_summary":"1 sentence","key_qualifications":["skill1","skill2","skill3"]}}
Role: {search_term} in {location}. Candidate: {profile.get("current_title","Engineer")}, skills: {skills_short}.
Use real company names. job_url must be empty string. Generate {need} now:""", max_tokens=1500)
    except Exception as e:
        return jsonify({"error": f"Job search failed: {str(e)}"}), 500

    if isinstance(jobs, dict):
        for key in ("jobs", "results", "job_listings", "postings"):
            if isinstance(jobs.get(key), list):
                jobs = jobs[key]
                break

    if not isinstance(jobs, list):
        jobs = []

    combined = real_jobs + jobs
    if not combined:
        return jsonify({"error": "No jobs found. Try a different location or position."}), 404

    print(f"[Search] returning {len(combined[:5])} jobs ({len(real_jobs)} real + {len(jobs)} generated)", flush=True)
    return jsonify({"jobs": combined[:5]})


@app.route("/api/tailor-resume", methods=["POST"])
def tailor_resume_api():
    data        = request.get_json()
    resume_text = data.get("resume_text", "")
    profile     = data.get("profile", {})
    jobs        = data.get("selected_jobs", [])
    # These are locked fields ΓÇö extracted once at parse time, never re-generated
    locked_education      = profile.get("education", [])
    locked_certifications = profile.get("certifications", [])
    locked_languages      = profile.get("languages", [])

    try:
        client = make_client()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []

    for job in jobs:
        try:
            tailored = claude_json(client, f"""Tailor this resume for the job below. Return ONLY valid JSON, no markdown.

Schema (education/certifications/languages injected separately ΓÇö do NOT include them):
{{"name":"","email":"","phone":"","location":"","linkedin":"","summary":"","skills":[],"experience":[{{"title":"","company":"","dates":"","bullets":[]}}],"changes_made":["change 1","change 2","change 3"]}}

STRICT RULES ΓÇö violating any is a critical error:
1. Copy name, email, phone, location, linkedin CHARACTER-FOR-CHARACTER from the resume. Zero changes.
2. NEVER add a skill, tool, technology, company, date, title, certification, or achievement that does not appear in the original resume. If it is not there, do not include it.
3. NEVER remove any experience entry. All jobs must remain, same company names and dates.
4. Skills: reorder so the most job-relevant ones appear first. Do not add new ones. Do not remove any.
5. Bullets: you MAY use stronger action verbs and slightly sharper phrasing ΓÇö but only to express what is already stated. Never introduce a new fact.
6. Summary: highlight the candidate's most relevant real experience for this specific role. Do not claim anything not supported by the resume.
7. changes_made: list only the structural/ordering/phrasing changes you actually made (3-5 items).

Resume:
{resume_text[:4000]}

Job: {job.get("title","")} at {job.get("company","")}
{job.get("description","")[:800]}""", max_tokens=2500)

            # Inject locked fields directly ΓÇö never re-generated by Claude
            tailored["education"]      = locked_education
            tailored["certifications"] = locked_certifications
            tailored["languages"]      = locked_languages
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


@app.route("/api/fetch-job", methods=["POST"])
def fetch_job_api():
    import urllib.request
    import urllib.error
    import html as _html
    import re as _re

    data = request.get_json()
    url  = (data.get("url") or "").strip()
    if not url or not url.startswith("http"):
        return jsonify({"error": "Please provide a valid job URL starting with http"}), 400

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ResumeBot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return jsonify({"error": f"Could not fetch that URL: {str(e)}"}), 400

    # Strip scripts/styles/head then all tags
    text = _re.sub(r'(?is)<(script|style|head)[^>]*>.*?</\1>', ' ', raw_html)
    text = _re.sub(r'<[^>]+>', ' ', text)
    text = _html.unescape(text)
    text = _re.sub(r'[ \t]+', ' ', text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if len(text) < 100:
        return jsonify({"error": "Could not extract readable text from that page. Try copying the job description manually."}), 400

    try:
        client = make_client()
        meta = claude_json(client, f"""From this job posting text extract the following as JSON. Return ONLY JSON:
{{"title":"Job title","company":"Company name","description":"Full job description including responsibilities and requirements, max 1500 chars"}}

Job page text (first 4000 chars):
{text[:4000]}""", max_tokens=800)
    except Exception:
        meta = {"title": "", "company": "", "description": text[:1500]}

    return jsonify({
        "title":       meta.get("title", ""),
        "company":     meta.get("company", ""),
        "description": meta.get("description", text[:1500]),
    })


@app.route("/api/generate-docx", methods=["POST"])
def generate_docx_api():
    data        = request.get_json()
    resume_data = data.get("resume_data", {})
    company     = data.get("company", "tailored").lower().replace(" ", "_")

    try:
        from generate_pdf import build_docx_bytes
        docx_bytes = build_docx_bytes(resume_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(docx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"resume_{company}.docx",
    )


@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf_api():
    data        = request.get_json()
    resume_data = data.get("resume_data", {})
    company     = data.get("company", "tailored").lower().replace(" ", "_")

    try:
        from generate_pdf import build_pdf_bytes
        pdf_bytes = build_pdf_bytes(resume_data)
    except Exception as e:
        import traceback
        print(f"[PDF error] {traceback.format_exc()}", flush=True)
        return jsonify({"error": str(e)}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resume_{company}.pdf",
    )
