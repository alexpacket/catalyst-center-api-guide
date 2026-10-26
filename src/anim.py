"""Animated flows: packets along figure arrows, play/pause bars, and the live cadence simulation."""


def sim_controls():
    return '''<div class="simbar" id="simbar" role="group" aria-label="Simulation controls">
  <button type="button" class="sbtn" id="sim-pp" aria-pressed="false">Pause</button>
  <button type="button" class="sbtn" id="sim-cr">Run Command Runner</button>
  <button type="button" class="sbtn" id="sim-is">Raise an issue</button>
  <button type="button" class="sbtn" id="sim-cm">Run CMDB sync now</button>
  <button type="button" class="sbtn warn" id="sim-bk">Fire 120-call bulk script</button>
  <label class="simspd">Speed <input type="range" id="sim-sp" min="1" max="20" value="4" aria-label="Simulated minutes per second"> <span id="sim-spv">4 min/s</span></label>
  <span class="simclk" id="sim-clk" aria-live="off">Day 1 08:00</span>
</div>'''


def sim_log():
    return '''<div class="simlog-w"><div class="simlegend">
  <span><i class="pk-dev"></i>device telemetry and resync (no API call)</span>
  <span><i class="pk-read"></i>read call</span><span><i class="pk-write"></i>write or task</span>
  <span><i class="pk-acc"></i>event or webhook</span><span><i class="pk-bad"></i>429 rejected</span></div>
<ol class="simlog" id="sim-log" aria-live="polite" aria-label="Simulation event log"></ol></div>'''


JS = r'''
(function(){
var RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var NS = 'http://www.w3.org/2000/svg';
/* ---- shared packet engine ---- */
var live = [];
function loop(now){
  for (var i = live.length - 1; i >= 0; i--) {
    var p = live[i];
    if (p.paused()) { p.t0 += now - (p.last || now); p.last = now; continue; }
    p.last = now;
    var k = Math.min(1, (now - p.t0) / p.dur), pt = p.at(k);
    p.c.setAttribute('cx', pt[0]); p.c.setAttribute('cy', pt[1]);
    p.c.setAttribute('opacity', k < 0.08 ? k / 0.08 : (k > 0.92 ? (1 - k) / 0.08 : 1));
    if (k >= 1) { p.c.remove(); live.splice(i, 1); if (p.done) p.done(); }
  }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
function polyAt(pts){
  var seg = [], tot = 0;
  for (var i = 1; i < pts.length; i++) { var l = Math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]); seg.push(l); tot += l; }
  return function(k){ var d = k * tot;
    for (var i = 0; i < seg.length; i++) { if (d <= seg[i] || i === seg.length - 1) { var f = seg[i] ? Math.min(1, d / seg[i]) : 1;
      return [pts[i][0] + (pts[i+1][0] - pts[i][0]) * f, pts[i][1] + (pts[i+1][1] - pts[i][1]) * f]; } d -= seg[i]; }
    return pts[pts.length - 1]; };
}
function send(layer, at, cls, dur, paused, done){
  var c = document.createElementNS(NS, 'circle'); c.setAttribute('r', 4.5); c.setAttribute('class', 'pk ' + cls); c.setAttribute('opacity', 0);
  layer.appendChild(c); live.push({c: c, at: at, dur: dur, t0: performance.now(), paused: paused, done: done});
}
function pathAt(p){ var L = p.getTotalLength(); return function(k){ var q = p.getPointAtLength(k * L); return [q.x, q.y]; }; }
function arrowCls(p){ var m = (p.getAttribute('class') || '').match(/a-(\w+)/); return 'pk-' + (m ? m[1] : 'n'); }
function layerOf(svg){ var g = svg.querySelector('g.pk-layer'); if (!g) { g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'pk-layer'); svg.appendChild(g); } return g; }
var never = function(){ return false; };

/* ---- stepper figures: one packet along the current step's arrows ---- */
window.catcFlow = function(stepEl){
  if (RM || !stepEl) return; var svg = stepEl.closest('svg');
  stepEl.querySelectorAll('path[marker-end], path[marker-start], line[marker-end]').forEach(function(p){ if (p.getTotalLength) send(layerOf(svg), pathAt(p), arrowCls(p), 750, never); });
};

/* ---- auto-animated flow figures with a play bar ---- */
document.querySelectorAll('figure.fig').forEach(function(fg){
  var svg = fg.querySelector('svg.dg');
  if (!svg || fg.querySelector('.stepbar') || fg.hasAttribute('data-noanim') || svg.querySelector('#sim-pk')) return;
  var arrows = Array.prototype.slice.call(svg.querySelectorAll('path[marker-end]'));
  if (arrows.length < 2) return;
  var STEP = 900, DUR = 750, T = arrows.length * STEP + 1200, start = performance.now(), off = 0, playing = !RM, visible = false, pausedAt = 0, timer = null;
  var bar = document.createElement('div'); bar.className = 'animbar';
  bar.innerHTML = '<button type="button" class="sbtn" data-a="pp"></button><button type="button" class="sbtn" data-a="rp">Replay</button><span class="ainfo">' + arrows.length + ' flows, ' + (T / 1000).toFixed(1) + ' s loop</span>';
  fg.insertBefore(bar, fg.firstChild);
  var pp = bar.querySelector('[data-a="pp"]');
  function label(){ pp.textContent = playing ? 'Pause' : 'Play'; pp.setAttribute('aria-pressed', playing ? 'false' : 'true'); }
  var idx = 0;
  function tick(){
    if (!(playing && visible)) return;
    var p = arrows[idx];
    send(layerOf(svg), pathAt(p), arrowCls(p), DUR, function(){ return !(playing && visible); });
    p.classList.add('pulse'); setTimeout(function(){ p.classList.remove('pulse'); }, DUR);
    idx++; if (idx >= arrows.length) { idx = 0; timer = setTimeout(tick, 1200 + STEP); return; }
    timer = setTimeout(tick, STEP);
  }
  function resume(){ clearTimeout(timer); if (playing && visible) tick(); }
  bar.addEventListener('click', function(e){ var b = e.target.closest('[data-a]'); if (!b) return;
    if (b.getAttribute('data-a') === 'pp') { playing = !playing; label(); resume(); }
    else { idx = 0; playing = true; label(); resume(); } });
  label();
  if ('IntersectionObserver' in window) new IntersectionObserver(function(es){ es.forEach(function(e){ var was = visible; visible = e.isIntersecting; if (visible && !was) resume(); }); }, {threshold: 0.25}).observe(svg);
  else { visible = true; resume(); }
});

/* ---- live cadence simulation ---- */
var S = document.getElementById('sim-pk'); if (!S) return;
var svg = S.closest('svg'), clk = document.getElementById('sim-clk'), logEl = document.getElementById('sim-log'),
    sp = document.getElementById('sim-sp'), spv = document.getElementById('sim-spv'), ppb = document.getElementById('sim-pp'), gw = document.getElementById('sim-gw');
var t = 0, speed = 4, running = !RM, visible = false, last = null, queue = [], nextIssue = 47;
var DEV = [121, 201, 281];
/* Illustrative per-operation limits per minute; real values are on each operation's Features tab. */
var OPS = {site: {limit: 100}, dev: {limit: 100}, cli: {limit: 50}, task: {limit: 1000}};
Object.keys(OPS).forEach(function(k){ var o = OPS[k]; o.calls = []; o.shown = 0; o.hold = 0;
  o.bar = document.getElementById('sim-m-' + k); o.txt = document.getElementById('sim-c-' + k); });
var P = {
  noc: [[590,121],[440,121],[420,185]], cmdb: [[590,191],[440,191],[420,123]], eng: [[590,261],[440,261],[420,247]],
  task2dev: [[240,247],[166,281]], ev: [[330,208],[330,286]], hook: [[420,309],[590,331]],
  bulk: [[590,191],[440,191],[420,123]]
};
function rev(a){ return a.slice().reverse(); }
function stopped(){ return !(running && visible); }
function go(pts, cls, done, dur){ send(S, polyAt(pts), cls, dur || 700, stopped, done); }
function hhmm(m){ var d = Math.floor((m + 480) / 1440) + 1, x = (m + 480) % 1440; return 'Day ' + d + ' ' + ('0' + Math.floor(x / 60)).slice(-2) + ':' + ('0' + Math.floor(x % 60)).slice(-2); }
function log(msg, cls){ var li = document.createElement('li'); li.className = cls || ''; li.innerHTML = '<b>' + hhmm(t) + '</b> '; li.appendChild(document.createTextNode(msg));
  logEl.insertBefore(li, logEl.firstChild); while (logEl.children.length > 8) logEl.removeChild(logEl.lastChild); }
function at(dt, fn){ queue.push({at: t + dt, fn: fn}); }
function inWindow(o){ o.calls = o.calls.filter(function(c){ return c > t - 1; }); return o.calls.length; }
function apiCall(pts, cls, op, ok){
  var o = OPS[op];
  if (o && inWindow(o) >= o.limit) { go(pts.slice(0, 2), 'pk-bad', function(){ go(rev(pts.slice(0, 2)), 'pk-bad'); }, 500); gw.classList.add('hot'); setTimeout(function(){ gw.classList.remove('hot'); }, 400); return false; }
  if (o) o.calls.push(t);
  go(pts, cls, function(){ go(rev(pts), cls, ok); }); return true;
}
function noc(){ apiCall(P.noc, 'pk-read', 'site'); }
function cmdb(pages){ var ok = 0, rej = 0;
  for (var i = 0; i < pages; i++) (function(i){ at(i * 0.03, function(){ apiCall(P.cmdb, 'pk-read', 'dev') ? ok++ : rej++; if (i === pages - 1) log('CMDB sync: ' + pages + ' pages of 500 devices (offset 1, 501, 1001...)' + (rej ? '; ' + rej + ' pages hit 429 and must be retried' : ''), rej ? 'bad' : 'read'); }); })(i); }
function bulk(){ var rej = 0, N = 120;
  for (var i = 0; i < N; i++) (function(i){ at(i * 0.004, function(){ if (!apiCall(P.bulk, 'pk-read', 'dev')) rej++;
    if (i === N - 1) log('Bulk script: ' + N + ' GET /network-device calls in under a minute. ' + rej + ' rejected with 429 by that operation\'s limit; the dashboard\'s site-health calls are unaffected. Back off and retry.', rej ? 'bad' : 'read'); }); })(i); }
function cmdRunner(){
  if (!apiCall(P.eng, 'pk-write', 'cli', null)) { log('Command Runner request rejected with 429: that operation\'s limit is used up for this client IP address.', 'bad'); return; }
  log('Engineer: POST /network-device-poller/cli/read-request returns 202 and a taskId', 'write');
  at(0.6, function(){ go(P.task2dev, 'pk-dev', function(){ go(rev(P.task2dev), 'pk-dev'); }); });
  at(2, function(){ apiCall(P.eng, 'pk-write', 'task'); log('Engineer: GET /tasks/{id} until status is SUCCESS, then read the fileId from the task's progress', 'write'); });
  at(3, function(){ apiCall(P.eng, 'pk-write', null); log('Engineer: GET /file/{fileId} returns the CLI output', 'write'); });
}
function issue(manual){
  var y = DEV[Math.floor(Math.random() * 3)];
  go([[166,y],[240,185]], 'pk-bad', function(){ go(P.ev, 'pk-acc', function(){ go(P.hook, 'pk-acc'); }); });
  log((manual ? 'Issue raised: ' : 'Assurance issue detected: ') + 'event engine posts a webhook to the ITSM listener (outbound, no API call counted)', 'acc');
}
function step(prev, now){
  for (var m = Math.floor(prev) + 1; m <= Math.floor(now); m++) {
    DEV.forEach(function(y, i){ if ((m + i) % 2 === 0) go([[166,y],[240,185]], 'pk-dev', null, 600); });
    if (m % 5 === 0) noc();
    if (m % 360 === 0) { DEV.forEach(function(y){ go([[166,y],[240,123]], 'pk-dev'); }); log('Periodic inventory resync (6-hour minimum interval from 3.1.5)', 'dev'); }
    if ((m + 480) % 1440 === 120) cmdb(10);
    if (m >= nextIssue) { issue(false); nextIssue = m + 40 + Math.floor(Math.random() * 60); }
  }
}
function frame(now){
  if (last === null) last = now; var dt = (now - last) / 1000; last = now;
  if (running && visible && dt < 0.5) {
    var prev = t; t += dt * speed;
    queue.sort(function(a, b){ return a.at - b.at; });
    while (queue.length && queue[0].at <= t) queue.shift().fn();
    step(prev, t); clk.textContent = hhmm(t);
  }
  Object.keys(OPS).forEach(function(k){ var o = OPS[k], n = inWindow(o);
    if (n >= o.shown) { o.shown = n; o.hold = now; } else if (now - o.hold > 1500) o.shown = Math.max(n, o.shown - dt * o.limit * 0.8);
    var v = Math.round(o.shown); if (!o.bar) return;
    o.bar.setAttribute('width', Math.min(1, v / (o.limit * 1.5)) * 296); o.bar.classList.toggle('over', v >= o.limit);
    o.txt.textContent = v + ' / ' + o.limit + (v >= o.limit ? ', limit reached' : ''); });
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
function setRun(r){ running = r; ppb.textContent = r ? 'Pause' : 'Play'; ppb.setAttribute('aria-pressed', r ? 'false' : 'true'); }
setRun(running);
ppb.addEventListener('click', function(){ setRun(!running); });
sp.addEventListener('input', function(){ speed = +sp.value; spv.textContent = speed + ' min/s'; });
document.getElementById('sim-cr').addEventListener('click', function(){ if (!running) setRun(true); cmdRunner(); });
document.getElementById('sim-is').addEventListener('click', function(){ if (!running) setRun(true); issue(true); });
document.getElementById('sim-cm').addEventListener('click', function(){ if (!running) setRun(true); cmdb(10); });
document.getElementById('sim-bk').addEventListener('click', function(){ if (!running) setRun(true); bulk(); });
if ('IntersectionObserver' in window) new IntersectionObserver(function(es){ es.forEach(function(e){ visible = e.isIntersecting; }); }, {threshold: 0.2}).observe(svg);
else visible = true;
log('Simulation started. NOC polls site health every 5 min; CMDB sync runs nightly at 02:00. Each operation has its own limit.', 'read');
})();
'''
