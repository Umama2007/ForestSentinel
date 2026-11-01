/* ==========================================================================
   ForestSentinel — data + motion & interaction layer
   Every figure on the page is rendered from /api/dashboard, which reads the
   latest ETL, analysis and conservation reports — nothing is hardcoded.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const PRIORITY = {
    'High Priority': { cls: 'high', color: 'var(--g-high)', fill: '#f87171', short: 'High' },
    'Medium Priority': { cls: 'medium', color: 'var(--g-medium)', fill: '#fbbf24', short: 'Medium' },
    'Low Priority': { cls: 'low', color: 'var(--g-low)', fill: '#475569', short: 'Low' },
  };

  // Vertical gradients for SVG marks, drawn from the dashboard palette.
  const GRADIENTS = {
    primary: ['#34d399', '#06b6d4'],
    day: ['#fde68a', '#f59e0b'],
    night: ['#67e8f9', '#0891b2'],
  };

  const FIGURE_NAMES = {
    daily_fire_activity: ['Daily Fire Activity', 'Temporal Profile'],
    hourly_activity: ['Detections by Hour', 'Diurnal Cycle'],
    frp_distribution: ['Fire Radiative Power (FRP) Distribution', 'Intensity'],
    brightness_distribution: ['Brightness Temperature', 'VIIRS I-4 / I-5'],
    outlier_boxplots: ['Outlier Box Plots', 'Tukey Fences'],
    confidence_distribution: ['Detection Confidence Levels', 'Quality'],
    day_night_distribution: ['Day vs Night Passes', 'Overpass'],
    satellite_sensor_distribution: ['Satellite / Sensor Mix', 'Instrument'],
    hotspot_priority_distribution: ['0.25° Hotspot Priority Distribution', 'Explainable Scoring'],
    species_exposure_by_priority_zone: ['Species by Priority Zone', 'GBIF Exposure'],
    top_conservation_priority_cells: ['Top Conservation Cells', 'Ranking'],
    threatened_species_by_category: ['Threatened Species by Category', 'IUCN'],
    biodiversity_data_quality: ['Biodiversity Data Quality', 'GBIF Records'],
  };

  /* ---------------------------------------------------------------------
     Formatting helpers
     --------------------------------------------------------------------- */
  const fmt = (n, d = 0) =>
    n == null || Number.isNaN(n) ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
  const pct = (part, whole) => (whole ? (part / whole) * 100 : 0);
  const parseDay = (s) => new Date(`${s}T00:00:00Z`);
  const fmtDay = (s, opts = { month: 'short', day: 'numeric' }) => parseDay(s).toLocaleDateString('en-US', { ...opts, timeZone: 'UTC' });
  const fmtDateTime = (iso) =>
    new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  /** Number that counts up when it scrolls into view (final value is the fallback text). */
  const num = (v, dec = 0, suffix = '') =>
    v == null || Number.isNaN(v) ? '—' : `<span data-count="${v}" data-dec="${dec}" data-suffix="${suffix}">${fmt(v, dec)}${suffix}</span>`;
  const cellName = (id) => {
    const m = /grid_(-?[\d.]+)_(-?[\d.]+)/.exec(id || '');
    if (!m) return esc(id);
    const lat = Number(m[1]), lon = Number(m[2]);
    return `${Math.abs(lat).toFixed(2)}°${lat < 0 ? 'S' : 'N'}, ${Math.abs(lon).toFixed(2)}°${lon < 0 ? 'W' : 'E'}`;
  };
  /** Sparkline bar heights (as %) from a list of values. */
  const spark = (vals) => {
    const v = (vals || []).filter((x) => x != null).slice(0, 8);
    const max = Math.max(1, ...v);
    return v.map((x) => `<span style="--h:${Math.max(14, (x / max) * 100)}%"></span>`).join('');
  };

  /* ---------------------------------------------------------------------
     Tooltip
     --------------------------------------------------------------------- */
  const tip = $('#tooltip');
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 14;
    const r = tip.getBoundingClientRect();
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  }
  const hideTip = () => { tip.hidden = true; };

  /* ---------------------------------------------------------------------
     SVG chart primitives
     --------------------------------------------------------------------- */
  let gradSeq = 0;
  function svgEl(tag, attrs = {}, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  /** Return an SVG fill for a gradient key, creating its <linearGradient> on first use. */
  function paint(svg, key) {
    svg._grads = svg._grads || {};
    if (!svg._grads[key]) {
      const id = `fsg-${key}-${++gradSeq}`;
      const defs = svg.querySelector('defs') || svgEl('defs', {}, svg);
      const lg = svgEl('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      svgEl('stop', { offset: '0%', 'stop-color': GRADIENTS[key][0] }, lg);
      svgEl('stop', { offset: '100%', 'stop-color': GRADIENTS[key][1] }, lg);
      svg._grads[key] = `url(#${id})`;
    }
    return svg._grads[key];
  }

  function niceMax(v) {
    if (v <= 0) return 1;
    const mag = 10 ** Math.floor(Math.log10(v));
    const n = v / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }

  /** Column path with a rounded data-end and a square baseline. */
  function columnPath(x, y, w, h, r = 4) {
    if (h <= 0) return '';
    r = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }

  /** Column chart, optionally stacked. series: [{ name, color, values[] }] */
  function columnChart(container, { labels, series, height = 240, tickEvery = 1, labelValues = false, tipFor }) {
    container.innerHTML = '';
    const W = 640, H = height, m = { t: 20, r: 8, b: 28, l: 36 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const totals = labels.map((_, i) => series.reduce((s, ser) => s + (ser.values[i] || 0), 0));
    const yMax = niceMax(Math.max(...totals) * 1.08);
    const band = iw / labels.length;
    const bw = Math.min(26, band * 0.62);

    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img' }, container);
    const g = svgEl('g', { transform: `translate(${m.l},${m.t})` }, svg);

    for (let k = 0; k <= 4; k++) {
      const v = (yMax / 4) * k, y = ih - (v / yMax) * ih;
      if (k > 0) svgEl('line', { class: 'grid-line', x1: 0, x2: iw, y1: y, y2: y }, g);
      svgEl('text', { x: -8, y: y + 4, 'text-anchor': 'end' }, g).textContent = fmt(v);
    }
    svgEl('line', { class: 'baseline', x1: 0, x2: iw, y1: ih, y2: ih }, g);

    labels.forEach((lab, i) => {
      const cx = band * i + band / 2;
      let acc = 0;
      const marks = [];
      series.forEach((ser, si) => {
        const v = ser.values[i] || 0;
        if (!v) return;
        const h = (v / yMax) * ih;
        const y = ih - ((acc + v) / yMax) * ih;
        const isTop = series.slice(si + 1).every((s) => !(s.values[i] || 0));
        const hh = acc > 0 ? Math.max(0, h - 2) : h;
        const path = isTop ? columnPath(cx - bw / 2, y, bw, hh) : `M${cx - bw / 2},${y}h${bw}v${hh}h${-bw}Z`;
        marks.push(svgEl('path', { d: path, fill: paint(svg, ser.color), class: 'mark', style: `--i:${i}` }, g));
        acc += v;
      });

      if (labelValues && totals[i]) {
        svgEl('text', { class: 'value-label', x: cx, y: ih - (totals[i] / yMax) * ih - 7, 'text-anchor': 'middle' }, g).textContent = fmt(totals[i]);
      }
      if (i % tickEvery === 0) {
        svgEl('text', { class: 'axis-label', x: cx, y: ih + 18, 'text-anchor': 'middle' }, g).textContent = lab;
      }

      const hit = svgEl('rect', { class: 'hit', x: band * i, y: 0, width: band, height: ih + 4 }, g);
      hit.addEventListener('mousemove', (e) => {
        svg.classList.add('dimmed');
        marks.forEach((mk) => mk.classList.add('hover'));
        showTip(e, tipFor(i));
      });
      hit.addEventListener('mouseleave', () => {
        svg.classList.remove('dimmed');
        marks.forEach((mk) => mk.classList.remove('hover'));
        hideTip();
      });
    });
  }

  /** Histogram with Tukey fences, outlier zone and a box plot strip underneath. */
  function histogram(container, d, unit) {
    container.innerHTML = '';
    const { edges, counts, log_scale: log } = d.histogram;
    const W = 420, H = 230, m = { t: 16, r: 10, b: 66, l: 32 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const tf = (v) => (log ? Math.log10(Math.max(v, 1e-9)) : v);
    const lo = tf(edges[0]), hi = tf(edges[edges.length - 1]);
    const xOf = (v) => ((Math.min(Math.max(tf(v), lo), hi) - lo) / (hi - lo || 1)) * iw;
    const yMax = niceMax(Math.max(...counts) * 1.1);
    const INK = '#64748b';

    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${d.label} histogram` }, container);
    const g = svgEl('g', { transform: `translate(${m.l},${m.t})` }, svg);

    const ux = xOf(d.upper_fence), lx = xOf(d.lower_fence);
    if (d.upper_fence < d.max) svgEl('rect', { x: ux, y: 0, width: iw - ux, height: ih, fill: 'var(--outlier-wash)' }, g);
    if (d.lower_fence > d.min) svgEl('rect', { x: 0, y: 0, width: lx, height: ih, fill: 'var(--outlier-wash)' }, g);

    for (let k = 1; k <= 2; k++) {
      const y = ih - (k / 2) * ih;
      svgEl('line', { class: 'grid-line', x1: 0, x2: iw, y1: y, y2: y }, g);
      svgEl('text', { x: -6, y: y + 4, 'text-anchor': 'end' }, g).textContent = fmt((yMax / 2) * k);
    }

    counts.forEach((c, i) => {
      const x0 = xOf(edges[i]), x1 = xOf(edges[i + 1]);
      const w = Math.max(1, x1 - x0 - 2);
      const h = (c / yMax) * ih;
      const mark = svgEl('path', { d: columnPath(x0 + 1, ih - h, w, h, 3), fill: paint(svg, 'primary'), class: 'mark', style: `--i:${i}` }, g);
      const hit = svgEl('rect', { class: 'hit', x: x0, y: 0, width: Math.max(1, x1 - x0), height: ih }, g);
      hit.addEventListener('mousemove', (e) => {
        svg.classList.add('dimmed'); mark.classList.add('hover');
        showTip(e, `<b>${fmt(edges[i], 1)} – ${fmt(edges[i + 1], 1)} ${unit}</b><br>${fmt(c)} detections`);
      });
      hit.addEventListener('mouseleave', () => { svg.classList.remove('dimmed'); mark.classList.remove('hover'); hideTip(); });
    });
    svgEl('line', { class: 'baseline', x1: 0, x2: iw, y1: ih, y2: ih }, g);

    const fence = (x, text, anchor) => {
      svgEl('line', { x1: x, x2: x, y1: -4, y2: ih, stroke: '#f87171', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, g);
      svgEl('text', { x: x + (anchor === 'start' ? 4 : -4), y: 6, 'text-anchor': anchor, class: 'axis-label' }, g).textContent = text;
    };
    if (d.upper_fence < d.max) fence(ux, 'outliers →', ux > iw * 0.7 ? 'end' : 'start');
    if (d.lower_fence > d.min) fence(lx, '← outliers', lx < iw * 0.3 ? 'start' : 'end');

    [[d.min, 'start'], [d.median, 'middle'], [d.max, 'end']].forEach(([v, a]) => {
      svgEl('text', { x: xOf(v), y: ih + 15, 'text-anchor': a, class: 'axis-label' }, g).textContent = fmt(v, v < 100 ? 1 : 0);
    });

    // box plot strip
    const by = ih + 36, bh = 14;
    const wLo = Math.max(d.min, d.lower_fence), wHi = Math.min(d.max, d.upper_fence);
    svgEl('line', { x1: xOf(wLo), x2: xOf(wHi), y1: by, y2: by, stroke: INK, 'stroke-width': 1 }, g);
    [wLo, wHi].forEach((v) => svgEl('line', { x1: xOf(v), x2: xOf(v), y1: by - 5, y2: by + 5, stroke: INK, 'stroke-width': 1 }, g));
    svgEl('rect', { x: xOf(d.q1), y: by - bh / 2, width: Math.max(2, xOf(d.q3) - xOf(d.q1)), height: bh, rx: 3, fill: 'rgba(52, 211, 153, 0.14)', stroke: '#34d399', 'stroke-width': 1 }, g);
    svgEl('line', { x1: xOf(d.median), x2: xOf(d.median), y1: by - bh / 2, y2: by + bh / 2, stroke: '#f8fafc', 'stroke-width': 2 }, g);
    (d.outlier_values || []).forEach((v, k) => {
      svgEl('circle', { cx: xOf(v), cy: by, r: 4, fill: '#f87171', stroke: '#080e1b', 'stroke-width': 2, class: 'dot', style: `--i:${k}` }, g);
    });
    const boxHit = svgEl('rect', { class: 'hit', x: 0, y: by - 12, width: iw, height: 24 }, g);
    boxHit.addEventListener('mousemove', (e) =>
      showTip(e, `<b>Box plot</b><br>Q1 ${fmt(d.q1, 2)} · median ${fmt(d.median, 2)} · Q3 ${fmt(d.q3, 2)}<br>Fences ${fmt(d.lower_fence, 2)} – ${fmt(d.upper_fence, 2)} ${unit}`));
    boxHit.addEventListener('mouseleave', hideTip);
    if (log) svgEl('text', { x: iw, y: ih + 60, 'text-anchor': 'end' }, g).textContent = 'log scale';
  }

  /* ---------------------------------------------------------------------
     Scroll reveal choreography (works on content rendered after load)
     --------------------------------------------------------------------- */
  /* Safety net: if a reveal transition never gets a frame to run on
     (background tab, stalled renderer), force the final state so content
     is never left invisible. In a healthy renderer this never triggers. */
  function revealNow(el) {
    if (el.classList.contains('revealed')) return;
    const delay = parseInt(el.style.getPropertyValue('--rd'), 10) || 0;
    el.classList.add('revealed');
    window.setTimeout(() => {
      if (parseFloat(getComputedStyle(el).opacity) < 0.05) {
        el.style.setProperty('transition', 'none', 'important');
        el.style.setProperty('opacity', '1', 'important');
        el.style.setProperty('translate', 'none', 'important');
        el.style.setProperty('scale', '1', 'important');
      }
    }, delay + 1500);
  }

  const revealObserver = reduceMotion || !('IntersectionObserver' in window)
    ? null
    : new IntersectionObserver((entries, obs) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            revealNow(entry.target);
            obs.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  function observeReveal() {
    $$('[data-reveal]:not([data-watched])').forEach((el) => {
      el.dataset.watched = '1';
      const delay = el.getAttribute('data-delay');
      if (delay) el.style.setProperty('--rd', `${delay}ms`);
      if (revealObserver) revealObserver.observe(el);
      else el.classList.add('revealed');
    });
  }

  /* Belt-and-braces: if the observer never gets a frame (occluded window),
     reveal whatever is already inside the viewport. */
  function revealVisibleSoon() {
    window.setTimeout(() => {
      $$('[data-reveal]:not(.revealed)').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) revealNow(el);
      });
    }, 2500);
  }

  /* Watchdog for the hero word-reveal animation */
  window.setTimeout(() => {
    $$('.word-inner').forEach((w) => {
      const m = new DOMMatrixReadOnly(getComputedStyle(w).transform);
      if (Math.abs(m.m42) > 1) {
        w.style.setProperty('animation', 'none', 'important');
        w.style.setProperty('transform', 'none', 'important');
      }
    });
  }, 2600);

  /* ---------------------------------------------------------------------
     Animated counters + chart entrance
     --------------------------------------------------------------------- */
  const easeOutExpo = (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));

  function countUp(el) {
    const target = parseFloat(el.dataset.count);
    if (Number.isNaN(target)) return;
    const dec = Number(el.dataset.dec || 0), suffix = el.dataset.suffix || '';
    if (reduceMotion) { el.textContent = fmt(target, dec) + suffix; return; }
    const duration = 1500;
    const start = performance.now();
    const step = (now) => {
      const p = Math.min((now - start) / duration, 1);
      el.textContent = fmt(easeOutExpo(p) * target, dec) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  const motionObserver = reduceMotion || !('IntersectionObserver' in window)
    ? null
    : new IntersectionObserver((entries, obs) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          if (el.dataset.count != null) countUp(el); else el.classList.add('play');
          obs.unobserve(el);
        });
      }, { threshold: 0.3 });

  function observeMotion() {
    $$('.chart:not([data-moved]), [data-count]:not([data-moved])').forEach((el) => {
      el.dataset.moved = '1';
      if (motionObserver) motionObserver.observe(el);
      else if (el.dataset.count == null) el.classList.add('play');
    });
  }

  /* ---------------------------------------------------------------------
     3D tilt + magnetic buttons (bound to new cards after each render)
     --------------------------------------------------------------------- */
  const canHover = !reduceMotion && window.matchMedia('(hover: hover)').matches;
  function bindTilt() {
    if (!canHover) return;
    $$('.tilt:not([data-tilt])').forEach((card) => {
      card.dataset.tilt = '1';
      card.addEventListener('pointerenter', () => {
        card.style.transition = 'transform 0.18s ease-out, border-color 0.35s ease, box-shadow 0.4s ease, background 0.35s ease';
      });
      card.addEventListener('pointermove', (e) => {
        const rect = card.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width;
        const py = (e.clientY - rect.top) / rect.height;
        card.style.setProperty('--ry', `${(px - 0.5) * 9}deg`);
        card.style.setProperty('--rx', `${(0.5 - py) * 8}deg`);
      });
      card.addEventListener('pointerleave', () => {
        card.style.setProperty('--ry', '0deg');
        card.style.setProperty('--rx', '0deg');
        card.style.transition = '';
      });
    });
  }

  if (canHover) {
    $$('.btn-magnetic').forEach((btn) => {
      btn.addEventListener('pointermove', (e) => {
        const rect = btn.getBoundingClientRect();
        const mx = e.clientX - rect.left - rect.width / 2;
        const my = e.clientY - rect.top - rect.height / 2;
        btn.style.transform = `translate(${mx * 0.16}px, ${my * 0.24}px)`;
      });
      btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
    });
  }

  /** Re-run every per-element enhancement after content is (re)rendered. */
  function enhance() {
    observeReveal();
    observeMotion();
    bindTilt();
  }

  /* ---------------------------------------------------------------------
     Scroll progress + sticky nav state + scroll spy
     --------------------------------------------------------------------- */
  const progressBar = $('#scroll-progress-bar');
  const navbar = $('#navbar');
  const navLinks = $$('.nav-link');
  const glider = $('#nav-glider');
  const spyTargets = navLinks
    .map((link) => {
      const section = document.getElementById((link.getAttribute('href') || '').replace('#', ''));
      return section ? { link, section } : null;
    })
    .filter(Boolean);

  function placeGlider(activeLink) {
    if (!glider || !activeLink || window.innerWidth <= 1024) return;
    glider.style.width = `${activeLink.offsetWidth}px`;
    glider.style.transform = `translateX(${activeLink.offsetLeft}px)`;
    glider.classList.add('on');
  }

  let ticking = false;
  function onScroll() {
    const y = window.scrollY;
    const docH = document.documentElement.scrollHeight - window.innerHeight;
    if (progressBar) progressBar.style.width = `${docH > 0 ? (y / docH) * 100 : 0}%`;
    if (navbar) navbar.classList.toggle('scrolled', y > 12);

    let current = spyTargets[0];
    spyTargets.forEach((item) => {
      if (item.section.getBoundingClientRect().top <= 160) current = item;
    });
    if (current) {
      navLinks.forEach((l) => l.classList.toggle('active', l === current.link));
      placeGlider(current.link);
    }
    ticking = false;
  }

  window.addEventListener('scroll', () => {
    if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
  }, { passive: true });
  window.addEventListener('resize', () => placeGlider($('.nav-link.active')));
  navLinks.forEach((link) => link.addEventListener('mouseenter', () => placeGlider(link)));
  const navLinkWrap = $('#nav-links');
  if (navLinkWrap) navLinkWrap.addEventListener('mouseleave', () => placeGlider($('.nav-link.active')));
  window.addEventListener('load', onScroll);
  onScroll();

  /* Mobile nav */
  const burger = $('#nav-burger');
  if (burger && navbar) {
    burger.addEventListener('click', () => {
      const open = navbar.classList.toggle('nav-open');
      burger.classList.toggle('open', open);
      burger.setAttribute('aria-expanded', String(open));
    });
    navLinks.forEach((link) =>
      link.addEventListener('click', () => {
        navbar.classList.remove('nav-open');
        burger.classList.remove('open');
        burger.setAttribute('aria-expanded', 'false');
      })
    );
  }

  /* Hero spotlight (cursor-following glow) */
  const hero = $('.hero-section');
  if (hero && !reduceMotion) {
    hero.addEventListener('pointermove', (e) => {
      const rect = hero.getBoundingClientRect();
      hero.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`);
      hero.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`);
    });
  }

  $('#live-host').textContent = `LIVE ON ${location.host.toUpperCase()}`;

  /* ---------------------------------------------------------------------
     Hero: meta bar, ticker, KPI cards
     --------------------------------------------------------------------- */
  function renderHeroMeta(etl) {
    if (!etl) return;
    if (etl.study_bbox) $('#meta-area').textContent = `Amazon Pilot Bounding Box ([${etl.study_bbox.split(',').join(', ')}])`;
    const project = etl.database_project || etl.firebase_project_id;
    if (project) $('#meta-storage').textContent = `Supabase Postgres (${project})`;
  }

  function renderLead(etl, a) {
    const ov = a.eda_results.overview;
    const grid = a.grid_metadata;
    const dates = ov.unique_detection_dates || [];
    const first = dates[0], last = dates[dates.length - 1];
    const range = first && last ? `${fmtDay(first)} – ${fmtDay(last, { month: 'short', day: 'numeric', year: 'numeric' })}` : '—';
    const daily = a.eda_results.temporal.daily_detections || {};
    const dailyVals = Object.keys(daily).sort().map((k) => daily[k]);
    const peak = Object.entries(daily).sort((x, y) => y[1] - x[1])[0];
    const top = a.top_hotspot_cells[0];
    const frp = a.eda_results.distributions?.frp;
    const sats = (ov.satellites || []).join(', ');

    const ticks = [
      ['crimson', `${fmt(ov.total_records)} DETECTIONS ANALYSED`],
      ['amber', `${fmt(grid.total_populated_cells)} POPULATED GRID CELLS`],
      ['orange', `${fmt(grid.high_priority_count)} HIGH-PRIORITY CELLS`],
      ['emerald', `${fmt(ov.day_detections)} DAY · ${fmt(ov.night_detections)} NIGHT`],
      ['cyan', `${fmt(grid.grid_size_degrees, 2)}° SPATIAL TESSELLATION`],
      ['crimson', `NASA FIRMS · VIIRS ${esc(sats)}`],
      ['emerald', `${range.toUpperCase()}`],
      ['cyan', 'GBIF · IUCN RED LIST'],
    ].map(([c, t]) => `<span class="tick"><i class="dot-${c}"></i>${t}</span>`).join('');
    $('#ticker-track').innerHTML = `<div class="ticker-group">${ticks}</div><div class="ticker-group" aria-hidden="true">${ticks}</div>`;

    const scores = a.top_hotspot_cells.map((c) => c.priority_score);
    const hourly = a.eda_results.temporal.hourly_detections || {};
    const hourVals = Object.keys(hourly).sort((x, y) => x - y).map((k) => hourly[k]);
    const kpis = [
      ['var(--crimson-400)', 'kpi-fire', '🔥', num(ov.total_records), '', 'Detections Analysed',
        `${fmt(ov.records_with_frp_percentage, 0)}% with FRP · confidence H/N/L ${fmt(ov.confidence_counts?.h)}/${fmt(ov.confidence_counts?.n)}/${fmt(ov.confidence_counts?.l)}`, dailyVals],
      ['var(--amber-400)', 'kpi-grid-cell', '🌐', num(grid.total_populated_cells), '', 'Populated Grid Cells',
        `${grid.grid_size_degrees}° cells with FRP aggregates`, scores.slice().reverse()],
      ['#fb923c', 'kpi-hotspot', '⚡', num(grid.high_priority_count), '', 'High-Priority Cells',
        top ? `Score ≥ 70 · top cell ${fmt(top.priority_score, 1)} / 100` : 'Score ≥ 70', scores.slice(0, 8).reverse()],
      ['var(--emerald-400)', 'kpi-species', '📅', peak ? num(peak[1]) : '—', '', 'Peak Day Detections',
        peak ? `on ${fmtDay(peak[0], { weekday: 'short', month: 'short', day: 'numeric' })}` : '', hourVals.filter(Boolean)],
      ['var(--cyan-400)', 'kpi-tests', '📈', frp?.available ? num(frp.outlier_count) : '—', '', 'FRP Outliers',
        frp?.available ? `${fmt(frp.outlier_percentage, 1)}% above ${fmt(frp.upper_fence, 1)} MW (Tukey fence)` : 'Re-run Part 2 analysis', frp?.histogram?.counts],
    ];
    $('#kpi-grid').innerHTML = kpis.map(([accent, icls, icon, value, suffix, label, sub, sp], i) => `
      <article class="kpi-card tilt" data-reveal data-delay="${i * 80}" style="--accent: ${accent};">
        <div class="kpi-sheen" aria-hidden="true"></div>
        <div class="kpi-icon-wrap ${icls}">${icon}</div>
        <div class="kpi-value">${value}${suffix}</div>
        <div class="kpi-label">${label}</div>
        <div class="kpi-subtext">${esc(sub)}</div>
        <div class="kpi-spark" aria-hidden="true">${spark(sp)}</div>
      </article>`).join('');

    renderFootprint(a.top_hotspot_cells, grid.grid_size_degrees || 0.25);
  }

  /* ---------------------------------------------------------------------
     01 Data quality
     --------------------------------------------------------------------- */
  function renderQuality(etl, a) {
    const box = $('#chart-funnel');
    if (!etl) { box.innerHTML = '<p class="empty">No ETL report found.</p>'; return; }
    const c = etl.counts;
    $('#etl-meta').textContent = `${etl.run_id} · ${fmt(etl.duration_seconds, 1)} s`;
    const max = c.raw_rows_extracted || 1;
    const rows = [
      ['Extracted from FIRMS', 'raw API rows', c.raw_rows_extracted, ''],
      ['Exact duplicates removed', 'pandas drop_duplicates', c.exact_duplicates_removed, 'bad'],
      ['Rejected during cleaning', 'bad coordinates / timestamps', c.cleaning_rejections, 'bad'],
      ['Rejected by Pydantic', 'schema validation', c.pydantic_rejections, 'bad'],
      ['Valid records', 'passed every check', c.valid_records, ''],
      null,
      ['Inserted into Supabase', 'new detection keys', c.inserted_records, ''],
      ['Skipped, already stored', 'same hash key from earlier run', c.skipped_existing_records, 'muted'],
      ['Rejections saved', 'rejected_records collection', c.saved_rejections, 'bad'],
    ];
    box.innerHTML = rows.map((r, idx) => {
      if (!r) return '<div class="funnel-divider"></div>';
      const [label, sub, v, cls] = r;
      return `<div class="funnel-row">
        <div class="f-label">${label}<small>${sub}</small></div>
        <div class="funnel-track">${v ? `<div class="funnel-bar ${cls}" style="width:${Math.max(pct(v, max), 0.6)}%;--i:${idx}"></div>` : ''}</div>
        <div class="f-value">${num(v)}</div></div>`;
    }).join('');

    const missing = a?.eda_results.distributions?.missing_values;
    $('#missing-table tbody').innerHTML = missing
      ? Object.entries(missing).map(([k, v]) => `<tr><td><code>${esc(k)}</code></td><td class="num">${fmt(v)}</td></tr>`).join('')
      : '<tr><td colspan="2">Re-run Part 2 analysis to compute.</td></tr>';

    const notes = [...(a?.eda_results.data_quality_notes || [])];
    if (etl && a) {
      notes.unshift(`Latest FIRMS pull returned ${fmt(c.raw_rows_extracted)} rows; the analysis covers ${fmt(a.eda_results.overview.total_records)} stored records in the ${a.eda_results.overview.unique_detection_dates_count}-day window.`);
    }
    $('#quality-notes').innerHTML = notes.map((n) => `<li>${esc(n)}</li>`).join('');
  }

  /* ---------------------------------------------------------------------
     02 Distributions
     --------------------------------------------------------------------- */
  function renderDistributions(a) {
    const dist = a.eda_results.distributions;
    const wrap = $('#dist-cards');
    if (!dist) {
      wrap.innerHTML = '<div class="chart-card"><p class="empty">Distribution profiles are missing from this report. Re-run Part 2 analysis.</p></div>';
    } else {
      const meta = {
        frp: ['Fire Radiative Power', 'MW', 'chip-crimson'],
        bright_ti4: ['Brightness I-4 (3.7 µm)', 'K', 'chip-amber'],
        bright_ti5: ['Brightness I-5 (11 µm)', 'K', 'chip-cyan'],
      };
      wrap.innerHTML = '';
      Object.entries(meta).forEach(([key, [title, unit, chip]], idx) => {
        const d = dist[key];
        const card = document.createElement('div');
        card.className = 'chart-card dist-card';
        card.setAttribute('data-reveal', '');
        card.setAttribute('data-delay', String(idx * 90));
        if (!d?.available) {
          card.innerHTML = `<div class="chart-card-header"><span class="chart-card-title">${title}</span></div><p class="empty">No data.</p>`;
          wrap.appendChild(card);
          return;
        }
        const skewWord = Math.abs(d.skewness) < 0.5 ? 'roughly symmetric' : d.skewness > 0 ? 'right-skewed' : 'left-skewed';
        card.innerHTML = `
          <div class="chart-card-header"><span class="chart-card-title">${title}</span><span class="chip ${chip}">n = ${fmt(d.count)}</span></div>
          <div class="chart"></div>
          <div class="dist-stats">
            <div><span>Median</span><b>${fmt(d.median, 1)}</b></div>
            <div><span>Mean</span><b>${fmt(d.mean, 1)}</b></div>
            <div><span>IQR</span><b>${fmt(d.iqr, 1)}</b></div>
            <div><span>Outliers</span><b>${fmt(d.outlier_count)}</b></div>
          </div>
          <p class="dist-note">${skewWord[0].toUpperCase() + skewWord.slice(1)} (skew ${fmt(d.skewness, 2)}) · ${fmt(d.outlier_percentage, 1)}% outliers · values in ${unit}.</p>`;
        wrap.appendChild(card);
        histogram($('.chart', card), d, unit);
      });
    }

    const conf = a.eda_results.sensors?.confidence_counts || a.eda_results.overview.confidence_counts || {};
    const order = [['h', 'High', 'var(--conf-h)'], ['n', 'Nominal', 'var(--conf-n)'], ['l', 'Low', 'var(--conf-l)']];
    const total = Object.values(conf).reduce((s, v) => s + v, 0);
    const present = order.filter(([k]) => conf[k]);
    const box = $('#chart-confidence');
    box.innerHTML = `
      <div class="stack-bar">${present.map(([k, n, col], i) =>
        `<div style="flex:${conf[k]};background:${col};--i:${i}" data-tip="<b>${n}</b><br>${fmt(conf[k])} detections · ${fmt(pct(conf[k], total), 1)}%"></div>`).join('')}</div>
      <div class="stack-legend">${present.map(([k, n, col]) =>
        `<span><i style="background:${col}"></i>${n} <b>${fmt(conf[k])}</b> · ${fmt(pct(conf[k], total), 1)}%</span>`).join('')}</div>`;
    $$('[data-tip]', box).forEach((el) => {
      el.addEventListener('mousemove', (e) => showTip(e, el.dataset.tip));
      el.addEventListener('mouseleave', hideTip);
    });
  }

  /* ---------------------------------------------------------------------
     03 Timing
     --------------------------------------------------------------------- */
  function renderTiming(a) {
    const t = a.eda_results.temporal;
    const days = Object.keys(t.daily_detections).sort();
    const total = days.reduce((s, d) => s + t.daily_detections[d], 0);
    columnChart($('#chart-daily'), {
      labels: days.map((d) => fmtDay(d)),
      series: [{ name: 'Detections', color: 'primary', values: days.map((d) => t.daily_detections[d]) }],
      labelValues: true,
      tipFor: (i) => `<b>${fmtDay(days[i], { weekday: 'short', month: 'short', day: 'numeric' })}</b><br>${fmt(t.daily_detections[days[i]])} detections · ${fmt(pct(t.daily_detections[days[i]], total), 1)}%`,
    });
    $('#trend-meta').textContent = t.trend_summary ? `Trend: ${t.trend_summary}` : 'Temporal Profile';
    $('#trend-text').textContent = t.trend_explanation || '';

    const hours = [...Array(24).keys()];
    const split = t.hourly_by_daynight;
    const series = split
      ? [
          { name: 'Day pass', color: 'day', values: hours.map((h) => split.D?.[h] || 0) },
          { name: 'Night pass', color: 'night', values: hours.map((h) => split.N?.[h] || 0) },
        ]
      : [{ name: 'Detections', color: 'primary', values: hours.map((h) => t.hourly_detections[h] || 0) }];
    $('#hour-legend').innerHTML = split
      ? series.map((s) => `<span><i style="background:var(--g-${s.color})"></i>${s.name}</span>`).join('')
      : '';
    columnChart($('#chart-hourly'), {
      labels: hours.map((h) => String(h).padStart(2, '0')),
      series,
      tickEvery: 3,
      tipFor: (i) => `<b>${String(i).padStart(2, '0')}:00 UTC</b> <span class="tt-muted">(${String((i + 20) % 24).padStart(2, '0')}:00 local)</span><br>` +
        series.map((s) => `${s.name}: ${fmt(s.values[i])}`).join('<br>'),
    });

    const dn = t.day_night_distribution || {};
    const day = dn.D || 0, night = dn.N || 0;
    const fd = a.eda_results.distributions?.frp_by_daynight || {};
    $('#daynight').innerHTML = [
      ['var(--g-day)', 'Day detections', num(day), `${fmt(pct(day, day + night), 1)}% of total`],
      ['var(--g-night)', 'Night detections', num(night), `${fmt(pct(night, day + night), 1)}% of total`],
      ['var(--g-day)', 'Median FRP, day', fd.D ? num(fd.D.median, 1, ' MW') : '—', fd.D ? `mean ${fmt(fd.D.mean, 1)} · max ${fmt(fd.D.max, 0)} MW` : ''],
      ['var(--g-night)', 'Median FRP, night', fd.N ? num(fd.N.median, 1, ' MW') : '—', fd.N ? `mean ${fmt(fd.N.mean, 1)} · max ${fmt(fd.N.max, 0)} MW` : ''],
    ].map(([c, l, v, s], i) => `<div class="dn-cell" data-reveal data-delay="${i * 70}"><div class="dn-label"><i style="background:${c};color:${c}"></i>${l}</div><div class="dn-value">${v}</div><div class="dn-sub">${s}</div></div>`).join('');
  }

  /* ---------------------------------------------------------------------
     04 Hotspots
     --------------------------------------------------------------------- */
  function scoreBar(score, color, i = 0) {
    return `<div class="scorebar"><div class="scorebar-track"><div class="scorebar-fill" style="width:${Math.min(100, score)}%;background:${color};--i:${i}"></div></div><b>${fmt(score, 1)}</b></div>`;
  }
  const badge = (label) => {
    const p = PRIORITY[label];
    return p ? `<span class="badge ${p.cls}"><i></i>${p.short}</span>` : `<span class="badge pending">${esc(label)}</span>`;
  };

  /** Mini map of the top-ranked grid cells; High cells pulse. Click jumps to the table row. */
  function renderFootprint(cells, size) {
    const box = $('#footprint');
    box.innerHTML = '';
    const pts = cells.map((c) => {
      const [lat, lon] = c.center_coordinates.split(',').map(Number);
      return { ...c, lat, lon };
    });
    if (!pts.length) return;
    const lats = pts.map((p) => p.lat), lons = pts.map((p) => p.lon);
    const pad = size * 0.75;
    const minLon = Math.min(...lons) - pad, maxLon = Math.max(...lons) + pad;
    const minLat = Math.min(...lats) - pad, maxLat = Math.max(...lats) + pad;
    const H = 220, W = Math.max(H, Math.round(H * (maxLon - minLon) / (maxLat - minLat)));
    const k = Math.min(W / (maxLon - minLon), H / (maxLat - minLat));
    const ox = (W - (maxLon - minLon) * k) / 2, oy = (H - (maxLat - minLat) * k) / 2;
    const X = (lon) => ox + (lon - minLon) * k;
    const Y = (lat) => oy + (maxLat - lat) * k;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', role: 'img', 'aria-label': 'Top hotspot cells' }, box);

    for (let lon = Math.floor(minLon / size) * size + size / 2; lon <= maxLon; lon += size) {
      for (let lat = Math.floor(minLat / size) * size + size / 2; lat <= maxLat; lat += size) {
        svgEl('circle', { class: 'grid-dot', cx: X(lon), cy: Y(lat), r: 1.2 }, svg);
      }
    }

    const s = Math.max(8, size * k - 3);
    [...pts].reverse().forEach((c, idx) => {
      const x = X(c.lon) - s / 2, y = Y(c.lat) - s / 2, fill = PRIORITY[c.priority_label]?.fill || '#475569';
      const g = svgEl('g', { class: 'cell-in', style: `--i:${pts.length - idx};color:${fill}` }, svg);
      if (c.priority_label === 'High Priority') svgEl('rect', { class: 'ring', x, y, width: s, height: s, rx: 3, stroke: fill }, g);
      const r = svgEl('rect', { class: 'cell', x, y, width: s, height: s, rx: 3, fill }, g);
      r.addEventListener('mousemove', (e) => showTip(e, `<b>#${c.rank} · ${cellName(c.grid_id)}</b><br>${esc(c.priority_label)} · score ${fmt(c.priority_score, 1)}<br>${fmt(c.detection_count)} detections · mean FRP ${fmt(c.mean_frp, 1)} MW`));
      r.addEventListener('mouseleave', hideTip);
      r.addEventListener('click', () => {
        hideTip();
        const row = document.getElementById(`row-${c.grid_id}`);
        if (!row) return;
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        row.classList.remove('flash'); void row.offsetWidth; row.classList.add('flash');
      });
    });
    $('#footprint-legend').innerHTML = Object.values(PRIORITY)
      .map((p) => `<span><i style="background:${p.fill}"></i>${p.short}</span>`).join('');
  }

  function renderHotspots(a) {
    const g = a.grid_metadata;
    const total = g.total_populated_cells || 1;
    const tiers = [
      ['high', 'High priority', g.high_priority_count, 'Score ≥ 70'],
      ['medium', 'Medium priority', g.medium_priority_count, 'Score 35 – 69.9'],
      ['low', 'Low priority', g.low_priority_count, 'Score < 35'],
    ];
    $('#priority-strip').innerHTML = tiers.map(([cls, label, n, rule], i) => `
      <div class="prio ${cls}" data-reveal data-delay="${i * 80}">
        <div class="prio-head"><span>${label}</span><span>${fmt(pct(n, total), 0)}%</span></div>
        <div class="prio-value">${num(n)}</div>
        <div class="prio-sub">${rule} · of ${fmt(total)} cells</div>
      </div>`).join('');

    $('#grid-meta').textContent = `${a.top_hotspot_cells.length} of ${fmt(total)} cells`;
    $('#hotspot-table tbody').innerHTML = a.top_hotspot_cells.map((c, i) => `
      <tr id="row-${esc(c.grid_id)}" title="${esc(c.score_explanation)}">
        <td class="num">${c.rank}</td>
        <td class="cell-id">${cellName(c.grid_id)}<small>${esc(c.grid_id)}</small></td>
        <td>${badge(c.priority_label)}</td>
        <td>${scoreBar(c.priority_score, PRIORITY[c.priority_label]?.color || 'var(--g-low)', i)}</td>
        <td class="num">${fmt(c.detection_count)}</td>
        <td class="num">${fmt(c.recent_count)}</td>
        <td class="num">${fmt(c.unique_dates)}</td>
        <td class="num">${c.mean_frp == null ? '—' : fmt(c.mean_frp, 1)}</td>
        <td class="num">${c.max_frp == null ? '—' : fmt(c.max_frp, 1)}</td>
      </tr>`).join('');

    const names = { frequency: 'Detection frequency', recency: 'Recent activity (48 h)', frp: 'Mean FRP', confidence: 'Confidence' };
    $('#weights').innerHTML = Object.entries(g.active_weights || {}).sort((x, y) => y[1] - x[1]).map(([k, w], i) => `
      <div class="weight-row"><span>${names[k] || esc(k)}</span>
        <div class="scorebar-track"><div class="scorebar-fill" style="width:${w * 100}%;--i:${i}"></div></div>
        <b>${fmt(w * 100)}%</b></div>`).join('');
  }

  /* ---------------------------------------------------------------------
     06 Biodiversity
     --------------------------------------------------------------------- */
  function renderBiodiversity(cons, stale) {
    $('#gbif-stale').hidden = !stale;
    if (!cons) {
      $('#gbif-stats').innerHTML = '<div class="stat"><div class="stat-label">No conservation report yet</div><div class="stat-sub">Run Part 3 to query GBIF.</div></div>';
      return;
    }
    const s = cons.summary_metrics;
    const stats = [
      ['var(--crimson-400)', 'Priority cells queried', s.priority_cells_considered, 'Medium + High fire cells'],
      ['var(--emerald-400)', 'GBIF occurrence records', s.gbif_occurrence_records_received, `animal records · ${fmt(s.gbif_requests_made)} API requests`],
      ['var(--cyan-400)', 'Unique animal species', s.unique_animal_species_found, 'deduplicated by taxon key'],
      ['var(--amber-400)', 'IUCN status verified', s.species_with_verified_iucn_status,
        cons.metadata.iucn_api_configured ? `${s.threatened_species_found} threatened` : 'IUCN token not configured'],
    ];
    $('#gbif-stats').innerHTML = stats.map(([accent, l, v, sub], i) =>
      `<div class="stat" data-reveal data-delay="${i * 70}" style="--accent:${accent}"><div class="stat-label">${l}</div><div class="stat-value">${num(v)}</div><div class="stat-sub">${esc(sub)}</div></div>`).join('');

    const pending = s.pending_iucn_verification_count;
    if (pending != null) {
      $('#method-pending-text').textContent = `Assigned when IUCN Red List verification has not yet run or is pending. Species exposure score is not calculated. (${fmt(pending)} species-cell summaries in the current run)`;
    }

    const cells = cons.cell_conservation_summaries || [];
    const maxSp = Math.max(1, ...cells.map((c) => c.total_species_recorded || 0));
    $('#gbif-meta').textContent = `GBIF run · ${fmtDateTime(cons.metadata.generated_at)}`;
    $('#gbif-table tbody').innerHTML = cells.map((c, i) => `
      <tr>
        <td class="cell-id">${cellName(c.grid_id)}<small>${esc(c.grid_id)}</small></td>
        <td>${badge(c.fire_priority_label)}</td>
        <td>${scoreBar(c.fire_priority_score, PRIORITY[c.fire_priority_label]?.color || 'var(--g-low)', i)}</td>
        <td class="num">${fmt(c.detection_count)}</td>
        <td><div class="species-bar"><div class="scorebar-track"><div class="scorebar-fill" style="width:${pct(c.total_species_recorded, maxSp)}%;--i:${i}"></div></div><b class="num">${fmt(c.total_species_recorded)}</b></div></td>
        <td><span class="badge pending">${esc((c.conservation_priority_label || '').replace(/ IUCN Verification$/, ''))}</span></td>
      </tr>`).join('');
  }

  /* ---------------------------------------------------------------------
     07 Figures + 08 Reports
     --------------------------------------------------------------------- */
  function renderFigures(figures, sources) {
    const tiles = [];
    for (const group of ['analysis', 'conservation']) {
      for (const file of figures[group] || []) {
        const key = file.replace(/\.png$/, '');
        const [name, tag] = FIGURE_NAMES[key] || [key.replace(/_/g, ' '), group];
        tiles.push({ src: `/figures/${group}/${file}`, name, tag, file, group });
      }
    }
    $('#figure-grid').innerHTML = tiles.length
      ? tiles.map((t, i) => `
        <div class="chart-card tilt" data-reveal data-delay="${(i % 2) * 90}">
          <div class="chart-card-header">
            <span class="chart-card-title">${esc(t.name)}</span>
            <span class="chip ${t.group === 'analysis' ? 'chip-amber' : 'chip-emerald'}">${esc(t.tag)}</span>
          </div>
          <div class="chart-card-body">
            <img src="${t.src}" alt="${esc(t.name)}" loading="lazy" data-zoom>
            <span class="expand-hint" aria-hidden="true">⤢ Enlarge</span>
          </div>
          <div class="chart-card-footer">${t.group === 'analysis' ? 'Part 2 analysis' : 'Part 3 biodiversity'} · ${esc(t.file)}</div>
        </div>`).join('')
      : '<div class="chart-card"><p class="empty">No figures generated yet. Run Part 2 analysis.</p></div>';
    $('#footer-sources').textContent = [sources.etl, sources.analysis, sources.conservation].filter(Boolean).join(' · ');
  }

  function renderReportMeta({ etl, analysis, conservation, conservation_stale: stale }) {
    const set = (kind, text) => { const el = $(`[data-meta="${kind}"]`); if (el) el.textContent = text; };
    const ov = analysis?.eda_results.overview;
    set('project', analysis ? `${fmt(ov.total_records)} detections · ${ov.unique_detection_dates_count} days · ~12 pages` : 'Run the analysis first');
    set('etl', etl ? `${etl.run_id} · ${fmtDateTime(etl.started_at)}` : 'No ETL run yet');
    set('analysis', analysis ? `Generated ${fmtDateTime(analysis.generated_at)}` : 'No analysis yet');
    set('biodiversity', conservation ? `${fmtDateTime(conservation.metadata.generated_at)}${stale ? ' · refresh pending' : ''}` : 'No GBIF run yet');
    $$('.report').forEach((card) => {
      const kind = card.dataset.kind;
      const ok = kind === 'etl' ? etl : kind === 'biodiversity' ? conservation : analysis;
      card.classList.toggle('disabled', !ok);
    });
  }

  /* ---------------------------------------------------------------------
     Image modal (delegated, so it covers figures rendered later)
     --------------------------------------------------------------------- */
  const modal = $('#image-modal');
  const modalImg = $('#modal-img');
  const modalCaption = $('#modal-caption');

  document.addEventListener('click', (e) => {
    const img = e.target.closest?.('.chart-card-body img[data-zoom]') ||
      e.target.closest?.('.chart-card-body')?.querySelector('img[data-zoom]');
    if (!img) return;
    modalImg.src = img.src;
    modalImg.alt = img.alt || 'Chart Preview';
    const title = img.closest('.chart-card')?.querySelector('.chart-card-title');
    modalCaption.textContent = title ? title.textContent : '';
    modal.classList.add('active');
  });
  const closeModal = () => modal.classList.remove('active');
  $('#modal-close').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

  /* ---------------------------------------------------------------------
     Map tabs / fullscreen / loading state
     --------------------------------------------------------------------- */
  const tabFire = $('#tab-fire');
  const tabConservation = $('#tab-conservation');
  const mapFrame = $('#map-frame');
  const openNewTabBtn = $('#open-map-new-tab');
  const mapContainer = $('#map-container');
  let currentMap = 'fire';

  function switchMap(type, bust = false) {
    currentMap = type;
    const isFire = type === 'fire';
    tabFire.classList.toggle('active', isFire);
    tabConservation.classList.toggle('active', !isFire);
    tabFire.setAttribute('aria-selected', String(isFire));
    tabConservation.setAttribute('aria-selected', String(!isFire));
    mapContainer.classList.remove('loaded');
    const src = isFire ? '/map/fire' : '/map/conservation';
    mapFrame.src = bust ? `${src}?t=${Date.now()}` : src;
    openNewTabBtn.href = src;
  }
  tabFire.addEventListener('click', () => switchMap('fire'));
  tabConservation.addEventListener('click', () => switchMap('conservation'));
  mapFrame.addEventListener('load', () => mapContainer.classList.add('loaded'));
  setTimeout(() => mapContainer.classList.add('loaded'), 6000);

  $('#toggle-fullscreen').addEventListener('click', () => {
    if (!document.fullscreenElement) {
      mapContainer.requestFullscreen().catch((err) => console.error(`Fullscreen error: ${err.message}`));
    } else {
      document.exitFullscreen();
    }
  });

  /* ---------------------------------------------------------------------
     Terminal console + pipeline runner
     --------------------------------------------------------------------- */
  const terminal = $('#terminal-output');
  const termStatus = $('#term-status');

  function setStatus(state, label) {
    termStatus.className = `term-status ${state || ''}`.trim();
    termStatus.lastChild.textContent = ` ${label}`;
  }

  function logTerminal(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    let prefix = `[${timestamp}] `;
    if (type === 'error') prefix += '✖ ERROR: ';
    else if (type === 'success') prefix += '✔ SUCCESS: ';
    else prefix += '› ';
    const line = document.createElement('span');
    line.className = `log-line log-${type}`;
    line.textContent = prefix + message;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
  }

  $('#clear-terminal').addEventListener('click', () => {
    terminal.textContent = 'ForestSentinel Console Ready. Select an action to execute.';
  });

  $$('.pipeline-run-btn').forEach((btn) => btn.addEventListener('click', async () => {
    const stage = btn.dataset.stage;
    const all = $$('.pipeline-run-btn');
    all.forEach((b) => { b.disabled = true; });
    btn.classList.add('is-running');
    setStatus('running', 'running');
    logTerminal(`Initiating pipeline execution: ${stage.toUpperCase()}...`);
    try {
      const response = await fetch(`/api/run/${stage}`, { method: 'POST' });
      const data = await response.json();
      if (data.error) {
        logTerminal(data.error, 'error');
        setStatus('error', 'failed');
      } else if (data.success) {
        logTerminal(`${data.script} finished\n${(data.output || '').trim()}`, 'success');
        logTerminal('Refreshing dashboard from the new reports...');
        await load();
        if (data.map_updated) switchMap(currentMap, true);
        setStatus('', 'idle');
      } else {
        logTerminal(`${data.script} exited with ${data.returncode}\n${(data.output || '').trim()}`, 'error');
        setStatus('error', 'failed');
      }
    } catch (err) {
      logTerminal(`Network / Server error: ${err.message}`, 'error');
      setStatus('error', 'failed');
    } finally {
      setTimeout(() => btn.classList.remove('is-running'), 400);
      all.forEach((b) => { b.disabled = false; });
    }
  }));

  /* ---------------------------------------------------------------------
     Load everything from the latest reports
     --------------------------------------------------------------------- */
  let booted = false;
  async function load() {
    try {
      const res = await fetch('/api/dashboard', { cache: 'no-store' });
      const data = await res.json();
      const { etl, analysis, conservation } = data;

      renderHeroMeta(etl);
      $('#load-error').hidden = !!analysis;
      renderQuality(etl, analysis);
      renderFigures(data.figures, data.sources);
      renderReportMeta(data);
      if (analysis) {
        renderLead(etl, analysis);
        renderDistributions(analysis);
        renderTiming(analysis);
        renderHotspots(analysis);
      }
      renderBiodiversity(conservation, data.conservation_stale);

      if (!booted) {
        booted = true;
        if (etl) logTerminal(`Connected to Supabase project: ${etl.database_project || etl.firebase_project_id}`);
        if (analysis) {
          const ov = analysis.eda_results.overview;
          logTerminal(`Loaded ${fmt(ov.total_records)} detections across ${fmt(analysis.grid_metadata.total_populated_cells)} grid cells (${data.sources.analysis}).`);
        }
        if (conservation) {
          const s = conservation.summary_metrics;
          logTerminal(`Biodiversity layer: ${fmt(s.unique_animal_species_found)} species from ${fmt(s.gbif_occurrence_records_received)} GBIF records.`);
        }
        logTerminal('Ready for operator commands.');
      }
    } catch (err) {
      console.error(err);
      $('#load-error').hidden = false;
      logTerminal(`Could not load reports: ${err.message}`, 'error');
    } finally {
      enhance();
      revealVisibleSoon();
      onScroll();
    }
  }

  enhance();
  load();
});
