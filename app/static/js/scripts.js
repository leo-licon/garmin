/* ── Clock ─────────────────────────────────────────────── */
function startClock(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const update = () => {
    el.textContent = new Date().toLocaleString('es-MX', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      day: '2-digit', month: 'short'
    });
  };
  update();
  setInterval(update, 1000);
}

/* ── Toast ─────────────────────────────────────────────── */
function toast(msg, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* ── Live log ───────────────────────────────────────────── */
function addLog(msg, type = 'info') {
  const log = document.getElementById('live-log');
  if (!log) return;
  const line = document.createElement('div');
  const ts = new Date().toLocaleTimeString('es-MX');
  line.className = `log-line ${type}`;
  line.textContent = `[${ts}] ${msg}`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

/* ── Hamburger / sidebar ────────────────────────────────── */
function initSidebar() {
  const hamburger = document.getElementById('hamburger');
  const sidebar   = document.getElementById('sidebar');
  const overlay   = document.getElementById('sidebar-overlay');
  if (!hamburger || !sidebar) return;

  const toggle = () => {
    const isOpen = sidebar.classList.toggle('open');
    overlay.classList.toggle('open', isOpen);
    hamburger.classList.toggle('open', isOpen);
  };
  const close = () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
    hamburger.classList.remove('open');
  };

  hamburger.addEventListener('click', toggle);
  overlay.addEventListener('click', close);
  sidebar.querySelectorAll('nav a').forEach(a => a.addEventListener('click', close));
}

/* ── Init on DOM ready ──────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  startClock('clock');
  initSidebar();
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js');
}
