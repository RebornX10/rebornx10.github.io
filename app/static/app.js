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
$('ask').onclick = async () => {
  const question = $('q').value.trim();
  if (!question) return;
  $('ask').disabled = true; $('answer').style.display = 'none'; $('sources').textContent = '';
  $('abarwrap').style.display = 'block'; $('abar').style.width = '100%';
  $('abar').style.transition = 'none'; $('abar').style.opacity = '.6';
  $('astage').textContent = 'Thinking with global model…';
  const res = await post('/ask', {question});
  $('abarwrap').style.display = 'none'; $('astage').textContent = '';
  $('ask').disabled = false;
  if (res.error) { $('astage').textContent = res.error; return; }
  $('answer').style.display = 'block'; $('answer').textContent = res.answer;
  if (res.sources && res.sources.length)
    $('sources').textContent = 'Sources: ' +
      res.sources.map(s => '“' + s.title + '”').join('  ·  ');
};
$('q').addEventListener('keydown', e => { if (e.key === 'Enter') $('ask').click(); });

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
  } catch (e) {}
}
setInterval(pollMetrics, 1000); pollMetrics();
