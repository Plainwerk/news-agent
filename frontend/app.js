'use strict';

const SPECTRUM_CLASS = {
  'links':        'spec-links',
  'mitte-links':  'spec-mitte-links',
  'mitte':        'spec-mitte',
  'mitte-rechts': 'spec-mitte-rechts',
  'rechts':       'spec-rechts',
  'öRR':          'spec-oerr',
  'Agentur':      'spec-agentur',
};

// ── Spectrum badge ────────────────────────────────────────────────
function specBadge(label) {
  const cls = SPECTRUM_CLASS[label] || 'spec-agentur';
  return `<span class="spec-badge ${cls}">${escHtml(label)}</span>`;
}

function specBar(labels) {
  return labels.map(specBadge).join(' ');
}

// ── DOM helpers ───────────────────────────────────────────────────
function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function show(id)  { document.getElementById(id).style.display = ''; }
function hide(id)  { document.getElementById(id).style.display = 'none'; }

// ── API ───────────────────────────────────────────────────────────
async function apiFetch(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Card rendering ────────────────────────────────────────────────
function buildCard(topic) {
  const colDiv = document.createElement('div');
  colDiv.className = 'col-12 col-md-6 col-xl-4';
  colDiv.id = `col-${topic.id}`;

  const hasAnalysis = topic.framing_count > 0;
  const analysisNote = hasAnalysis
    ? `<span class="text-success">● ${topic.framing_count} Framing${topic.framing_count > 1 ? 's' : ''}</span>`
    : `<span class="text-muted">○ keine Analyse</span>`;

  colDiv.innerHTML = `
    <div class="card h-100 topic-card">
      <div class="card-body pb-2">
        <h6 class="card-title fw-semibold mb-2">${escHtml(topic.label)}</h6>
        <div class="spectrum-bar d-flex gap-1 flex-wrap mb-2">
          ${specBar(topic.spectrum_labels)}
        </div>
        <div class="d-flex justify-content-between align-items-center">
          <small class="text-muted">${topic.article_count} Artikel</small>
          <small>${analysisNote}</small>
        </div>
      </div>
      <div class="card-footer bg-transparent border-0 pt-0 pb-2">
        <button class="btn btn-sm btn-outline-secondary w-100 toggle-btn"
                data-id="${topic.id}" data-loaded="0">
          Details ▼
        </button>
      </div>
      <div class="detail-section collapse" id="detail-${topic.id}">
        <div class="card-body pt-3" id="detail-body-${topic.id}">
          <div class="text-muted text-center py-3">
            <div class="spinner-border spinner-border-sm"></div>
          </div>
        </div>
      </div>
    </div>`;

  colDiv.querySelector('.toggle-btn').addEventListener('click', () => toggleDetail(topic.id));
  return colDiv;
}

async function toggleDetail(id) {
  const btn     = document.querySelector(`[data-id="${id}"]`);
  const collapse = document.getElementById(`detail-${id}`);
  const bsCollapse = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });

  if (collapse.classList.contains('show')) {
    bsCollapse.hide();
    btn.textContent = 'Details ▼';
    return;
  }

  bsCollapse.show();
  btn.textContent = 'Details ▲';

  if (btn.dataset.loaded === '1') return;
  btn.dataset.loaded = '1';

  try {
    const data = await apiFetch(`/api/topics/${id}/framing`);
    renderDetail(id, data);
  } catch (e) {
    document.getElementById(`detail-body-${id}`).innerHTML =
      `<p class="text-danger small">Fehler beim Laden: ${escHtml(e.message)}</p>`;
  }
}

function renderDetail(id, data) {
  const body = document.getElementById(`detail-body-${id}`);
  let html = '';

  // Faktenkern
  html += `<h6 class="fw-bold text-dark mb-1">Faktenkern</h6>`;
  html += `<p class="faktenkern-text">${escHtml(data.faktenkern || '(keine Analyse verfügbar)')}</p>`;

  // Framing-Unterschiede
  if (data.framing_sources && data.framing_sources.length) {
    html += `<h6 class="fw-bold text-dark mb-1 mt-3">Framing</h6>`;
    html += `<div>`;
    for (const fs of data.framing_sources) {
      html += `<div class="framing-item d-flex gap-2">
        <span class="framing-quelle">${specBadge(fs.spectrum_label)} ${escHtml(fs.quelle)}</span>
        <span>${escHtml(fs.framing)}</span>
      </div>`;
    }
    html += `</div>`;
  }

  // Wortwahl-Diff
  if (data.wortwahl_diffs && data.wortwahl_diffs.length) {
    html += `<h6 class="fw-bold text-dark mb-1 mt-3">Wortwahl</h6>`;
    for (const wd of data.wortwahl_diffs) {
      html += `<div class="wort-konzept">${escHtml(wd.konzept)}</div>`;
      for (const v of wd.varianten) {
        html += `<div class="wort-var">
          <span class="wort-quelle">${escHtml(v.quelle)}</span>
          <span class="text-secondary">„${escHtml(v.bezeichnung)}"</span>
        </div>`;
      }
    }
  }

  // Quellenlinks
  if (data.articles && data.articles.length) {
    html += `<div class="article-links mt-3 pt-2 border-top">`;
    for (const a of data.articles) {
      if (a.url) {
        html += `<a href="${escHtml(a.url)}" target="_blank" rel="noopener">${escHtml(a.source_name)}</a>`;
      }
    }
    html += `</div>`;
  }

  body.innerHTML = html;
}

// ── Main load ─────────────────────────────────────────────────────
async function loadTopics() {
  const date  = document.getElementById('filter-date').value;
  const label = document.getElementById('filter-label').value;

  show('spinner');
  hide('no-results');
  document.getElementById('topics-grid').innerHTML = '';

  let url = '/api/topics/today';
  const params = new URLSearchParams();
  if (date || label) {
    url = '/api/topics';
    if (date)  params.set('date',  date);
    if (label) params.set('label', label);
  }
  const fullUrl = params.toString() ? `${url}?${params}` : url;

  try {
    const topics = await apiFetch(fullUrl);
    hide('spinner');

    if (!topics.length) {
      show('no-results');
      document.getElementById('stats-bar').textContent = '';
      return;
    }

    const grid = document.getElementById('topics-grid');
    for (const t of topics) grid.appendChild(buildCard(t));

    const withAnalysis = topics.filter(t => t.framing_count > 0).length;
    document.getElementById('stats-bar').textContent =
      `${topics.length} Themen · ${withAnalysis} mit Framing-Analyse`;
  } catch (e) {
    hide('spinner');
    document.getElementById('topics-grid').innerHTML =
      `<div class="col"><p class="text-danger">Fehler: ${escHtml(e.message)}</p></div>`;
  }
}

async function loadDates() {
  try {
    const dates = await apiFetch('/api/dates');
    const sel = document.getElementById('filter-date');
    for (const d of dates) {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      sel.appendChild(opt);
    }
  } catch (_) {}
}

// ── Bootstrap ─────────────────────────────────────────────────────
document.getElementById('filter-date').addEventListener('change', loadTopics);
document.getElementById('filter-label').addEventListener('change', loadTopics);

loadDates();
loadTopics();
