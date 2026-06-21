/* ── State ────────────────────────────────────────────────────────────── */
const state = {
  apiKey:       localStorage.getItem('rb_api_key') || '',
  resumeText:   '',
  profile:      null,
  jobs:         [],
  selectedJobs: [],
  tailored:     [],
  pdfFiles:     [],
  currentTab:   0,
};

/* ── Utilities ───────────────────────────────────────────────────────── */
const $  = (s, ctx = document) => ctx.querySelector(s);
const $$ = (s, ctx = document) => [...ctx.querySelectorAll(s)];

function showToast(msg, type = 'info') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => t.classList.remove('show'), 3500);
}

function showPanel(id) {
  $$('.panel').forEach(p => p.classList.remove('active'));
  $(`#panel-${id}`).classList.add('active');
  updateSteps(id);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setStep(n) {
  $$('.step-item').forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i + 1 < n)  el.classList.add('done');
    if (i + 1 === n) el.classList.add('active');
  });
  $$('.step-line').forEach((el, i) => {
    el.classList.toggle('done', i + 1 < n);
  });
}

function updateSteps(panel) {
  const map = { upload: 1, loading: 2, jobs: 3, tailoring: 4, review: 5, done: 5 };
  setStep(map[panel] || 1);
}

/* ── API key modal ───────────────────────────────────────────────────── */
function openApiModal() { $('#api-modal').classList.add('open'); }
function closeApiModal() { $('#api-modal').classList.remove('open'); }

function saveApiKey() {
  const key = $('#api-key-input').value.trim();
  if (!key.startsWith('sk-')) { showToast('Invalid API key format', 'error'); return; }
  state.apiKey = key;
  localStorage.setItem('rb_api_key', key);
  updateApiBtn();
  closeApiModal();
  showToast('API key saved', 'success');
}

function updateApiBtn() {
  const btn = $('#api-btn');
  if (state.apiKey) {
    btn.classList.add('connected');
    btn.innerHTML = `<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> API Connected`;
  } else {
    btn.classList.remove('connected');
    btn.innerHTML = `<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg> Set API Key`;
  }
}

/* ── File upload / drag-drop ─────────────────────────────────────────── */
function initDropzone() {
  const zone  = $('#dropzone');
  const input = $('#file-input');
  const name  = $('#file-name');

  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });

  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(input.files[0]);
  });

  function handleFile(file) {
    const allowed = ['.pdf', '.docx', '.doc', '.txt'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) { showToast('Please upload a PDF, DOCX, or TXT file', 'error'); return; }
    name.textContent = '📎 ' + file.name;
    $('#resume-textarea').value = '';
    state._file = file;
  }
}

/* ── Step 1: Upload & Analyze ────────────────────────────────────────── */
async function analyzeResume() {


  const location = $('#location').value.trim();
  const position = $('#position').value.trim();
  const salary   = $('#salary').value.trim();

  if (!location) { showToast('Please enter a job location', 'error'); return; }
  if (!position) { showToast('Please enter the position you want', 'error'); return; }

  const textarea = $('#resume-textarea').value.trim();
  if (!textarea && !state._file) { showToast('Please upload or paste your resume', 'error'); return; }

  // Show loading
  showPanel('loading');
  setLoadingStep(0);

  const fd = new FormData();
  fd.append('api_key', state.apiKey);
  if (state._file) {
    fd.append('file', state._file);
  } else {
    fd.append('resume_text', textarea);
  }

  try {
    setLoadingStep(1);
    const res  = await fetch('/api/parse-resume', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to parse resume');

    state.resumeText = data.resume_text;
    state.profile    = data.profile;
    state._location  = location;
    state._position  = position;
    state._salary    = salary;

    setLoadingStep(2);
    await searchJobs();
  } catch (err) {
    showPanel('upload');
    showToast(err.message, 'error');
  }
}

async function searchJobs() {
  try {
    setLoadingStep(2);
    const res  = await fetch('/api/search-jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key:     state.apiKey,
        profile:     state.profile,
        resume_text: state.resumeText,
        location:    state._location,
        position:    state._position,
        salary:      state._salary,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Job search failed');

    state.jobs = data.jobs;
    setLoadingStep(3);

    setTimeout(() => {
      renderJobs();
      showPanel('jobs');
    }, 600);
  } catch (err) {
    showPanel('upload');
    showToast(err.message, 'error');
  }
}

/* ── Loading steps ───────────────────────────────────────────────────── */
const LOADING_STEPS = [
  'Reading your resume…',
  'Extracting your profile with AI…',
  'Searching LinkedIn & Indeed…',
  'Scoring job relevance…',
];

function setLoadingStep(i) {
  $$('.loading-step').forEach((el, idx) => {
    el.classList.remove('active', 'done');
    if (idx < i)  el.classList.add('done');
    if (idx === i) el.classList.add('active');
  });
}

/* ── Step 3: Jobs ────────────────────────────────────────────────────── */
function renderJobs() {
  const grid = $('#jobs-grid');
  grid.innerHTML = '';
  $('#jobs-found-count').textContent = `${state.jobs.length} jobs found`;

  state.jobs.forEach((job, idx) => {
    const worktypeColor = job.work_type === 'Remote' ? 'teal' : job.work_type === 'Hybrid' ? 'purple' : 'sub';
    const initial = (job.company || 'J').charAt(0).toUpperCase();
    const source  = (job.site || 'job board').replace('linkedin', 'LinkedIn').replace('indeed', 'Indeed');

    const card = document.createElement('div');
    card.className = 'job-card';
    card.dataset.idx = idx;
    card.innerHTML = `
      <div class="job-header">
        <div class="job-logo">${initial}</div>
        <div class="job-title-block">
          <div class="job-title">${esc(job.title)}</div>
          <div class="job-company">${esc(job.company)}</div>
        </div>
        <div class="job-score">${job.score}/10</div>
      </div>
      <div class="job-tags">
        <span class="tag tag-location">📍 ${esc(job.location || state._location)}</span>
        <span class="tag tag-worktype">🏢 ${esc(job.work_type || 'In-Office')}</span>
        <span class="tag tag-salary">💰 ${esc(job.salary_display || job.salary_raw || 'Not listed')}</span>
        <span class="tag tag-source">${esc(source)}</span>
      </div>
      <p class="job-summary">${esc(job.role_summary || job.description?.substring(0, 180) || '')}</p>
      <ul class="job-quals">
        ${(job.key_qualifications || []).map(q => `<li>${esc(q)}</li>`).join('')}
      </ul>
      ${job.job_url ? `<a href="${esc(job.job_url)}" target="_blank" class="job-link">View posting ↗</a>` : ''}
    `;

    card.addEventListener('click', e => {
      if (e.target.tagName === 'A') return;
      card.classList.toggle('selected');
      const i = state.selectedJobs.indexOf(idx);
      if (i === -1) state.selectedJobs.push(idx);
      else          state.selectedJobs.splice(i, 1);
      updateSelectBar();
    });

    grid.appendChild(card);
  });

  updateSelectBar();
}

function updateSelectBar() {
  const n = state.selectedJobs.length;
  $('#select-count').textContent = n;
  $('#tailor-btn').disabled = n === 0;
}

function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Step 4: Tailor ──────────────────────────────────────────────────── */
async function tailorResumes() {
  const jobs = state.selectedJobs.map(i => state.jobs[i]);
  showPanel('tailoring');

  try {
    const res  = await fetch('/api/tailor-resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key:       state.apiKey,
        resume_text:   state.resumeText,
        profile:       state.profile,
        selected_jobs: jobs,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Tailoring failed');

    state.tailored = data.tailored_resumes;
    renderReview();
    showPanel('review');
  } catch (err) {
    showPanel('jobs');
    showToast(err.message, 'error');
  }
}

async function downloadPDF(resumeData, company) {
  try {
    const res = await fetch('/api/generate-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_data: resumeData, company }),
    });
    if (!res.ok) { showToast('PDF generation failed', 'error'); return; }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `resume_${company.toLowerCase().replace(/\s+/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast('Download failed: ' + err.message, 'error');
  }
}

/* ── Step 5: Review ──────────────────────────────────────────────────── */
function renderReview() {
  const tabs    = $('#review-tabs');
  const content = $('#review-content');

  tabs.innerHTML    = '';
  content.innerHTML = '';

  state.tailored.forEach((resume, i) => {
    // Tab button
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = `${resume.job_company || 'Job ' + (i+1)}`;
    btn.addEventListener('click', () => {
      $$('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      $$('.tab-pane').forEach(p => p.classList.add('hidden'));
      $(`#pane-${i}`).classList.remove('hidden');
    });
    tabs.appendChild(btn);

    // Pane content
    const pane = document.createElement('div');
    pane.className = 'tab-pane' + (i > 0 ? ' hidden' : '');
    pane.id = `pane-${i}`;

    // Changes list
    const changes = (resume.changes_made || []).map(c => `<li>${esc(c)}</li>`).join('');

    // Tailored resume preview
    const skills = (resume.skills || []).join(', ');
    const expHtml = (resume.experience || []).map(e =>
      `<div style="margin-bottom:.75rem">
        <strong>${esc(e.title)}</strong> @ ${esc(e.company)} <span style="color:var(--sub2)">${esc(e.dates)}</span>
        <ul style="margin:.25rem 0 0 1rem">${(e.bullets||[]).map(b=>`<li style="color:var(--sub);font-size:.82rem">${esc(b)}</li>`).join('')}</ul>
      </div>`
    ).join('');

    pane.innerHTML = `
      <div class="changes-list mb-2">
        <h3>✨ Changes Made</h3>
        <ul style="list-style:none;padding:0">${changes || '<li>Resume tailored for this role</li>'}</ul>
      </div>

      <div class="resume-review">
        <div class="resume-pane">
          <div class="pane-header original">📄 Original Resume</div>
          <div class="pane-body" style="white-space:pre-wrap;font-size:.8rem">${esc(state.resumeText.substring(0, 2000))}${state.resumeText.length > 2000 ? '\n…' : ''}</div>
        </div>
        <div class="resume-pane">
          <div class="pane-header tailored">✨ Tailored for ${esc(resume.job_title || 'this role')}</div>
          <div class="pane-body">
            <div style="font-size:1.1rem;font-weight:700;margin-bottom:.25rem">${esc(resume.name)}</div>
            <div style="color:var(--sub2);font-size:.8rem;margin-bottom:.75rem">${esc(resume.email)} · ${esc(resume.phone)}</div>
            <div style="margin-bottom:.75rem"><strong style="color:var(--blue);font-size:.8rem">SUMMARY</strong><br>${esc(resume.summary)}</div>
            <div style="margin-bottom:.75rem"><strong style="color:var(--blue);font-size:.8rem">SKILLS</strong><br><span style="font-size:.82rem">${esc(skills)}</span></div>
            <div><strong style="color:var(--blue);font-size:.8rem">EXPERIENCE</strong><br>${expHtml}</div>
          </div>
        </div>
      </div>

      <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center">
        <button class="btn btn-success" onclick="downloadPDF(state.tailored[${i}], '${esc(resume.job_company || 'resume')}')">
          ⬇ Download PDF Resume
        </button>
        ${resume.job_url
          ? `<a href="${esc(resume.job_url)}" target="_blank" class="btn btn-secondary">🔗 View Job Posting ↗</a>`
          : ''}
        <div style="margin-left:auto">
          <span class="tag tag-worktype">${esc(resume.work_type || '')}</span>
          <span class="tag tag-salary">${esc(resume.salary_display || '')}</span>
        </div>
      </div>
    `;

    content.appendChild(pane);
  });
}

/* ── Restart ─────────────────────────────────────────────────────────── */
function restart() {
  state.resumeText = '';
  state.profile    = null;
  state.jobs       = [];
  state.selectedJobs = [];
  state.tailored   = [];
  state.pdfFiles   = [];
  state._file      = null;
  $('#file-input').value   = '';
  $('#file-name').textContent = '';
  $('#resume-textarea').value = '';
  showPanel('upload');
}

/* ── Init ────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  updateApiBtn();
  if (state.apiKey) $('#api-key-input').value = state.apiKey;
  initDropzone();
  showPanel('upload');

  $('#api-btn').addEventListener('click', openApiModal);
  $('#modal-cancel').addEventListener('click', closeApiModal);
  $('#modal-save').addEventListener('click', saveApiKey);
  $('#api-modal').addEventListener('click', e => { if (e.target === $('#api-modal')) closeApiModal(); });

  $('#analyze-btn').addEventListener('click', analyzeResume);
  $('#tailor-btn').addEventListener('click', tailorResumes);
  $('#restart-btn').addEventListener('click', restart);

  // Allow Enter in API key field
  $('#api-key-input').addEventListener('keydown', e => { if (e.key === 'Enter') saveApiKey(); });
});
