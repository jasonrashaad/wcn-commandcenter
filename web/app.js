/* wcn-commandcenter — scene loop for the office TV.
   Sequence: brand, brand, reel(1 clip), brand, photos(3), brand, pulse — then round again.
   Brands rotate through the family; the reel advances one clip per visit so the
   whole playlist cycles over a few loops. Data comes from /api/state every 5 s (local; also carries the remote nudge).
   Remote nudge: GET /api/cmd?scene=reel|pulse|brand (from any LAN device). */

const BRANDS = [
  { key: 'wcn', img: '/assets/What_Comes_Next.svg', accent: '#f4f4f4',
    eyebrow: 'What Comes Next? LLC', name: 'What Comes Next?',
    line: 'Project-management discipline, applied to personal behavior change. Ardmore, PA.' },
  { key: 'evolutions', img: '/assets/Evolutions.svg', accent: '#f4a261',
    eyebrow: 'The methodology', name: 'Evolutions',
    line: 'Personal project management. Seven-day sprints. Pick 3 of 5. No judgment, just data.' },
  { key: 'spark', img: '/assets/The_Spark.svg', accent: '#e76f51',
    eyebrow: 'Free habit mapper', name: 'The Spark',
    line: 'Intake → a personalized report from a locally hosted model. Nothing leaves the building. Stays free.' },
  { key: 'clipboard', img: '/assets/Coach_s_Clipboard.svg', accent: '#eaaa00',
    eyebrow: 'The coach’s desk', name: 'Coach’s Clipboard',
    line: 'Lead management, pipeline, prompt testing. Evolves with use.' },
];

const SEQUENCE = ['brand', 'brand', 'reel', 'brand', 'photos', 'brand', 'pulse'];
const DUR = { brand: 32000, pulse: 26000, reelMax: 120000, photo: 14000, photosPerVisit: 3 };

const $ = (id) => document.getElementById(id);
let state = {};
let seqIdx = -1, brandIdx = -1, clipIdx = -1;
let timer = null, current = null, lastCmdSeq = null;

/* ── data ─────────────────────────────────────────────────────── */
async function poll() {
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    state = await r.json();
    renderChrome();
    if (current === 'pulse') renderPulse();
    if (state.cmd && lastCmdSeq !== null && state.cmd.seq !== lastCmdSeq && state.cmd.scene) {
      lastCmdSeq = state.cmd.seq;
      show(state.cmd.scene);
    } else if (lastCmdSeq === null && state.cmd) {
      lastCmdSeq = state.cmd.seq;
    }
  } catch (e) { /* keep last state; the screen never goes blank over a fetch */ }
}

/* ── scene switching ──────────────────────────────────────────── */
function next() {
  seqIdx = (seqIdx + 1) % SEQUENCE.length;
  let s = SEQUENCE[seqIdx];
  if (s === 'reel' && !(state.gallery && state.gallery.clips && state.gallery.clips.length)) s = 'brand';
  if (s === 'photos' && !(state.photos && state.photos.photos && state.photos.photos.length)) s = 'brand';
  show(s);
}

function show(name) {
  clearTimeout(timer);
  stopReel();
  document.querySelectorAll('.scene').forEach(el => el.classList.toggle('on', el.dataset.scene === name));
  document.body.classList.toggle('reel', name === 'reel');
  document.body.classList.toggle('photos', name === 'photos');
  current = name;
  if (name === 'brand') startBrand();
  else if (name === 'reel') startReel();
  else if (name === 'pulse') startPulse();
  else if (name === 'photos') startPhotos();
}

/* ── brand ────────────────────────────────────────────────────── */
function startBrand() {
  brandIdx = (brandIdx + 1) % BRANDS.length;
  const b = BRANDS[brandIdx];
  const sc = $('scene-brand');
  sc.classList.remove('in');
  setTimeout(() => {
    $('brand-img').src = b.img;
    $('brand-eyebrow').textContent = b.eyebrow;
    $('brand-name').textContent = b.name;
    $('brand-line').textContent = b.line;
    $('brand-rule').style.background = b.accent;
    requestAnimationFrame(() => sc.classList.add('in'));
  }, current === 'brand' ? 0 : 200);
  timer = setTimeout(next, DUR.brand);
}

/* ── reel ─────────────────────────────────────────────────────── */
const video = $('reel-video');
let progressTimer = null;

function startReel() {
  const g = state.gallery;
  const clips = g.clips;
  clipIdx = (clipIdx + 1) % clips.length;
  const c = clips[clipIdx];
  $('reel-eyebrow').textContent = (g.title || 'ILBTYD Gallery') + (g.source === 'studio' ? ' · from the studio' : '');
  $('reel-count').textContent = `${clipIdx + 1} / ${clips.length}`;
  $('reel-title').textContent = c.title;
  $('reel-blurb').textContent = c.blurb || '';
  $('reel-progress').style.width = '0';
  video.poster = c.poster || '';
  video.src = c.src;
  video.load();
  video.play().catch(() => {});
  progressTimer = setInterval(() => {
    if (video.duration) $('reel-progress').style.width = (100 * video.currentTime / video.duration) + '%';
  }, 400);
  timer = setTimeout(next, DUR.reelMax);   // a stalled stream must not park the screen
}
video.addEventListener('ended', () => { if (current === 'reel') next(); });
video.addEventListener('error', () => { if (current === 'reel') setTimeout(next, 1500); });

function stopReel() {
  clearInterval(progressTimer);
  clearTimeout(photoTimer);
  if (!video.paused) video.pause();
}

/* ── photos ───────────────────────────────────────────────────── */
let photoIdx = -1, photoShown = 0, photoTimer = null, photoLayer = 0;
const photoLayers = [$('photo-a'), $('photo-b')];

function startPhotos() {
  photoShown = 0;
  timer = setTimeout(next, DUR.photo * DUR.photosPerVisit + 20000);   // safety net for a stalled image
  nextPhoto();
}

function nextPhoto() {
  const list = state.photos.photos;
  if (photoShown >= DUR.photosPerVisit || !list.length) { next(); return; }
  photoIdx = (photoIdx + 1) % list.length;
  const p = list[photoIdx];
  const incoming = photoLayers[photoLayer ^= 1], outgoing = photoLayers[photoLayer ^ 1];
  const img = new Image();
  img.onload = () => {
    incoming.src = img.src;
    // Landscape fills the frame; portrait letterboxes, same rule as the reel.
    const wide = img.naturalWidth >= img.naturalHeight * 1.15;
    incoming.classList.toggle('cover', wide);
    $('scene-photos').classList.toggle('portrait', !wide);   // caption moves into the side bar
    outgoing.classList.remove('on');
    void incoming.offsetWidth;            // restart the drift animation
    incoming.classList.add('on');
    // PhotoPrism auto-titles restate the place ("Park / Lansing / 2023"), so the place leads.
    $('photo-title').textContent = p.place || p.title || '';
    const when = p.taken ? new Date(p.taken).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : '';
    $('photo-when').textContent = when;
    $('photo-place').textContent = p.camera || '';
    photoShown++;
    photoTimer = setTimeout(nextPhoto, DUR.photo);
  };
  img.onerror = () => { photoShown++; photoTimer = setTimeout(nextPhoto, 300); };
  img.src = p.src;
}

/* ── pulse ────────────────────────────────────────────────────── */
function startPulse() {
  renderPulse();
  timer = setTimeout(next, DUR.pulse);
}

function renderPulse() {
  const f = state.fleet || {};
  const hosts = f.hosts || [];
  $('pulse-summary').textContent = hosts.length
    ? (f.up === f.total ? 'all present.' : `${f.up} of ${f.total} present.`)
    : 'checking.';
  $('fleet').innerHTML = hosts.map(h => `
    <li><span class="dot ${h.ok ? 'ok' : 'down'}"></span>
        <span><span class="name">${esc(h.name)}</span><span class="role">${esc(h.role)}</span></span>
        <span class="ms">${h.ok ? h.ms + ' ms' : (h.detail || 'down')}</span></li>`).join('');

  $('stat-studio').textContent = (state.studio && state.studio.count != null) ? state.studio.count : '—';
  $('stat-gallery').textContent = (state.gallery && state.gallery.clips) ? state.gallery.clips.length : '—';
  const sys = state.sys || {};
  $('stat-temp').textContent = sys.temp_c != null ? Math.round(sys.temp_c) : '—';
  $('stat-up').textContent = sys.uptime_s != null ? fmtUptime(sys.uptime_s) : '—';

  const jf = state.jellyfin || {};
  let html;
  if (!jf.ok) {
    html = `<span class="dim">Not reachable right now.</span>`;
  } else if (jf.now_playing && jf.now_playing.length) {
    const p = jf.now_playing[0];
    const sub = [p.series || p.artist || p.album, p.year, p.user && `${p.user} on ${p.device || p.client}`].filter(Boolean).join(' · ');
    html = `<div class="jf-now"><img src="${p.image}" alt=""><div>
              <div class="t">${esc(p.title)}</div><div class="s">${p.paused ? 'Paused' : 'Now playing'} · ${esc(sub)}</div></div></div>`;
  } else if (jf.configured && jf.recent && jf.recent.length) {
    html = `<div class="s dim">Nothing playing. Recently added:</div>
            <div class="jf-recent">${jf.recent.slice(0, 6).map(r => `<img src="${r.image}" alt="${esc(r.title)}" title="${esc(r.title)}">`).join('')}</div>`;
  } else if (jf.configured) {
    html = `${esc(jf.server)} · ${esc(jf.version)} · quiet.`;
  } else {
    html = `${esc(jf.server)} · ${esc(jf.version)} · reachable. <span class="dim">Drop an API key in wcn-commandcenter.env to see what’s playing.</span>`;
  }
  $('jf-body').innerHTML = html;
}

/* ── chrome ───────────────────────────────────────────────────── */
function renderChrome() {
  const hosts = (state.fleet && state.fleet.hosts) || [];
  $('dots').innerHTML = hosts.map(h => `<i class="${h.ok ? 'ok' : 'down'}" title="${esc(h.name)}"></i>`).join('');
  if (state.sys && state.sys.host) $('host').textContent = state.sys.host;
}

function tick() {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  $('date').textContent = d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

/* ── utils ────────────────────────────────────────────────────── */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function fmtUptime(s) {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return d ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
}

/* ── remote / keyboard ─────────────────────────────────────────
   The Samsung remote arrives over HDMI-CEC as plain key events (kernel rc-cec
   keymap → libinput → Chromium). Bindings:
     Right / Down / Enter   next scene        Left / Up   previous scene
     Play-Pause / Space     hold here (pause the loop; again to resume)
     Back / Escape          resume the loop
     r / p / b              jump to reel / pulse / brand (keyboard only)
   Every key is echoed to the server log so unknown remote buttons can be mapped:
   tail -f ~/.cache/wcn-commandcenter.log  */
let held = false;
function hold(on) {
  held = on;
  document.body.classList.toggle('held', held);
  if (held) { clearTimeout(timer); clearTimeout(photoTimer); if (current === 'reel') video.pause(); }
  else if (current === 'reel') { video.play().catch(() => {}); timer = setTimeout(next, DUR.reelMax); }
  else if (current === 'photos') nextPhoto();
  else timer = setTimeout(next, DUR[current] || DUR.brand);
}
function prev() {
  // Step the cursors back two so next() lands on the previous item.
  if (current === 'reel' && state.gallery) { clipIdx -= 2; show('reel'); return; }
  if (current === 'photos' && state.photos) { clearTimeout(photoTimer); photoIdx -= 2; photoShown = Math.max(0, photoShown - 2); nextPhoto(); return; }
  seqIdx -= 2; if (SEQUENCE[(seqIdx + 1 + SEQUENCE.length) % SEQUENCE.length] === 'brand') brandIdx -= 2;
  held = false; document.body.classList.remove('held');
  next();
}
document.addEventListener('keydown', (e) => {
  fetch('/api/log?key=' + encodeURIComponent(e.key) + '&code=' + encodeURIComponent(e.code)).catch(() => {});
  switch (e.key) {
    case 'ArrowRight': case 'ArrowDown': case 'Enter': case 'n':
      held = false; document.body.classList.remove('held'); if (current === 'photos') { clearTimeout(photoTimer); nextPhoto(); } else next(); break;
    case 'ArrowLeft': case 'ArrowUp': prev(); break;
    case 'MediaPlayPause': case 'MediaPlay': case 'MediaPause': case ' ': hold(!held); break;
    case 'Escape': case 'BrowserBack': case 'GoBack': if (held) hold(false); break;
    case 'r': show('reel'); break;
    case 'p': show('pulse'); break;
    case 'b': show('brand'); break;
    default: return;
  }
  e.preventDefault();
});

/* ── go ───────────────────────────────────────────────────────── */
tick(); setInterval(tick, 1000);
poll().then(() => { next(); });
setInterval(poll, 5000);

/* Landscape clips fill the frame (cover); portrait phone clips would lose their
   heads to that crop, so they letterbox (contain) instead. Decided per clip. */
video.addEventListener('loadedmetadata', () => {
  video.style.objectFit = video.videoWidth >= video.videoHeight ? 'cover' : 'contain';
});
