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
let theme = localStorage.getItem('theme') || 'dark';
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
$('go').onclick = async () => {
  const topic = $('topic').value.trim();
  if (!topic) { $('stage').textContent = 'Enter a topic first.'; return; }
  $('go').disabled = true; $('bar').style.width = '2%';
  $('stage').textContent = 'Starting…'; $('qa').classList.add('disabled');
  const {job_id, error} = await post('/build', {
    topic, date_from: $('from').value, date_to: $('to').value, n: +$('n').value });
  if (error || !job_id) { $('stage').textContent = error || 'Failed to start.';
                          $('go').disabled = false; return; }
  startFun(topic);
  poll(job_id);
};

function poll(job) {
  const t = setInterval(async () => {
    const s = await (await fetch('/status?job=' + job)).json();
    $('bar').style.width = (s.progress||0) + '%';
    $('stage').textContent = s.stage || '';
    updateETA(s.progress || 0);
    if (s.done) {
      clearInterval(t); $('go').disabled = false; stopFun(!s.error);
      if (!s.error) { $('qa').classList.remove('disabled'); $('q').focus(); }
      else if (s.suggested_n) { $('n').value = s.suggested_n; $('n').focus(); }
    }
  }, 500);
}

// --- ask ---
const esc = s => String(s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let _sources = [];

// Render the answer: HTML-escape it, then turn [n] markers into hoverable citations.
function renderAnswer(text){
  $('answer').innerHTML = esc(text || '').replace(/\[(\d+)\]/g, (m, n) => {
    const i = +n - 1;
    return _sources[i] ? `<sup class="cite" data-i="${i}">[${n}]</sup>` : m;
  });
}

$('ask').onclick = async () => {
  const question = $('q').value.trim();
  if (!question) return;
  $('ac').classList.remove('open');
  $('ask').disabled = true; $('answer').style.display = 'none'; $('sources').textContent = '';
  $('abarwrap').style.display = 'block'; $('abar').style.width = '100%';
  $('abar').style.transition = 'none'; $('abar').style.opacity = '.6';
  $('astage').textContent = 'Thinking with global model…';
  const res = await post('/ask', {question});
  $('abarwrap').style.display = 'none'; $('astage').textContent = '';
  $('ask').disabled = false;
  if (res.error) { $('astage').textContent = res.error; return; }
  _sources = res.sources || [];
  $('answer').style.display = 'block';
  renderAnswer(res.answer);
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

// --- autocomplete for the question bar ---
let _sugg = [], _acItems = [], _acIdx = -1;
async function loadSugg(){
  try { _sugg = (await (await fetch('/suggest')).json()).suggestions || []; }
  catch (e) { _sugg = []; }
}
function renderAC(){
  const v = $('q').value.trim().toLowerCase();
  _acItems = _sugg.filter(s => !v || s.toLowerCase().includes(v)).slice(0, 8);
  _acIdx = -1;
  if (!_acItems.length) { $('ac').classList.remove('open'); $('ac').innerHTML = ''; return; }
  $('ac').innerHTML = _acItems.map((s, i) =>
    `<div class="ac-item" data-i="${i}">${esc(s)}</div>`).join('');
  $('ac').classList.add('open');
  [...$('ac').children].forEach(el => {
    el.onmousedown = ev => { ev.preventDefault(); $('q').value = _acItems[+el.dataset.i];
      $('ac').classList.remove('open'); $('q').focus(); };
  });
}
function acHighlight(){ [...$('ac').children].forEach((el, i) => el.classList.toggle('active', i === _acIdx)); }
$('q').addEventListener('focus', async () => { if (!_sugg.length) await loadSugg(); renderAC(); });
$('q').addEventListener('input', renderAC);
$('q').addEventListener('blur', () => setTimeout(() => $('ac').classList.remove('open'), 130));
$('q').addEventListener('keydown', e => {
  const open = $('ac').classList.contains('open');
  if (open && e.key === 'ArrowDown') { e.preventDefault(); _acIdx = Math.min(_acIdx + 1, _acItems.length - 1); acHighlight(); }
  else if (open && e.key === 'ArrowUp') { e.preventDefault(); _acIdx = Math.max(_acIdx - 1, 0); acHighlight(); }
  else if (e.key === 'Enter') {
    if (open && _acIdx >= 0) { e.preventDefault(); $('q').value = _acItems[_acIdx]; $('ac').classList.remove('open'); }
    else { $('ac').classList.remove('open'); $('ask').click(); }
  }
  else if (e.key === 'Escape') { $('ac').classList.remove('open'); }
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
async function pollMetrics(){
  try {
    const m = await (await fetch('/metrics')).json();
    push(cpuD, m.cpu); push(ramD, m.ram); push(netD, m.net_kbps);
    $('cpuVal').textContent = m.cpu + '%';
    $('ramVal').textContent = m.ram + '%';
    $('netVal').textContent = fmtNet(m.net_kbps);
    spark($('cpuG'), cpuD, 100, '#6ea8fe');
    spark($('ramG'), ramD, 100, '#3fb950');
    spark($('netG'), netD, 0,   '#e3b341');

    // live RAM used (GB) + rolling average over the window
    push(ramGbD, m.ram_used_gb);
    const avgGb = ramGbD.reduce((a,b) => a+b, 0) / ramGbD.length;
    $('ramUsed').textContent = m.ram_used_gb.toFixed(2) + ' GB (avg ' + avgGb.toFixed(2) + ')';

    // average download speed per paper
    if (m.dl_avg_s > 0) {
      $('dlAvg').textContent = m.dl_avg_s.toFixed(2) + ' s/paper'
        + (m.dl_active && m.dl_total ? '  (' + m.dl_done + '/' + m.dl_total + ')' : '');
    } else {
      $('dlAvg').textContent = m.dl_active ? 'starting…' : '–';
    }
  } catch (e) {}
}
setInterval(pollMetrics, 1000); pollMetrics();

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
