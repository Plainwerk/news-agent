'use strict';

// ── Spectrum ──────────────────────────────────────────────────────
const SPECTRUM_ORDER  = ['links', 'mitte-links', 'mitte', 'mitte-rechts', 'rechts'];
const SPECTRUM_COLORS = {
  'links':        '#e63946',
  'mitte-links':  '#f4845f',
  'mitte':        '#adb5bd',
  'mitte-rechts': '#5b9bd5',
  'rechts':       '#1a3a5c',
};
const SPEC_CSS = {
  'links':        'spec-links',
  'mitte-links':  'spec-mitte-links',
  'mitte':        'spec-mitte',
  'mitte-rechts': 'spec-mitte-rechts',
  'rechts':       'spec-rechts',
  'öRR':          'spec-oerr',
  'Agentur':      'spec-agentur',
};

// ── Category keywords (client-side filter) ────────────────────────
const CATEGORY_KEYWORDS = {
  'Politik':      ['trump', 'putin', 'ukraine', 'merz', 'bundesregierung', 'iran',
                   'nato', 'koalition', 'bundestag', 'krieg', 'kanzler', 'außen',
                   'bundeswehr', 'rede', 'wahl', 'frieden', 'minister', 'militär',
                   'diplomat', 'präsident', 'kongress', 'charles', 'scholz', 'habeck'],
  'Wirtschaft':   ['inflation', 'fed', 'leitzins', 'börse', 'aktie', 'wirtschaft',
                   'haushalt', 'aldi', 'porsche', 'unicredit', 'notenbank', 'opec',
                   'öl', 'gewinn', 'umsatz', 'dax', 'euro', 'ezb', 'handels',
                   'bank', 'verbraucherpreis', 'invest', 'finanz', 'markt'],
  'Gesellschaft': ['krankenhaus', 'krankenversicherung', 'künstliche intelligenz',
                   'meta', 'facebook', 'instagram', 'musik', 'film', 'gericht',
                   'klima', 'gesundheit', 'bildung', 'jugend', 'ki ', ' ki-',
                   'technologie', 'gaming', 'social media', 'wal', 'tier'],
};

// ── State ─────────────────────────────────────────────────────────
let allTopics      = [];
let activeCategory = 'Alle';
let activeDate     = '';
const loadedIds    = new Set();

// ── Utilities ─────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function truncate(text, max = 220) {
  if (!text || text.length <= max) return text || '';
  const cut = text.lastIndexOf('. ', max);
  return cut > 0 ? text.slice(0, cut + 1) : text.slice(0, max) + '…';
}

async function apiFetch(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function show(id) { const el = document.getElementById(id); if (el) el.style.display = ''; }
function hide(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }

// ── Spectrum bar ──────────────────────────────────────────────────
function spectrumBar(labels, height, showAxis) {
  const present = new Set(labels);

  const segs = SPECTRUM_ORDER.map(label => {
    const color = present.has(label) ? SPECTRUM_COLORS[label] : 'var(--seg-off)';
    return `<div class="spectrum-seg" style="height:${height}px;background:${color}" title="${esc(label)}"></div>`;
  }).join('');

  const extras = ['öRR', 'Agentur'].filter(l => present.has(l));
  const extraHtml = extras.length
    ? `<div class="spec-extras">${extras.map(l =>
        `<div class="spec-dot spec-dot-${l === 'öRR' ? 'oerr' : 'agentur'}" title="${esc(l)}"></div>`
      ).join('')}</div>`
    : '';

  const axis = showAxis
    ? `<div class="spectrum-axis">
         <span class="spectrum-axis-label">← Links</span>
         ${extraHtml}
         <span class="spectrum-axis-label">Rechts →</span>
       </div>`
    : '';

  return `<div class="spectrum-bar-wrap">
    <div class="spectrum-bar" style="border-radius:${height / 2}px">${segs}</div>
    ${axis}
  </div>`;
}

function specBadge(label) {
  return `<span class="spec-badge ${SPEC_CSS[label] || 'spec-agentur'}">${esc(label)}</span>`;
}

// ── Category filter ───────────────────────────────────────────────
function matchesCategory(topic) {
  if (activeCategory === 'Alle') return true;
  const kws = CATEGORY_KEYWORDS[activeCategory] || [];
  const lbl = topic.label.toLowerCase();
  return kws.some(kw => lbl.includes(kw));
}

// ── Hero ──────────────────────────────────────────────────────────
function renderHero(topic) {
  if (!topic) { hide('hero-section'); return; }
  show('hero-section');

  document.getElementById('hero-section').innerHTML = `
    <div class="hero-card">
      <div class="hero-eyebrow">Top-Thema</div>
      <h1 class="hero-title">${esc(topic.label)}</h1>
      ${spectrumBar(topic.spectrum_labels, 16, true)}
      ${topic.faktenkern
        ? `<p class="hero-faktenkern">${esc(truncate(topic.faktenkern, 240))}</p>`
        : ''}
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <span class="hero-meta">
          ${topic.article_count} Artikel &nbsp;·&nbsp; ${topic.spectrum_score} Spektrum-Ebenen
          ${topic.framing_count > 0 ? `&nbsp;·&nbsp; <span class="has-framing">${topic.framing_count} Framings</span>` : ''}
        </span>
        <button class="btn-hero-detail" id="btn-${topic.id}"
                onclick="toggleDetail(${topic.id})">
          Details &amp; Framing ↓
        </button>
      </div>
      <div class="collapse" id="detail-${topic.id}">
        <div class="detail-body" id="detail-body-${topic.id}">
          <div class="spinner-mini">Lädt…</div>
        </div>
      </div>
    </div>`;
}

// ── Card ──────────────────────────────────────────────────────────
function buildCard(topic) {
  const col = document.createElement('div');
  col.className = 'col-12 col-md-6 col-xl-4';
  col.innerHTML = `
    <div class="topic-card h-100">
      <div class="card-inner">
        <div class="card-title-text">${esc(topic.label)}</div>
        ${spectrumBar(topic.spectrum_labels, 8, false)}
        <div class="card-meta">
          ${topic.article_count} Artikel
          ${topic.framing_count > 0
            ? `<span class="has-framing ms-2">● ${topic.framing_count} Framings</span>`
            : ''}
        </div>
      </div>
      <button class="toggle-btn" id="btn-${topic.id}"
              onclick="toggleDetail(${topic.id})">
        Details anzeigen ↓
      </button>
      <div class="collapse" id="detail-${topic.id}">
        <div class="detail-body" id="detail-body-${topic.id}">
          <div class="spinner-mini">Lädt…</div>
        </div>
      </div>
    </div>`;
  return col;
}

// ── Toggle detail ─────────────────────────────────────────────────
function toggleDetail(id) {
  const collapse = document.getElementById(`detail-${id}`);
  const btn      = document.getElementById(`btn-${id}`);
  const bsc      = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });
  const isHero   = !!collapse.closest('.hero-card');

  if (collapse.classList.contains('show')) {
    bsc.hide();
    if (btn) btn.innerHTML = isHero ? 'Details &amp; Framing ↓' : 'Details anzeigen ↓';
    return;
  }

  bsc.show();
  if (btn) btn.innerHTML = isHero ? 'Details &amp; Framing ↑' : 'Details ausblenden ↑';

  if (loadedIds.has(id)) return;
  loadedIds.add(id);

  apiFetch(`/api/topics/${id}/framing`)
    .then(data => renderDetail(id, data))
    .catch(e => {
      const body = document.getElementById(`detail-body-${id}`);
      if (body) body.innerHTML = `<p class="text-danger small">Fehler: ${esc(e.message)}</p>`;
    });
}

// ── Detail content ────────────────────────────────────────────────
function renderDetail(id, data) {
  const body = document.getElementById(`detail-body-${id}`);
  if (!body) return;

  let html = '';

  // Faktenkern
  html += `<div class="detail-section-label">Faktenkern</div>
    <div class="faktenkern-box">${esc(data.faktenkern || '(keine Analyse verfügbar)')}</div>`;

  // Framing table
  if (data.framing_sources?.length) {
    html += `<div class="detail-section-label">Framing nach Quelle</div>
      <div class="framing-table">`;
    for (const fs of data.framing_sources) {
      html += `<div class="framing-row">
        <div class="framing-cell framing-source">
          ${specBadge(fs.spectrum_label)}
          <span>${esc(fs.quelle)}</span>
        </div>
        <div class="framing-cell">${esc(fs.framing)}</div>
      </div>`;
    }
    html += `</div>`;
  }

  // Wortwahl
  if (data.wortwahl_diffs?.length) {
    html += `<div class="detail-section-label mt-3">Wortwahl</div>`;
    for (const wd of data.wortwahl_diffs) {
      html += `<div class="wort-konzept">${esc(wd.konzept)}</div>
        <div class="wort-grid">`;
      for (const v of wd.varianten) {
        html += `<div class="wort-item">
          <span class="wort-source">${esc(v.quelle)}</span>
          <span class="wort-term"> „${esc(v.bezeichnung)}"</span>
        </div>`;
      }
      html += `</div>`;
    }
  }

  // Source chips (one per source, deduped)
  if (data.articles?.length) {
    const seen = new Set();
    const chips = data.articles
      .filter(a => a.url && !seen.has(a.source_name) && seen.add(a.source_name))
      .map(a => `<a href="${esc(a.url)}" target="_blank" rel="noopener" class="source-chip">${esc(a.source_name)} ↗</a>`)
      .join('');
    if (chips) html += `<div class="source-chips">${chips}</div>`;
  }

  body.innerHTML = html;
}

// ── Render topics ─────────────────────────────────────────────────
function renderTopics() {
  const filtered = allTopics.filter(matchesCategory);
  const grid     = document.getElementById('topics-grid');
  grid.innerHTML  = '';
  loadedIds.clear();

  if (!filtered.length) {
    hide('hero-section');
    document.getElementById('stats-bar').textContent = '';
    grid.innerHTML = '<div class="col"><p class="text-muted text-center py-5">Keine Themen für diese Auswahl.</p></div>';
    return;
  }

  const [hero, ...rest] = filtered;
  renderHero(hero);
  for (const t of rest) grid.appendChild(buildCard(t));

  const withFr = filtered.filter(t => t.framing_count > 0).length;
  document.getElementById('stats-bar').textContent =
    `${filtered.length} Themen · ${withFr} mit Framing-Analyse`;
}

// ── Load from API ─────────────────────────────────────────────────
async function loadTopics() {
  hide('hero-section');
  document.getElementById('topics-grid').innerHTML = '';
  document.getElementById('stats-bar').textContent = '';
  show('spinner');

  const url = activeDate
    ? `/api/topics?date=${encodeURIComponent(activeDate)}`
    : '/api/topics/today';

  try {
    allTopics = await apiFetch(url);
    hide('spinner');
    renderTopics();
  } catch (e) {
    hide('spinner');
    document.getElementById('topics-grid').innerHTML =
      `<div class="col"><p class="text-danger py-4">Fehler: ${esc(e.message)}</p></div>`;
  }
}

// ── Date dropdown ─────────────────────────────────────────────────
async function loadDates() {
  try {
    const dates = await apiFetch('/api/dates');
    const sel   = document.getElementById('filter-date');
    for (const d of dates) {
      const opt = document.createElement('option');
      opt.value = d; opt.textContent = d;
      sel.appendChild(opt);
    }
  } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────
document.getElementById('filter-date').addEventListener('change', e => {
  activeDate = e.target.value;
  loadTopics();
});

document.querySelectorAll('.pill').forEach(pill => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    activeCategory = pill.dataset.cat;
    renderTopics();
  });
});

loadDates();
loadTopics();
