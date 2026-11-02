/* NathGPT Dynamic Island — version JavaScript native du composant React DynamicIsland.
 *
 * Même comportement que <motion.div layout> : pilule noire, origine en haut au centre,
 * ressort { stiffness: 110, damping: 12 }. Sur les iPhone à Dynamic Island ouverts
 * depuis l'écran d'accueil, la pilule se superpose exactement à l'île matérielle.
 *
 * API : window.NathGPTIsland.setActivity(état | null), .update(champs), .flash(état, ms)
 * Tailles (active) : idle, compact, expanded, large.
 */
(() => {
  'use strict';

  const SPRING = { stiffness: 110, damping: 12, mass: 1 };
  // Écrans CSS (portrait) des iPhone à Dynamic Island : 14 Pro → 17 Pro Max, Air.
  // Les modèles plus récents (18 Pro…) sont reconnus par leur zone sûre supérieure.
  const ISLAND_SCREENS = new Set(['393x852', '430x932', '402x874', '440x956', '420x912']);
  const CUTOUT = { width: 126, height: 37 };
  // Largeur de chaque côté de l'île matérielle en mode compact : évite l'heure et la batterie.
  const SIDE = 44;
  const FLOATING = { idleWidth: 125, height: 40 }; // min-w-[125px] min-h-10

  function springTransition({ stiffness, damping, mass }) {
    const w0 = Math.sqrt(stiffness / mass);
    const zeta = damping / (2 * Math.sqrt(stiffness * mass));
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    const position = (t) => 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + (zeta * w0 / wd) * Math.sin(wd * t));
    const duration = Math.log(200) / (zeta * w0);
    const steps = 48;
    const points = Array.from({ length: steps + 1 }, (_, index) => Number(position((index / steps) * duration).toFixed(4)));
    points[steps] = 1;
    const easing = `linear(${points.join(', ')})`;
    if (window.CSS?.supports?.('transition-timing-function', easing)) return { easing, duration: Math.round(duration * 1000) };
    return { easing: 'cubic-bezier(.32, 1.42, .56, 1)', duration: 560 };
  }

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
  const svg = (body) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  const glyphs = {
    orb: '<span class="di-glyph di-orb"></span>',
    image: '<span class="di-glyph di-image-glyph"></span>',
    wave: '<span class="di-glyph di-wave"><i></i><i></i><i></i><i></i><i></i></span>',
    check: '<span class="di-glyph di-check"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11"/><path d="m7 12.5 3.2 3.2L17 9"/></svg></span>',
    error: '<span class="di-glyph di-alert">!</span>',
    logo: '<span class="di-glyph di-logo"><img src="logo.png" alt=""></span>',
    mic: `<span class="di-glyph di-icon di-mic">${svg('<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5"/>')}</span>`,
    offline: `<span class="di-glyph di-icon di-offline">${svg('<path d="m2 2 20 20M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 5.2-2.8M19 13a10 10 0 0 0-2-1.6M2 8.8a15 15 0 0 1 4.2-2.7M22 8.8A15 15 0 0 0 10.7 5"/><circle cx="12" cy="20" r=".6"/>')}</span>`,
    sparkles: `<span class="di-glyph di-icon di-sparkles">${svg('<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z"/>')}</span>`,
    stop: '<span class="di-glyph di-stop"><i></i></span>',
    bell: `<span class="di-glyph di-icon di-bell">${svg('<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15Z"/><path d="M10 20a2 2 0 0 0 4 0"/>')}</span>`,
    user: `<span class="di-glyph di-icon">${svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>')}</span>`,
  };
  const formatElapsed = (startedAt) => {
    const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  };

  class DynamicIsland {
    constructor() {
      this.spring = springTransition(SPRING);
      this.activity = null;
      this.transient = null;
      this.transientTimer = 0;
      this.expanded = false;
      this.key = '';
      this.layer = null;
      this.tick = 0;
      this.flashCount = 0;

      this.el = document.createElement('div');
      this.el.className = 'dynamic-island is-hidden';
      this.el.setAttribute('role', 'status');
      this.el.setAttribute('aria-live', 'polite');
      this.el.dataset.active = 'idle';
      this.el.style.setProperty('--di-ease', this.spring.easing);
      this.el.style.setProperty('--di-duration', `${this.spring.duration}ms`);
      document.body.append(this.el);

      this.probe = document.createElement('div');
      this.probe.className = 'di-safe-probe';
      document.body.append(this.probe);

      this.el.addEventListener('click', (event) => this.onClick(event));
      document.addEventListener('pointerdown', (event) => {
        if (this.expanded && !this.el.contains(event.target)) { this.expanded = false; this.apply(); }
      });
      let frame = 0;
      const relayout = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { this.measure(); this.apply(); }); };
      window.addEventListener('resize', relayout);
      window.addEventListener('orientationchange', relayout);
      matchMedia('(display-mode: standalone)').addEventListener?.('change', relayout);

      this.measure();
      this.apply();
    }

    measure() {
      const safeTop = this.probe.offsetHeight || 0;
      const portrait = window.innerHeight >= window.innerWidth;
      const isIPhone = /iPhone/.test(navigator.userAgent);
      const screenKey = `${Math.min(screen.width, screen.height)}x${Math.max(screen.width, screen.height)}`;
      const standalone = navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
      if (portrait && safeTop) this.portraitSafeTop = safeTop;
      const islandPhone = isIPhone && (ISLAND_SCREENS.has(screenKey) || (this.portraitSafeTop || 0) >= 51);
      // L'île matérielle n'est atteignable que si la page s'affiche sous la barre d'état.
      this.hardware = islandPhone && standalone && portrait && safeTop >= 51;
      this.top = this.hardware ? Math.max(8, (safeTop - CUTOUT.height) / 2) : safeTop + 8;
      this.el.dataset.mode = this.hardware ? 'hardware' : 'floating';
      this.el.style.setProperty('--di-cutout-w', `${CUTOUT.width}px`);
      this.el.style.setProperty('--di-cutout-h', `${CUTOUT.height}px`);
      const root = document.documentElement.classList;
      root.toggle('is-iphone', isIPhone);
      root.toggle('has-dynamic-island', islandPhone);
      root.toggle('has-hardware-island', this.hardware);
    }

    displayed() {
      if (this.transient) return this.transient;
      if (!this.activity) return null;
      return this.expanded ? { ...this.activity, size: 'large' } : this.activity;
    }

    render(state, size) {
      const tone = state.tone ? ` di-tone-${state.tone}` : '';
      const lead = glyphs[state.leading] || '';
      const timer = state.startedAt ? `<span class="di-text" data-slot="timer">${formatElapsed(state.startedAt)}</span>` : '';
      if (size === 'compact') {
        const trailing = state.trailingGlyph ? glyphs[state.trailingGlyph] : (state.trailingText != null ? `<span class="di-text" data-slot="trailingText">${escapeHtml(state.trailingText)}</span>` : timer);
        return `<div class="di-compact${tone}">${lead}<span class="di-label" data-slot="label">${escapeHtml(state.label || '')}</span><span class="di-trailing">${trailing}</span></div>`;
      }
      const preview = state.preview != null ? `<p class="di-preview" data-slot="preview">${escapeHtml(state.preview)}</p>` : '';
      const actions = state.actions?.length ? `<div class="di-actions">${state.actions.map((action, index) => `<button type="button" class="${action.tone ? `di-${escapeHtml(action.tone)}` : ''}" data-island-action="${index}">${escapeHtml(action.label)}</button>`).join('')}</div>` : '';
      const trailing = state.trailingGlyph && size !== 'large' ? glyphs[state.trailingGlyph] : timer;
      return `<div class="di-expanded${tone}"><div class="di-x-lead">${lead}</div><div class="di-x-main"><strong data-slot="title">${escapeHtml(state.title || state.label || '')}</strong>${state.text ? `<p data-slot="text">${escapeHtml(state.text)}</p>` : ''}${preview}</div><div class="di-x-trail">${trailing}</div>${actions}</div>`;
    }

    apply() {
      const state = this.displayed();
      const size = state?.size || 'idle';
      const key = state ? `${state.id}|${size}` : 'idle';
      const html = state ? this.render(state, size) : '';
      const viewport = document.documentElement.clientWidth || window.innerWidth;

      if (key !== this.key) {
        const old = this.layer;
        if (old) {
          old.classList.add('di-leave');
          setTimeout(() => old.remove(), 260);
        }
        this.layer = document.createElement('div');
        this.layer.className = 'di-layer di-enter';
        this.layer.innerHTML = html;
        this.el.append(this.layer);
        this.key = key;
      } else if (this.layer && this.layer.innerHTML !== html) {
        this.layer.innerHTML = html;
      }

      let width;
      let height;
      let radius;
      if (size === 'idle') {
        width = this.hardware ? CUTOUT.width : FLOATING.idleWidth;
        height = this.hardware ? CUTOUT.height : 37;
      } else if (size === 'compact') {
        if (this.hardware) width = CUTOUT.width + SIDE * 2;
        else {
          this.layer.style.width = 'max-content';
          width = Math.min(viewport - 24, Math.max(160, Math.ceil(this.layer.offsetWidth)));
        }
        height = this.hardware ? CUTOUT.height : FLOATING.height;
      } else {
        width = Math.min(viewport - 16, 380);
      }
      this.layer.style.width = `${width}px`;
      if (height == null) height = Math.ceil(this.layer.offsetHeight);
      radius = size === 'expanded' || size === 'large' ? Math.min(42, height / 2) : height / 2;

      this.el.style.width = `${width}px`;
      this.el.style.height = `${height}px`;
      this.el.style.borderRadius = `${radius}px`;
      this.el.style.top = `${this.top}px`;
      this.el.dataset.active = size;
      this.el.classList.toggle('is-hidden', size === 'idle' && !this.hardware);
      // Le CSS peut libérer la place sous l'île flottante (titre de la barre du haut).
      document.documentElement.classList.toggle('island-visible', size !== 'idle' && !this.hardware);
      this.el.classList.toggle('is-interactive', Boolean(state && (state.onTap || state.actions?.length || this.activity)));
      this.el.setAttribute('aria-label', state ? [state.title || state.label, state.text].filter(Boolean).join(' — ') : 'NathGPT');
      // La lecture de offsetWidth/offsetHeight a fixé l'état de départ : l'entrée peut s'animer.
      this.layer.classList.remove('di-enter');
    }

    onClick(event) {
      const state = this.displayed();
      if (!state) return;
      const actionButton = event.target.closest('[data-island-action]');
      if (actionButton) {
        event.stopPropagation();
        state.actions?.[Number(actionButton.dataset.islandAction)]?.onSelect?.();
        return;
      }
      if (this.transient) {
        const tap = this.transient.onTap;
        this.dismiss();
        tap?.();
        return;
      }
      if (this.activity) {
        this.expanded = !this.expanded;
        this.apply();
      }
    }

    setActivity(state) {
      this.activity = state ? { size: 'compact', ...state } : null;
      if (!state) this.expanded = false;
      clearInterval(this.tick);
      if (this.activity?.startedAt) {
        this.tick = setInterval(() => {
          if (!this.activity?.startedAt) return;
          const text = formatElapsed(this.activity.startedAt);
          this.el.querySelectorAll('.di-layer:not(.di-leave) [data-slot="timer"]').forEach((node) => { node.textContent = text; });
        }, 1000);
      }
      this.apply();
    }

    // Met à jour le texte (aperçu, libellé…) sans animation ; un changement d'icône redessine.
    update(patch) {
      if (!this.activity) return;
      const visual = ['leading', 'trailingGlyph', 'trailingText', 'actions', 'size', 'tone', 'id'].some((name) => name in patch && patch[name] !== this.activity[name]);
      Object.assign(this.activity, patch);
      if (visual) { this.apply(); return; }
      if (this.transient || !this.layer) return;
      for (const [name, value] of Object.entries(patch)) {
        const node = this.layer.querySelector(`[data-slot="${name}"]`);
        if (node) node.textContent = String(value ?? '');
      }
      if (this.displayed()?.size === 'compact' && !this.hardware && 'label' in patch) this.apply();
    }

    flash(state, duration = 2600) {
      clearTimeout(this.transientTimer);
      this.transient = { size: 'compact', ...state, id: state.id || `flash-${++this.flashCount}` };
      if (state.haptic) navigator.vibrate?.(state.haptic === 'error' ? [12, 60, 12] : 10);
      this.apply();
      this.transientTimer = setTimeout(() => this.dismiss(), duration);
    }

    dismiss() {
      clearTimeout(this.transientTimer);
      if (!this.transient) return;
      this.transient = null;
      this.apply();
    }
  }

  const start = () => { window.NathGPTIsland = new DynamicIsland(); };
  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });
})();
