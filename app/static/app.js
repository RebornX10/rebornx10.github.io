const $ = id => document.getElementById(id);
async function post(url, body) {
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                             body: JSON.stringify(body)});
  return r.json();
}

// --- theme ---
function applyTheme(t){
  document.documentElement.classList.toggle('light', t === 'light');
  $('theme').textContent = t === 'light' ? '☀️' : '🌙';
  const mc = document.getElementById('themeColor');   // keep the OS status bar in sync
  if (mc) mc.setAttribute('content', t === 'light' ? '#f5f7fb' : '#0f1117');
}
let theme = localStorage.getItem('theme') ||
  (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
applyTheme(theme);
$('theme').onclick = () => { theme = theme === 'light' ? 'dark' : 'light';
  localStorage.setItem('theme', theme); applyTheme(theme); };

// --- stopwatch + ETA + quips ---
const QUIPS = [
  "Summoning papers from the archives…",
  "Politely asking OpenAlex for everything…",
  "Teaching robots to read PDFs…",
  "Untangling author affiliations…",
  "Extracting wisdom, one page at a time…",
  "Dusting off the preprints…",
  "Convincing publishers to share…",
  "Counting references so you don't have to…",
  "Following the citation trail…",
  "Brewing coffee for the CPU…",
];
let facts = [];   // fun facts about the current topic, fetched from Wikipedia
let _watch = null, _quip = null, _t0 = 0, _lastMsg = '', _running = false;
const fmt = s => Math.floor(s/60) + ':' + String(Math.floor(s%60)).padStart(2,'0');

function showQuip(text){
  _lastMsg = text;
  $('quip').style.opacity = 0;
  setTimeout(() => { $('quip').textContent = text; $('quip').style.opacity = 1; }, 220);
}

// Pull a few topic facts from Wikipedia (CORS-enabled) to spice up the wait.
async function fetchFacts(topic){
  facts = [];
  if (!topic) return;
  try {
    const os = await (await fetch(
      'https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&format=json&origin=*&search='
      + encodeURIComponent(topic))).json();
    const title = os && os[1] && os[1][0];
    if (!title) return;
    const sum = await (await fetch(
      'https://en.wikipedia.org/api/rest_v1/page/summary/'
      + encodeURIComponent(title) + '?redirect=true')).json();
    facts = ((sum.extract || '').match(/[^.!?]+[.!?]+/g) || [])
      .map(s => '💡 ' + s.trim())
      .filter(s => s.length > 34 && s.length < 230)
      .slice(0, 6);
    if (_running && facts.length) showQuip(facts[0]);  // show a fact as soon as it's ready
  } catch (e) { facts = []; }
}

// Next message: random pick from quips + topic facts, no immediate repeat.
function nextMsg(){
  const pool = QUIPS.concat(facts);
  let m;
  do { m = pool[Math.floor(Math.random() * pool.length)]; } while (pool.length > 1 && m === _lastMsg);
  return (_lastMsg = m);
}

function startFun(topic){
  _t0 = Date.now();
  _running = true;
  $('fun').style.display = 'block';
  document.querySelector('.bounce').style.display = '';
  $('watch').textContent = '0:00'; $('eta').textContent = '';
  _lastMsg = QUIPS[0];
  $('quip').style.opacity = 1; $('quip').textContent = QUIPS[0];
  fetchFacts(topic);  // fills `facts`; shows one as soon as it's fetched
  _watch = setInterval(() => { $('watch').textContent = fmt((Date.now()-_t0)/1000); }, 250);
  _quip = setInterval(() => showQuip(nextMsg()), 3000);
}
function updateETA(p){
  const el = (Date.now()-_t0)/1000;
  if (p >= 5 && p < 100) $('eta').textContent = '~ ' + fmt(el*(100-p)/p) + ' remaining';
  else if (p < 5) $('eta').textContent = 'estimating…';
}
function stopFun(ok){
  _running = false;
  clearInterval(_watch); clearInterval(_quip);
  document.querySelector('.bounce').style.display = 'none';
  $('eta').textContent = '';
  $('quip').textContent = ok ? ('Finished in ' + $('watch').textContent + ' 🎉') : '';
}

// --- build ---
let _jobId = null;
$('go').onclick = async () => {
  const topic = $('topic').value.trim();
  if (!topic) { $('stage').textContent = 'Enter a topic first.'; return; }
  $('go').disabled = true; $('bar').style.width = '2%';
  $('stage').textContent = 'Starting…'; $('qa').classList.add('disabled');
  const {job_id, error} = await post('/build', {
    topic, date_from: $('from').value, date_to: $('to').value, n: +$('n').value,
    source: $('source').value });
  if (error || !job_id) { $('stage').textContent = error || 'Failed to start.';
                          $('go').disabled = false; return; }
  _jobId = job_id;
  $('cancel').style.display = ''; $('cancel').disabled = false; $('cancel').textContent = 'Cancel';
  // ask (on this click gesture) for permission to notify when the build finishes
  if ('Notification' in window && Notification.permission === 'default')
    Notification.requestPermission().catch(() => {});
  startFun(topic);
  connect(job_id);   // stream this build's status (+ metrics) over SSE
};

$('cancel').onclick = async () => {
  if (!_jobId) return;
  $('cancel').disabled = true; $('cancel').textContent = 'Cancelling…';
  try { await post('/cancel', { job: _jobId }); } catch (e) {}
};

// --- corpus browse panel (also used to resume a loaded corpus on page load) ---
let _corpusRows = [], _curKey = '';
async function loadCorpus(){
  let data;
  try { data = await (await fetch('/corpus')).json(); } catch (e) { return; }
  if (!data || !data.count) { $('corpus').style.display = 'none'; return; }
  _corpusRows = data.papers || [];
  _curKey = data.key || '';
  $('corpus').style.display = '';
  $('qa').classList.remove('disabled');           // a corpus is loaded -> enable Q&A
  $('corpusTitle').textContent = data.topic || 'Corpus';
  const note = data.count > data.shown ? `, showing first ${data.shown}` : '';
  $('corpusCount').textContent = `· ${data.count} papers · ${data.with_text} with full text${note}`;
  renderCorpus();
  loadCorpora();
}

// populate the "switch corpus" dropdown from previously built corpora
async function loadCorpora(){
  let data;
  try { data = await (await fetch('/corpora')).json(); } catch (e) { return; }
  const items = (data && data.items) || [];
  const sel = $('corpusSwitch');
  if (items.length < 2) { sel.style.display = 'none'; return; }
  sel.innerHTML = items.map(it =>
    `<option value="${it.key}">${esc((it.topic || 'corpus') + ' (' + it.count + ')')}</option>`).join('');
  sel.value = data.current || items[0].key;
  sel.style.display = '';
}
$('corpusSwitch').addEventListener('change', async () => {
  const key = $('corpusSwitch').value;
  try {
    const r = await (await fetch('/corpus/select', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) })).json();
    if (r && r.ok) {
      $('answer').style.display = 'none'; $('answer').innerHTML = '';
      $('sources').textContent = ''; $('astage').textContent = '';
      $('corpusFilter').value = '';
      loadCorpus();   // refresh table + counts for the newly selected corpus
    }
  } catch (e) {}
});
let _sortKey = '', _sortDir = -1;
function renderCorpus(){
  const f = ($('corpusFilter').value || '').trim().toLowerCase();
  const rows = _corpusRows.map((r, i) => ({ r, i }))
    .filter(({ r }) => !f || ((r.title || '') + ' ' + (r.journal || '')).toLowerCase().includes(f));
  if (_sortKey) {
    rows.sort((a, b) => {
      let x = a.r[_sortKey], y = b.r[_sortKey];
      if (typeof x === 'string' || typeof y === 'string') {
        x = (x || '').toString().toLowerCase(); y = (y || '').toString().toLowerCase();
        return x < y ? -_sortDir : x > y ? _sortDir : 0;
      }
      return ((x || 0) - (y || 0)) * _sortDir;
    });
  }
  $('corpusTable').querySelector('tbody').innerHTML = rows.map(({ r, i }) =>
    `<tr class="crow" data-i="${i}"><td>${esc(r.title)}</td>` +
    `<td class="muted">${esc(r.journal || '')}</td>` +
    `<td class="muted">${esc(r.date || '')}</td>` +
    `<td style="text-align:center">${r.cited_by || 0}</td>` +
    `<td style="text-align:center">${r.has_text ? '✓' : '·'}</td></tr>`).join('');
  $('corpusMore').textContent = rows.length ? '' : 'No matching papers.';
}
// click a column header to sort (citations defaults to descending)
$('corpusTable').querySelector('thead').addEventListener('click', e => {
  const key = e.target.dataset && e.target.dataset.sort;
  if (!key) return;
  if (_sortKey === key) _sortDir = -_sortDir;
  else { _sortKey = key; _sortDir = key === 'cited_by' ? -1 : 1; }
  renderCorpus();
});
$('corpusFilter').addEventListener('input', renderCorpus);
$('corpusTable').addEventListener('click', e => {
  const tr = e.target.closest('.crow');
  if (!tr) return;
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('cdetail')) { next.remove(); return; }
  document.querySelectorAll('.cdetail').forEach(el => el.remove());
  const r = _corpusRows[+tr.dataset.i];
  if (!r) return;
  const bits = [];
  if (r.authors && r.authors.length) bits.push('<b>Authors:</b> ' + esc(r.authors.join(', ')));
  if (r.country) bits.push('<b>Country:</b> ' + esc(r.country));
  if (r.abstract) bits.push(esc(r.abstract));
  const links = [];
  if (r.doi) links.push(`<a href="${esc(r.doi)}" target="_blank" rel="noopener">DOI</a>`);
  if (r.pdf_url) links.push(`<a href="${esc(r.pdf_url)}" target="_blank" rel="noopener">PDF</a>`);
  if (links.length) bits.push(links.join(' · '));
  const det = document.createElement('tr');
  det.className = 'cdetail';
  det.innerHTML = `<td colspan="5">${bits.join('<br>') || 'No abstract.'}</td>`;
  tr.after(det);
});

// notify when a build finishes while the user is on another tab/app
// copy a shareable deep-link to the current corpus
$('share').onclick = async () => {
  if (!_curKey) return;
  const link = location.origin + '/?corpus=' + encodeURIComponent(_curKey);
  try { await navigator.clipboard.writeText(link); } catch (e) {}
  const label = $('share').textContent;
  $('share').textContent = 'Copied!';
  setTimeout(() => { $('share').textContent = label; }, 1200);
};

function notifyDone(s){
  if (document.hasFocus() || !('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    new Notification('Papers AI', {
      body: (s && s.stage) || 'Your corpus is ready.',
      icon: '/static/icon-192.png',
    });
  } catch (e) {}
}

// keyboard shortcuts: "/" focuses the topic box, Cmd/Ctrl+Enter asks
document.addEventListener('keydown', e => {
  const typing = /^(input|textarea)$/i.test(e.target.tagName || '');
  if (e.key === '/' && !typing) { e.preventDefault(); $('topic').focus(); }
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !$('qa').classList.contains('disabled')) {
    e.preventDefault(); $('ask').click();
  }
});

// on load: open a shared corpus (?corpus=key) if present, else resume the last one
(async () => {
  const key = new URLSearchParams(location.search).get('corpus');
  if (key) {
    try {
      await fetch('/corpus/select', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) });
    } catch (e) {}
  }
  loadCorpus();
})();

// handle a build-status update (from the SSE stream or the polling fallback)
function handleStatus(s) {
  if (_curJob === null) return;          // ignore a stray status after completion
  $('bar').style.width = (s.progress || 0) + '%';
  $('stage').textContent = s.stage || '';
  updateETA(s.progress || 0);
  if (s.done) {
    _curJob = null; _jobId = null;
    $('go').disabled = false; $('cancel').style.display = 'none';
    stopFun(!s.error);
    if (!s.error) { $('qa').classList.remove('disabled'); $('q').focus(); loadCorpus(); notifyDone(s); }
    else if (s.suggested_n) { $('n').value = s.suggested_n; $('n').focus(); }
    connect(null);                       // build over -> metrics-only stream
  }
}

// --- ask ---
const esc = s => String(s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let _sources = [], _sugg = [], _ghost = '';

// Minimal, safe Markdown -> HTML (input is escaped first, so no raw HTML passes).
function mdToHtml(src){
  const inline = t => t
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  const lines = esc(src || '').split('\n');
  let html = '', inUl = false, inOl = false, inCode = false, code = '';
  const closeLists = () => { if (inUl) { html += '</ul>'; inUl = false; }
                             if (inOl) { html += '</ol>'; inOl = false; } };
  for (const ln of lines){
    if (/^\s*```/.test(ln)){
      if (!inCode) { closeLists(); inCode = true; code = ''; }
      else { html += '<pre><code>' + code + '</code></pre>'; inCode = false; }
      continue;
    }
    if (inCode){ code += ln + '\n'; continue; }
    let m;
    if ((m = ln.match(/^(#{1,6})\s+(.*)$/))){
      closeLists();
      const lvl = Math.min(6, Math.max(2, m[1].length + 1));
      html += `<h${lvl}>` + inline(m[2]) + `</h${lvl}>`;
    } else if ((m = ln.match(/^\s*[-*]\s+(.*)$/))){
      if (inOl) { html += '</ol>'; inOl = false; }
      if (!inUl) { html += '<ul>'; inUl = true; }
      html += '<li>' + inline(m[1]) + '</li>';
    } else if ((m = ln.match(/^\s*\d+\.\s+(.*)$/))){
      if (inUl) { html += '</ul>'; inUl = false; }
      if (!inOl) { html += '<ol>'; inOl = true; }
      html += '<li>' + inline(m[1]) + '</li>';
    } else if (!ln.trim()){
      closeLists();
    } else {
      closeLists();
      html += '<p>' + inline(ln) + '</p>';
    }
  }
  closeLists();
  if (inCode) html += '<pre><code>' + code + '</code></pre>';
  return html;
}

// Render the answer as Markdown, then turn [n] markers into hoverable citations.
function renderAnswer(text){
  $('answer').innerHTML = mdToHtml(text).replace(/\[(\d+)\]/g, (m, n) => {
    const i = +n - 1;
    return _sources[i] ? `<sup class="cite" data-i="${i}">[${n}]</sup>` : m;
  });
}

// --- answer-time estimate: rolling average of past answer durations (persisted) ---
let _askDur = [];
try { _askDur = JSON.parse(localStorage.getItem('askDur') || '[]'); } catch (e) { _askDur = []; }
let _askT0 = 0, _askTimer = null, _askEst = 0;
const askEstimate = () => _askDur.length ? _askDur.reduce((a, b) => a + b, 0) / _askDur.length : 0;
function startAskClock(){
  _askT0 = Date.now(); _askEst = askEstimate();
  $('abar').style.transition = 'width .3s ease-out';
  const tick = () => {
    const el = (Date.now() - _askT0) / 1000;
    if (_askEst > 0) {
      const rem = _askEst - el;
      $('astage').textContent = 'Thinking… ⏱ ' + fmt(el)
        + (rem > 1 ? ' · ~' + fmt(rem) + ' left' : ' · almost there…');
      $('abar').style.width = Math.min(96, 100 * el / _askEst) + '%';
    } else {
      $('astage').textContent = 'Thinking… ⏱ ' + fmt(el) + ' · estimating…';
      $('abar').style.width = Math.min(92, 100 * (1 - Math.exp(-el / 8))) + '%';
    }
  };
  tick(); _askTimer = setInterval(tick, 250);
}
function stopAskClock(ok){
  clearInterval(_askTimer); _askTimer = null;
  $('abar').style.width = '100%';
  if (ok) {
    _askDur.push((Date.now() - _askT0) / 1000);
    _askDur = _askDur.slice(-8);
    try { localStorage.setItem('askDur', JSON.stringify(_askDur)); } catch (e) {}
  }
}

let _streaming = false;
function beginStream(){            // first token arrived: stop the ETA, show live state
  _streaming = true;
  if (_askTimer) { clearInterval(_askTimer); _askTimer = null; }
  $('abar').style.width = '94%';
  $('astage').textContent = 'Streaming answer…';
}

$('ask').onclick = async () => {
  const question = $('q').value.trim();
  if (!question) return;
  _ghost = ''; $('ghost').innerHTML = '';
  _streaming = false; _sources = [];
  $('ask').disabled = true; $('answer').style.display = 'none'; $('answer').textContent = '';
  $('sources').textContent = ''; $('verify').style.display = 'none'; $('verify').textContent = '';
  $('abarwrap').style.display = 'block'; $('abar').style.opacity = '.8';
  startAskClock();

  let answer = '', error = null, verifyNote = '';
  try {
    const resp = await fetch('/ask_stream', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
    const ctype = resp.headers.get('Content-Type') || '';
    if (!resp.ok || !resp.body || !ctype.includes('event-stream')) {
      const j = await resp.json().catch(() => ({ error: 'Request failed.' }));
      error = j.error || 'Request failed.';
    } else {
      $('answer').style.display = 'block';
      const reader = resp.body.getReader(), dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, i).split('\n').find(l => l.startsWith('data:'));
          buf = buf.slice(i + 2);
          if (!line) continue;
          let evt; try { evt = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }
          if (evt.sources) { _sources = evt.sources || []; }
          else if (evt.delta != null) { if (!_streaming) beginStream(); answer += evt.delta; $('answer').textContent = answer; }
          else if (evt.verify) { verifyNote = evt.verify; }
          else if (evt.error) { error = evt.error; }
        }
      }
    }
  } catch (e) { error = 'Network error.'; }

  stopAskClock(!error);
  $('abarwrap').style.display = 'none';
  $('ask').disabled = false;
  if (error) { $('astage').textContent = error; return; }
  $('astage').textContent = 'Answered in ' + fmt((Date.now() - _askT0) / 1000) + '.';
  $('answer').style.display = 'block';
  renderAnswer(answer);             // re-render the finished text as Markdown + citations
  if (verifyNote) {
    const ok = /^all claims supported/i.test(verifyNote.trim());
    $('verify').textContent = (ok ? '✓ ' : '⚠ Verification — ') + verifyNote;
    $('verify').style.display = '';
  }
  $('sources').innerHTML = _sources.length
    ? 'Sources: ' + _sources.map((s, i) =>
        `<span class="src-chip" data-i="${i}">“${esc(s.title || 'Untitled')}”</span>`).join('  ·  ')
    : '';
};

// --- hover tooltip for inline citations + source chips ---
const _tip = document.createElement('div');
_tip.className = 'tip'; document.body.appendChild(_tip);
function showTip(i, x, y){
  const s = _sources[i];
  if (!s) { hideTip(); return; }
  _tip.innerHTML = `<b>${esc(s.title || 'Untitled')}</b>`
    + (s.authors && s.authors.length ? `<div class="a">${esc(s.authors.slice(0,4).join(', '))}</div>` : '')
    + (s.journal || s.date ? `<div class="j">${esc([s.journal, s.date].filter(Boolean).join(' · '))}</div>` : '')
    + (s.snippet ? `<div class="s">${esc(s.snippet)}…</div>` : '');
  _tip.style.display = 'block';
  const w = _tip.offsetWidth, h = _tip.offsetHeight, pad = 14;
  let L = x + pad, T = y + pad;
  if (L + w > innerWidth - 8) L = x - w - pad;
  if (T + h > innerHeight - 8) T = y - h - pad;
  _tip.style.left = Math.max(8, L) + 'px';
  _tip.style.top = Math.max(8, T) + 'px';
}
function hideTip(){ _tip.style.display = 'none'; }
['mouseover', 'mousemove'].forEach(ev =>
  $('qa').addEventListener(ev, e => {
    const el = e.target.closest('.cite,.src-chip');
    if (el) showTip(+el.dataset.i, e.clientX, e.clientY);
  }));
$('qa').addEventListener('mouseout', e => { if (e.target.closest('.cite,.src-chip')) hideTip(); });

// --- predictive sentence completion (inline ghost text) ---
async function loadSugg(){
  try { _sugg = (await (await fetch('/suggest')).json()).suggestions || []; }
  catch (e) { _sugg = []; }
}
const _atEnd = () => { const el = $('q'); return el.selectionStart === el.value.length
  && el.selectionStart === el.selectionEnd; };
function predict(){
  const val = $('q').value;
  _ghost = '';
  if (val.trim()) {
    const lower = val.toLowerCase();
    const hit = _sugg.find(s => s.length > val.length && s.toLowerCase().startsWith(lower));
    if (hit) _ghost = hit.slice(val.length);
  }
  // typed text (transparent, just for spacing) + predicted suffix (muted)
  $('ghost').innerHTML = _ghost ? `<span class="typed">${esc(val)}</span>${esc(_ghost)}` : '';
  $('ghost').scrollLeft = $('q').scrollLeft;
}
function acceptGhost(){
  if (!_ghost) return false;
  $('q').value += _ghost; _ghost = ''; $('ghost').innerHTML = '';
  return true;
}
$('q').addEventListener('focus', async () => { if (!_sugg.length) await loadSugg(); predict(); });
$('q').addEventListener('input', predict);
$('q').addEventListener('scroll', () => { $('ghost').scrollLeft = $('q').scrollLeft; });
$('q').addEventListener('blur', () => { _ghost = ''; $('ghost').innerHTML = ''; });
$('q').addEventListener('keydown', e => {
  if (_ghost && (e.key === 'Tab' || (e.key === 'ArrowRight' && _atEnd()))) {
    e.preventDefault(); acceptGhost();
  } else if (e.key === 'Enter') {
    _ghost = ''; $('ghost').innerHTML = ''; $('ask').click();
  } else if (e.key === 'Escape') {
    _ghost = ''; $('ghost').innerHTML = '';
  }
});

// --- live system metrics ---
const cpuD = [], ramD = [], netD = [], MAXP = 60;
function push(a, v){ a.push(v); if (a.length > MAXP) a.shift(); }
function spark(cv, data, fixedMax, color){
  const ctx = cv.getContext('2d'), w = cv.width, h = cv.height;
  ctx.clearRect(0,0,w,h);
  if (!data.length) return;
  const max = fixedMax || Math.max(...data, 1);
  ctx.beginPath();
  data.forEach((v,i) => { const x = w*i/Math.max(1,MAXP-1), y = h - (v/max)*(h-4) - 2;
    i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); });
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
  ctx.lineTo(w*(data.length-1)/Math.max(1,MAXP-1), h); ctx.lineTo(0, h); ctx.closePath();
  ctx.globalAlpha = .15; ctx.fillStyle = color; ctx.fill(); ctx.globalAlpha = 1;
}
const fmtNet = k => k >= 1024 ? (k/1024).toFixed(1)+' MB/s' : Math.round(k)+' KB/s';
const ramGbD = [];  // rolling window of live RAM-used (GB) for the running average

function updateMetricsUI(m){
  push(cpuD, m.cpu); push(ramD, m.ram); push(netD, m.net_kbps);
  $('cpuVal').textContent = m.cpu + '%';
  $('ramVal').textContent = m.ram + '%';
  $('netVal').textContent = fmtNet(m.net_kbps);
  spark($('cpuG'), cpuD, 100, '#6ea8fe');
  spark($('ramG'), ramD, 100, '#3fb950');
  spark($('netG'), netD, 0,   '#e3b341');
  push(ramGbD, m.ram_used_gb);
  const avgGb = ramGbD.reduce((a, b) => a + b, 0) / ramGbD.length;
  $('ramUsed').textContent = m.ram_used_gb.toFixed(2) + ' GB (avg ' + avgGb.toFixed(2) + ')';
  if (m.dl_avg_s > 0) {
    $('dlAvg').textContent = m.dl_avg_s.toFixed(2) + ' s/paper'
      + (m.dl_active && m.dl_total ? '  (' + m.dl_done + '/' + m.dl_total + ')' : '');
  } else {
    $('dlAvg').textContent = m.dl_active ? 'starting…' : '–';
  }
}

const fmtDur = s => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return h + 'h ' + m + 'm';
  if (m) return m + 'm ' + sec + 's';
  return sec + 's';
};
const fmtMs = ms => ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : Math.round(ms) + ' ms';

function updateStatsUI(s){
  $('stUptime').textContent = fmtDur(s.uptime_s);
  $('stBuilds').textContent = s.builds;
  $('stPapers').textContent = s.papers.toLocaleString()
    + (s.with_text ? ' (' + s.with_text.toLocaleString() + ' full text)' : '');
  $('stQuestions').textContent = s.questions;
  $('stLastBuild').textContent = s.last_build_s ? s.last_build_s.toFixed(1) + ' s' : '–';
  $('stRetrieval').textContent = s.avg_retrieval_ms ? fmtMs(s.avg_retrieval_ms) : '–';
  $('stAnswer').textContent = s.avg_answer_ms ? fmtMs(s.avg_answer_ms) : '–';
}

// Push updates over a single SSE stream (metrics + the active build's status),
// falling back to polling if EventSource never connects (e.g. a buffering proxy).
let _es = null, _esGotData = false, _sseDead = !('EventSource' in window);
let _pmTimer = null, _psTimer = null, _stTimer = null, _curJob = null;

function pollMetricsOnce(){
  fetch('/metrics').then(r => r.json())
    .then(m => { if (!document.hidden) updateMetricsUI(m); }).catch(() => {});
}
function pollStatsOnce(){
  fetch('/stats').then(r => r.json())
    .then(s => { if (!document.hidden) updateStatsUI(s); }).catch(() => {});
}
function startStatusPoll(){
  if (_psTimer) { clearInterval(_psTimer); _psTimer = null; }
  if (!_curJob) return;
  _psTimer = setInterval(async () => {
    if (!_curJob) { clearInterval(_psTimer); _psTimer = null; return; }
    try { handleStatus(await (await fetch('/status?job=' + _curJob)).json()); } catch (e) {}
  }, 600);
}
function startPollingFallback(){
  if (!_pmTimer) { _pmTimer = setInterval(pollMetricsOnce, 1000); pollMetricsOnce(); }
  if (!_stTimer) { _stTimer = setInterval(pollStatsOnce, 5000); pollStatsOnce(); }
  startStatusPoll();
}
function connect(jobId){
  _curJob = jobId || null;
  if (_sseDead) { startPollingFallback(); return; }
  if (_es) { _es.close(); _es = null; }
  if (_psTimer) { clearInterval(_psTimer); _psTimer = null; }   // SSE carries status
  let es;
  try { es = new EventSource('/events' + (_curJob ? '?job=' + encodeURIComponent(_curJob) : '')); }
  catch (e) { _sseDead = true; startPollingFallback(); return; }
  _es = es;
  es.onmessage = ev => {
    _esGotData = true;
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    if (d.metrics && !document.hidden) updateMetricsUI(d.metrics);
    if (d.stats && !document.hidden) updateStatsUI(d.stats);
    if (d.status) handleStatus(d.status);
  };
  es.onerror = () => {
    if (!_esGotData) {            // never connected -> permanent polling fallback
      _sseDead = true; try { es.close(); } catch (e) {} _es = null;
      startPollingFallback();
    }                            // otherwise EventSource auto-reconnects
  };
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) { if (_es) { _es.close(); _es = null; } }
  else if (_sseDead) { pollMetricsOnce(); pollStatsOnce(); }
  else connect(_curJob);
});

connect(null);   // start the live stream (metrics; build status added on demand)

// --- PWA: service worker + install prompt ---
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () =>
    navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
let _installEvt = null;
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _installEvt = e;
  if ($('install')) $('install').style.display = '';
});
if ($('install')) $('install').onclick = async () => {
  if (!_installEvt) return;
  _installEvt.prompt();
  await _installEvt.userChoice;
  _installEvt = null;
  $('install').style.display = 'none';
};
window.addEventListener('appinstalled', () => {
  if ($('install')) $('install').style.display = 'none';
});
