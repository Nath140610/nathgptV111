(() => {
  'use strict';

  const PRICE_PER_TOKEN_EUR = 0.00000892;
  const $ = (id) => document.getElementById(id);

  const paths = {
    'arrow-up': '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
    message: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6M10 10v6m4-6v6"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    logout: '<path d="M10 17l5-5-5-5m5 5H3"/><path d="M12 3h6a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3h-6"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    paperclip: '<path d="m21.4 11.6-8.8 8.8a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5m-4 0h8"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    sparkles: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8L19 17ZM4 2l.6 1.4L6 4l-1.4.6L4 6l-.6-1.4L2 4l1.4-.6L4 2Z"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2.5"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    'eye-off': '<path d="M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.6M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2M2 2l20 20"/>',
  };
  function icon(name, size = 18) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ''}</svg>`;
  }
  document.querySelectorAll('[data-icon]').forEach((node) => { node.innerHTML = icon(node.dataset.icon, Number(node.dataset.size) || 18); });
  const island = window.NathGPTIsland;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // iOS ne réduit pas 100dvh quand le clavier s'ouvre : l'interface suit le viewport visible.
  const visualViewport = window.visualViewport;
  if (visualViewport) {
    const syncViewport = () => {
      if (visualViewport.scale > 1.01) return; // zoom manuel : ne pas déformer l'interface
      const root = document.documentElement;
      root.style.setProperty('--app-height', `${Math.round(visualViewport.height)}px`);
      root.style.setProperty('--vv-top', `${Math.round(visualViewport.offsetTop)}px`);
      root.classList.toggle('keyboard-open', window.innerHeight - visualViewport.height > 120);
    };
    visualViewport.addEventListener('resize', syncViewport);
    visualViewport.addEventListener('scroll', syncViewport);
    syncViewport();
  }
  const voiceTrigger = document.createElement('button');
  voiceTrigger.id = 'voice-trigger';
  voiceTrigger.className = 'voice-trigger';
  voiceTrigger.type = 'button';
  voiceTrigger.setAttribute('aria-label', 'Parler à NathGPT');
  voiceTrigger.title = 'Parler à NathGPT';
  voiceTrigger.innerHTML = icon('mic', 18);
  document.querySelector('.send-metal').before(voiceTrigger);
  document.getElementById('mode-menu').insertAdjacentHTML('beforeend', '<button data-mode="Image">Image</button>');
  const modeWarning = document.createElement('div');
  modeWarning.className = 'mode-warning';
  modeWarning.setAttribute('role', 'alert');
  modeWarning.hidden = true;
  document.querySelector('.composer').after(modeWarning);

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
  const displayAssistantContent = (value) => String(value ?? '').replace(/^\s*(?:\*\*ChatGPT said:\*\*|(?:\*\*)?ChatGPT said(?:\*\*)?\s*:)[ \t\r\n]*/i, '');
  function classifyPrompt(value) {
    const prompt = String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[’']/g, ' ');
    const imageObject = '(?:images?|photos?|illustrations?|dessins?|portraits?|logos?|visuels?|affiches?|icones?|peintures?)';
    const imageAction = '(?:genere|generer|cree|creer|dessine|dessiner|fais|fait|faire|produis|produire|realise|realiser|fabrique|fabriquer|concois|concevoir|montre|montrer)';
    const asksHow = /\b(?:comment|explique|expliquer|tutoriel|guide|apprends|apprendre)\b/.test(prompt);
    const imageActionMatch = prompt.match(new RegExp(`\\b${imageAction}\\b.{0,80}\\b${imageObject}\\b`));
    const actionTargetsImage = imageActionMatch && !/\b(?:poeme|poesie|histoire|recette|blague|email|mail|lettre|article|texte|exercice)\b/.test(imageActionMatch[0]);
    const image = /^\s*\/(?:image|imagine)\b/.test(prompt)
      || (!asksHow && (actionTargetsImage
        || /\b(?:dessine|dessiner)\b/.test(prompt)
        || new RegExp(`^\\s*(?:(?:une?|des?)\\s+)?${imageObject}\\b`).test(prompt)
        || new RegExp(`\\b(?:je veux|je voudrais|j aimerais|montre moi)\\s+(?:une?|des?)?\\s*${imageObject}\\b`).test(prompt)));
    const text = /\b(?:explique|expliquer|ecris|ecrire|redige|rediger|raconte|raconter|traduis|traduire|resume|resumer|calcule|calculer|resous|resoudre|reponds|repondre|analyse|analyser|compare|comparer|definis|definir|code|coder|programme|programmer)\b/.test(prompt)
      || /\b(?:poeme|poesie|histoire|recette|blague|email|mail|lettre|article|texte|exercice)\b/.test(prompt)
      || /^\s*(?:bonjour|salut|hello|ping|qui|que|quoi|comment|pourquoi|quand|combien|est ce que)\b/.test(prompt)
      || (!image && prompt.includes('?'));
    return { image, text };
  }
  function modeMismatch(selectedMode, content) {
    const intent = classifyPrompt(content);
    if (selectedMode !== 'Image' && intent.image) return 'Image';
    if (selectedMode === 'Image' && !intent.image && intent.text) return 'Chat';
    return null;
  }
  function formatAssistantContent(value, prompt = '') {
    const text = displayAssistantContent(value);
    if (!text || /\r|\n/.test(text) || /(^|\n)\s*(?:#{1,6}\s|[-*+]\s|\d+\.\s|>|```|~~~|\|)/m.test(text)) return text;

    if (text.length >= 120 && /\b(?:po[eè]me|po[eé]sie|vers)\b/i.test(prompt)) {
      const titled = text.replace(/^(.{3,80}✨)\s+(?=\p{Lu})/u, '$1\n\n');
      const separator = titled.indexOf('\n\n');
      const title = separator >= 0 ? titled.slice(0, separator) : '';
      const body = separator >= 0 ? titled.slice(separator + 2) : titled;
      const lines = body.split(/(?<=[,.!?…])\s+(?=\p{Lu})/gu).map((line) => line.trim()).filter(Boolean);
      if (lines.length >= 4) {
        const stanzas = [];
        for (let index = 0; index < lines.length; index += 4) stanzas.push(lines.slice(index, index + 4).join('\n'));
        return `${title ? `${title}\n\n` : ''}${stanzas.join('\n\n')}`;
      }
    }

    if (text.length < 220) return text;
    const sentences = text.split(/(?<=[.!?…])\s+(?=\p{Lu}|[«"“])/gu);
    if (sentences.length < 2) return text;
    const paragraphs = [];
    let paragraph = '';
    for (const sentence of sentences) {
      if (paragraph && paragraph.length >= 110 && paragraph.length + sentence.length > 230) {
        paragraphs.push(paragraph);
        paragraph = sentence;
      } else paragraph = paragraph ? `${paragraph} ${sentence}` : sentence;
    }
    if (paragraph) paragraphs.push(paragraph);
    return paragraphs.join('\n\n');
  }
  function formattedMessage(chat, message) {
    const index = chat.messages.indexOf(message);
    const prompt = index > 0 && chat.messages[index - 1].role === 'user' ? chat.messages[index - 1].content : '';
    return formatAssistantContent(message.content, prompt);
  }
  const readJSON = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const writeJSON = (key, value) => localStorage.setItem(key, JSON.stringify(value));
  const randomHex = (bytes = 16) => Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (byte) => byte.toString(16).padStart(2, '0')).join('');
  const newId = () => crypto.randomUUID?.() || randomHex(16);
  const chatKey = (key) => `nathgpt.chats.v1.${key}`;
  const estimateTokens = (value) => {
    const bytes = new TextEncoder().encode(String(value ?? '')).length;
    return bytes ? Math.max(1, Math.ceil(bytes / 4)) : 0;
  };
  // Le compteur d'économies est tenu par le serveur (Supabase) ; il renvoie le total après chaque réponse.
  function renderUsageCost() {
    const tokens = Number.isSafeInteger(account?.tokensUsed) ? account.tokensUsed : 0;
    const euros = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(tokens * PRICE_PER_TOKEN_EUR);
    $('usage-cost').textContent = `${account?.usageEstimated ? '≈ ' : ''}${euros} €`;
    $('usage-cost').title = 'Voir les économies estimées depuis la création du compte';
    $('usage-token-count').textContent = `${tokens.toLocaleString('fr-FR')} tokens ${account?.usageEstimated ? 'estimés' : 'comptés'} × 0,00000892 € par token`;
  }
  function closeUsageInfo() {
    $('usage-info').hidden = true;
    $('usage-cost').setAttribute('aria-expanded', 'false');
  }
  function recordUsage(key, prompt, answer, done) {
    if (account?.key !== key) return;
    if (Number.isSafeInteger(done?.account_tokens_used)) {
      account.tokensUsed = done.account_tokens_used;
      account.usageEstimated = Boolean(done.usage_estimated);
    } else {
      const exact = Number.isSafeInteger(done?.total_tokens) && done.total_tokens >= 0;
      account.tokensUsed += exact ? done.total_tokens : estimateTokens(prompt) + estimateTokens(answer);
      account.usageEstimated = account.usageEstimated || !exact;
    }
    renderUsageCost();
  }
  const restoreChats = (key) => readJSON(chatKey(key), []).map((chat) => ({ ...chat, messages: chat.messages.map((message) => message.state === 'streaming' ? { ...message, state: 'done', error: 'Réponse interrompue.' } : message) }));
  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(serverError(response.status, payload.detail));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  // Historique : copie locale immédiate, puis envoi au serveur pour le retrouver sur tous les appareils.
  const dirtyChats = new Set();
  let syncTimer = 0;
  function scheduleSync(delay = 800) { clearTimeout(syncTimer); syncTimer = setTimeout(flushChats, delay); }
  async function flushChats() {
    const key = account?.key;
    let failed = false;
    for (const id of [...dirtyChats]) {
      dirtyChats.delete(id);
      const chat = chats.find((item) => item.id === id);
      if (!chat || account?.key !== key) continue;
      const messages = chat.messages.filter((message) => message.state !== 'streaming');
      try {
        await api(`/api/conversations/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ title: chat.title, messages, created_at: messages[0]?.createdAt || chat.updatedAt, updated_at: chat.updatedAt }) });
      } catch (error) {
        if (error.status !== 403 && error.status !== 400) { dirtyChats.add(id); failed = true; }
      }
    }
    if (failed) scheduleSync(15000);
  }
  async function syncConversations() {
    const key = account?.key;
    try {
      const { conversations = [] } = await api('/api/conversations');
      if (account?.key !== key || pendingRequest) return;
      const merged = new Map(chats.map((chat) => [chat.id, chat]));
      for (const remote of conversations) {
        const local = merged.get(remote.id);
        if (!local || (remote.updated_at || 0) > (local.updatedAt || 0)) merged.set(remote.id, { id: remote.id, title: remote.title || 'Conversation', messages: remote.messages || [], updatedAt: remote.updated_at || Date.now() });
      }
      const remoteIds = new Set(conversations.map((remote) => remote.id));
      for (const chat of chats) if (!remoteIds.has(chat.id) && chat.messages.length) dirtyChats.add(chat.id);
      chats = [...merged.values()].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
      writeJSON(chatKey(key), chats);
      renderAll();
      if (dirtyChats.size) scheduleSync(200);
    } catch { /* hors ligne : la copie locale reste utilisable */ }
  }

  let account = null;
  let chats = [];
  let activeId = null;
  let attachments = [];
  let authMode = 'signup';
  let mode = 'Agent';
  let openMenu = '';
  let pendingRequest = null;
  let recognition = null;
  let voiceActive = false;
  let voiceShouldSend = false;
  let voiceFailure = false;
  let voiceBaseDraft = '';
  let voiceTranscript = '';
  const statusLabels = {
    working: 'Réfléchit…', searching: 'Recherche…', solving: 'Résout…',
    listening: 'Écoute…', connecting: 'Se connecte…', weaving: 'Assemble…',
    composing: 'Rédige…', breathing: 'En attente', shaping: 'Structure…',
  };
  function hideModeWarning() {
    modeWarning.hidden = true;
    modeWarning.replaceChildren();
  }
  function showModeWarning(targetMode) {
    const explanation = document.createElement('p');
    const action = document.createElement('button');
    action.type = 'button';
    action.dataset.switchMode = targetMode;
    if (targetMode === 'Image') {
      explanation.textContent = 'Pour générer une image, ouvre le menu de mode dans la barre de saisie et choisis « Image ». Ton message reste saisi.';
      action.textContent = 'Activer le mode Image';
    } else {
      explanation.textContent = 'Le mode Image est réservé aux demandes d’image. Pour une réponse texte, choisis « Chat » ou « Agent » dans le menu de mode. Ton message reste saisi.';
      action.textContent = 'Passer au mode Chat';
    }
    modeWarning.replaceChildren(explanation, action);
    modeWarning.hidden = false;
  }
  modeWarning.addEventListener('click', (event) => {
    const button = event.target.closest('[data-switch-mode]');
    if (button) setMode(button.dataset.switchMode);
  });

  function showAuth() {
    $('app-shell').hidden = true;
    $('auth-page').hidden = false;
    restartAnimation($('auth-card'), 'auth-enter');
    updatePseudoState();
    updateStrength();
    // Sur téléphone, pas de focus automatique : le clavier cacherait la carte.
    if (!matchMedia('(pointer: coarse)').matches) $('pseudo').focus();
  }
  function showApp() {
    $('auth-page').hidden = true;
    $('app-shell').hidden = false;
    $('profile-name').textContent = account.pseudo;
    $('avatar').textContent = account.pseudo[0].toUpperCase();
    $('welcome-name').textContent = account.pseudo;
    renderUsageCost();
    renderAll();
  }
  function startSession(data) {
    account = { key: data.key, pseudo: data.pseudo, tokensUsed: Number(data.tokens_used) || 0, usageEstimated: Boolean(data.usage_estimated) };
    chats = restoreChats(account.key);
    activeId = null;
    dirtyChats.clear();
    showApp();
    syncConversations();
  }
  function restartAnimation(node, className) {
    node.classList.remove(className);
    void node.offsetWidth;
    node.classList.add(className);
  }
  function showAuthError(message) {
    $('auth-error').textContent = message;
    $('auth-error').hidden = !message;
    if (message) restartAnimation($('auth-card'), 'shake');
  }
  const strengthLabels = ['8 caractères minimum', 'Faible', 'Moyen', 'Bon', 'Excellent'];
  function passwordLevel(value) {
    if (value.length < 8) return 0;
    const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(value)).length;
    return Math.min(4, 1 + Number(value.length >= 12) + Number(kinds >= 3) + Number(kinds === 4 || value.length >= 16));
  }
  function updateStrength() {
    const value = $('password').value;
    const level = passwordLevel(value);
    $('password-strength').dataset.level = String(level);
    $('strength-label').textContent = level === 0 && value ? `${value.length}/8 caractères` : strengthLabels[level];
  }
  function updatePseudoState() {
    const pseudo = $('pseudo').value.trim();
    const valid = pseudo.length >= 3 && pseudo.length <= 24;
    $('pseudo-state').classList.toggle('is-valid', valid);
    $('pseudo-hint').classList.remove('is-warning');
    $('pseudo-hint').textContent = pseudo && !valid ? `${pseudo.length}/24 · 3 caractères minimum` : '3 à 24 caractères';
  }
  function setPasswordVisible(visible) {
    $('password').type = visible ? 'text' : 'password';
    $('toggle-password').setAttribute('aria-pressed', String(visible));
    $('toggle-password').setAttribute('aria-label', visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe');
    $('toggle-password').innerHTML = icon(visible ? 'eye-off' : 'eye', 18);
  }
  function setAuthMode(next) {
    authMode = next;
    showAuthError('');
    $('password').value = '';
    setPasswordVisible(false);
    $('auth-card').dataset.mode = next;
    for (const tab of document.querySelectorAll('[data-auth-mode]')) tab.setAttribute('aria-selected', String(tab.dataset.authMode === next));
    $('password').autocomplete = next === 'signup' ? 'new-password' : 'current-password';
    $('password').placeholder = next === 'signup' ? '8 caractères minimum' : 'Votre mot de passe';
    $('auth-title').textContent = next === 'signup' ? 'Créer votre compte' : 'Bon retour';
    $('auth-subtitle').textContent = next === 'signup' ? 'Un pseudo, un mot de passe. C’est tout.' : 'Retrouvez votre espace de conversation.';
    $('auth-submit').querySelector('.auth-submit-label').textContent = next === 'signup' ? 'Créer mon compte' : 'Se connecter';
    restartAnimation($('auth-title'), 'auth-swap');
    restartAnimation($('auth-subtitle'), 'auth-swap');
    updatePseudoState();
    updateStrength();
  }
  document.querySelectorAll('[data-auth-mode]').forEach((tab) => tab.addEventListener('click', () => { if (tab.dataset.authMode !== authMode) setAuthMode(tab.dataset.authMode); }));
  $('pseudo').addEventListener('input', () => { updatePseudoState(); if (!$('auth-error').hidden) $('auth-error').hidden = true; });
  $('password').addEventListener('input', () => { updateStrength(); if (!$('auth-error').hidden) $('auth-error').hidden = true; });
  $('toggle-password').addEventListener('click', () => { setPasswordVisible($('password').type === 'password'); $('password').focus(); });
  $('auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    showAuthError('');
    const pseudo = $('pseudo').value.trim();
    const password = $('password').value;
    if (pseudo.length < 3 || pseudo.length > 24) return showAuthError('Le pseudo doit contenir entre 3 et 24 caractères.');
    if (password.length < 8) return showAuthError('Le mot de passe doit contenir au moins 8 caractères.');
    const submit = $('auth-submit');
    const label = submit.querySelector('.auth-submit-label');
    const signup = authMode === 'signup';
    submit.disabled = true;
    submit.classList.add('is-loading');
    label.textContent = signup ? 'Création…' : 'Connexion…';
    try {
      const data = await api(signup ? '/api/auth/signup' : '/api/auth/login', { method: 'POST', body: JSON.stringify({ pseudo, password }) });
      $('password').value = '';
      submit.classList.remove('is-loading');
      submit.classList.add('is-success');
      label.textContent = signup ? 'Compte créé' : 'Connecté';
      island?.flash({ size: 'expanded', leading: 'logo', tone: 'success', title: `Bonjour, ${data.account.pseudo}`, text: signup ? 'Votre compte est prêt. Bienvenue sur NathGPT !' : 'Content de vous revoir.', haptic: true }, 3200);
      await wait(520);
      $('auth-card').classList.add('is-leaving');
      await wait(280);
      startSession(data.account);
    } catch (error) { showAuthError(error.message || 'Connexion au serveur impossible. Réessayez.'); }
    finally {
      submit.disabled = false;
      submit.classList.remove('is-loading', 'is-success');
      $('auth-card').classList.remove('is-leaving');
      label.textContent = authMode === 'signup' ? 'Créer mon compte' : 'Se connecter';
    }
  });

  function saveChats(changedId) {
    if (!account) return;
    writeJSON(chatKey(account.key), chats);
    if (changedId) { dirtyChats.add(changedId); scheduleSync(); }
  }
  function shortDate(timestamp) {
    const date = new Date(timestamp);
    if (date.toDateString() === new Date().toDateString()) return 'Aujourd’hui';
    return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' }).format(date);
  }
  function renderSidebar() {
    const query = $('search-input').value.toLocaleLowerCase('fr-FR');
    const filtered = chats.filter((chat) => chat.title.toLocaleLowerCase('fr-FR').includes(query));
    $('chat-list').innerHTML = filtered.length ? filtered.map((chat) => `<div class="chat-row ${activeId === chat.id ? 'active' : ''}"><button data-select-chat="${escapeHtml(chat.id)}" title="${escapeHtml(chat.title)}">${icon('message', 16)}<span>${escapeHtml(chat.title)}</span></button><button class="delete-chat" data-delete-chat="${escapeHtml(chat.id)}" title="Supprimer la conversation" aria-label="Supprimer ${escapeHtml(chat.title)}">${icon('trash', 15)}</button></div>`).join('') : `<p class="empty-list">${query ? 'Aucun résultat' : 'Vos conversations apparaîtront ici.'}</p>`;
  }
  function renderWorkspace() {
    window.NathGPTOrbs?.unmountAll();
    window.NathGPTRings?.unmountAll();
    const chat = chats.find((item) => item.id === activeId);
    $('topbar-title-text').textContent = chat ? chat.title : 'NathGPT';
    $('welcome').hidden = Boolean(chat);
    $('messages').hidden = !chat;
    $('workspace').classList.toggle('is-empty', !chat);
    $('workspace').classList.toggle('has-chat', Boolean(chat));
    if (!chat) { $('messages').innerHTML = ''; return; }
    const nearBottom = $('messages').scrollHeight - $('messages').scrollTop - $('messages').clientHeight < 110;
    $('messages').innerHTML = `<div class="conversation-date">${shortDate(chat.updatedAt)}</div>${chat.messages.map((message) => {
      if (message.role === 'assistant') {
        const thinking = message.state === 'streaming';
        const isImage = thinking && message.task === 'image';
        const visual = isImage ? '<div class="image-processing-ring" data-image-ring="processing" aria-label="Traitement en cours"></div>' : `<div class="assistant-orb" data-thinking-orb="${thinking ? (message.content ? 'composing' : 'working') : 'breathing'}" aria-label="Statut de NathGPT"></div>`;
        const status = thinking ? `<div class="assistant-status">${isImage ? 'Traitement de la demande…' : (message.content ? 'Rédige…' : 'Réfléchit…')}</div>` : '';
        const displayContent = formattedMessage(chat, message);
        const content = displayContent ? `<div class="message-text assistant-markdown">${window.NathGPTMarkdown?.render(displayContent) || escapeHtml(displayContent)}</div>` : '';
        const error = message.error ? `<div class="message-error" role="alert">${escapeHtml(message.error)}</div>` : '';
        const copy = message.content && !thinking ? `<button class="copy-answer" data-copy-message="${escapeHtml(message.id)}" type="button" aria-label="Copier la réponse">${icon('copy', 14)} Copier</button>` : '';
        return `<div class="message-row assistant-message ${isImage ? 'image-processing-message' : ''}" data-message-id="${escapeHtml(message.id)}">${visual}<div class="message-body">${status}${content}${error}${copy}</div></div>`;
      }
      return `<div class="message-row user-message"><span class="message-avatar">${escapeHtml(account.pseudo[0].toUpperCase())}</span><div class="message-body"><div class="message-author">Vous</div>${message.content ? `<div class="message-text">${escapeHtml(message.content)}</div>` : ''}${message.attachments?.length ? `<div class="message-files">${message.attachments.map((file) => `<span>${icon('file', 16)} ${escapeHtml(file.name)}</span>`).join('')}</div>` : ''}</div></div>`;
    }).join('')}`;
    window.NathGPTOrbs?.mountAll();
    window.NathGPTRings?.mountAll();
    if (nearBottom) $('messages').scrollTop = $('messages').scrollHeight;
  }
  function renderAttachments() {
    $('attachments').hidden = attachments.length === 0;
    $('attachments').innerHTML = attachments.map((file, index) => `<span>${icon('paperclip', 14)}${escapeHtml(file.name)}<button data-remove-file="${index}" aria-label="Retirer ${escapeHtml(file.name)}">${icon('x', 13)}</button></span>`).join('');
    updateSendButton();
  }
  function renderAll() { renderSidebar(); renderWorkspace(); renderAttachments(); }
  function updateSendButton() {
    $('send-button').disabled = !pendingRequest && !$('message-input').value.trim();
    $('send-button').setAttribute('aria-label', pendingRequest ? 'Arrêter la réponse' : 'Envoyer le message');
    $('send-button').title = pendingRequest ? 'Arrêter la réponse' : 'Envoyer le message';
    $('send-button').innerHTML = pendingRequest ? '<span class="stop-symbol"></span>' : icon('arrow-up', 19);
  }
  function closeSidebar() { $('sidebar').classList.remove('sidebar-open'); $('sidebar-scrim').hidden = true; }
  function newChat() {
    activeId = null; attachments = []; $('message-input').value = '';
    hideModeWarning();
    renderAll(); closeSidebar(); $('message-input').focus();
  }
  async function* parseSSE(stream) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '', eventName = 'message', data = [];
    const dispatch = () => {
      if (!data.length) { eventName = 'message'; return null; }
      const event = { event: eventName, data: data.join('\n') };
      eventName = 'message'; data = [];
      return event;
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        if (buffer.length > 1_000_000) throw new Error('Réponse trop volumineuse.');
        let match;
        while ((match = /\r\n|\r|\n/.exec(buffer)) && (done || match.index + match[0].length < buffer.length || match[0] !== '\r')) {
          const line = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          if (!line) { const event = dispatch(); if (event) yield event; }
          else if (!line.startsWith(':')) {
            const colon = line.indexOf(':');
            const field = colon < 0 ? line : line.slice(0, colon);
            const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
            if (field === 'event') eventName = value || 'message';
            if (field === 'data') data.push(value);
          }
        }
        if (done) {
          if (buffer.startsWith('data:')) data.push(buffer.slice(5).replace(/^ /, ''));
          const event = dispatch(); if (event) yield event;
          return;
        }
      }
    } finally { reader.releaseLock(); }
  }
  function serverError(status, detail) {
    if (typeof detail === 'string' && detail) return detail;
    if (status === 401) return 'Session expirée. Reconnectez-vous.';
    if (status === 429) return 'NathGPT est occupé. Réessayez dans un instant.';
    if (status === 504) return 'NathGPT a mis trop de temps à répondre.';
    return 'Impossible de contacter NathGPT.';
  }
  function updateAssistant(chat, message) {
    if (chat.id !== activeId) return;
    const nearBottom = $('messages').scrollHeight - $('messages').scrollTop - $('messages').clientHeight < 110;
    const row = [...$('messages').querySelectorAll('[data-message-id]')].find((node) => node.dataset.messageId === message.id);
    if (row && message.state === 'streaming') {
      let body = row.querySelector('.assistant-markdown');
      if (!body) { body = document.createElement('div'); body.className = 'message-text assistant-markdown'; row.querySelector('.message-body').append(body); }
      const displayContent = formattedMessage(chat, message);
      body.innerHTML = window.NathGPTMarkdown?.render(displayContent) || escapeHtml(displayContent);
      const status = row.querySelector('.assistant-status'); if (status && message.content) status.textContent = 'Rédige…';
      if (nearBottom) $('messages').scrollTop = $('messages').scrollHeight;
      return;
    }
    renderWorkspace();
  }
  async function sendMessage() {
    const content = $('message-input').value.trim();
    if (!content || pendingRequest) return;
    const requiredMode = modeMismatch(mode, content);
    if (requiredMode) { showModeWarning(requiredMode); return; }
    hideModeWarning();
    const accountKey = account.key;
    const now = Date.now();
    const id = activeId || newId();
    const imageTask = mode === 'Image';
    const message = { id: newId(), role: 'user', content, task: imageTask ? 'image' : 'chat', attachments: attachments.map((file) => ({ name: file.name, size: file.size })), createdAt: now };
    const assistant = { id: newId(), role: 'assistant', content: '', task: message.task, state: 'streaming', createdAt: now };
    const existing = chats.find((chat) => chat.id === id);
    const title = content.split('\n')[0].slice(0, 45);
    const updated = existing ? { ...existing, messages: [...existing.messages, message, assistant], updatedAt: now } : { id, title, messages: [message, assistant], updatedAt: now };
    chats = [updated, ...chats.filter((chat) => chat.id !== id)];
    activeId = id;
    saveChats(id);
    $('message-input').value = ''; attachments = [];
    renderAll(); closeMenu(); $('message-input').focus();
    const controller = new AbortController();
    pendingRequest = controller;
    updateSendButton();
    const startedAt = Date.now();
    island?.setActivity({
      id: 'reply', leading: imageTask ? 'image' : 'orb', startedAt,
      label: imageTask ? 'Création de l’image…' : 'NathGPT réfléchit…',
      title: imageTask ? 'Création de l’image' : 'NathGPT réfléchit', text: title, preview: '',
      actions: [{ label: 'Arrêter', tone: 'danger', onSelect: () => controller.abort() }],
    });
    let writing = false;
    try {
      const response = await fetch('/api/chat', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ prompt: content, conversation_id: id, stream: true }), signal: controller.signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(serverError(response.status, payload.detail));
      }
      if (!response.body) throw new Error('Ce navigateur ne prend pas en charge le streaming.');
      let completed = false;
      let donePayload = {};
      for await (const event of parseSSE(response.body)) {
        let payload;
        try { payload = JSON.parse(event.data); } catch { continue; }
        if (event.event === 'delta') assistant.content += String(payload.text || '');
        else if (event.event === 'replace') assistant.content = String(payload.text || '');
        else if (event.event === 'error') throw new Error(serverError(502, payload.message));
        else if (event.event === 'done') {
          donePayload = payload || {};
          completed = true;
          break;
        }
        else continue;
        updateAssistant(updated, assistant);
        const visible = displayAssistantContent(assistant.content).replace(/[#*_`>|~-]+/g, ' ').replace(/\s+/g, ' ').trim();
        if (visible && !writing) {
          writing = true;
          island?.update({ label: 'NathGPT écrit…', title: 'NathGPT écrit', trailingGlyph: 'wave' });
        }
        island?.update({ preview: visible.length > 150 ? `…${visible.slice(-150)}` : visible });
      }
      if (!completed) throw new Error('La réponse a été interrompue.');
      if (!displayAssistantContent(assistant.content).trim()) throw new Error('NathGPT a renvoyé une réponse vide.');
      recordUsage(accountKey, content, assistant.content, donePayload);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      const words = displayAssistantContent(assistant.content).trim().split(/\s+/).length;
      island?.setActivity(null);
      island?.flash({
        size: 'expanded', leading: 'check', tone: 'success', haptic: true,
        title: 'Réponse prête', text: `${words.toLocaleString('fr-FR')} mot${words > 1 ? 's' : ''} · ${seconds} s`,
        onTap: () => { if (activeId === id) $('messages').scrollTop = $('messages').scrollHeight; },
      }, 2600);
    } catch (error) {
      assistant.error = error.name === 'AbortError' ? 'Réponse arrêtée.' : (error.message || 'Connexion interrompue.');
      island?.setActivity(null);
      if (error.name === 'AbortError') island?.flash({ leading: 'stop', label: 'Réponse arrêtée' }, 1600);
      else island?.flash({ size: 'expanded', leading: 'error', tone: 'error', haptic: 'error', title: 'Réponse impossible', text: assistant.error }, 4200);
    } finally {
      assistant.state = 'done';
      pendingRequest = null;
      saveChats(updated.id); updateAssistant(updated, assistant); updateSendButton();
    }
  }
  function showVoiceError(message) {
    $('voice-error').textContent = message;
    $('voice-error').hidden = !message;
  }
  function enterCallFullscreen() {
    try { $('voice-panel').requestFullscreen?.()?.catch?.(() => {}); } catch { /* l'interface couvre déjà la fenêtre */ }
  }
  function leaveCallFullscreen() {
    if (document.fullscreenElement !== $('voice-panel')) return;
    try { document.exitFullscreen?.()?.catch?.(() => {}); } catch { /* fermeture visuelle déjà effectuée */ }
  }
  function setVoiceDirection(direction) {
    const value = Math.max(-1, Math.min(1, Number(direction) || 0));
    document.querySelectorAll('[data-call-direction]').forEach((button) => {
      const selected = Number(button.dataset.callDirection) === value;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    window.NathGPTRings?.setCallDirection(value);
  }
  function finishVoice() {
    if (!voiceActive) return;
    const shouldSend = voiceShouldSend;
    const spoken = voiceTranscript.trim();
    voiceActive = false;
    voiceShouldSend = false;
    recognition = null;
    island?.setActivity(null);
    window.NathGPTVoice?.stop();
    window.NathGPTRings?.setCallState('idle');
    $('voice-panel').classList.remove('is-listening');
    if (voiceFailure) {
      $('voice-transcript').textContent = 'Dictée interrompue';
      $('voice-finish').disabled = true;
      return;
    }
    $('voice-panel').hidden = true;
    leaveCallFullscreen();
    window.NathGPTRings?.unmountCallRing();
    $('voice-finish').disabled = false;
    if (shouldSend && spoken) {
      $('message-input').value = [voiceBaseDraft, spoken].filter(Boolean).join(' ');
      $('message-input').dispatchEvent(new Event('input', { bubbles: true }));
      sendMessage();
    } else $('message-input').focus();
  }
  function cancelVoice() {
    voiceShouldSend = false;
    if (recognition) { try { recognition.abort(); } catch { /* déjà arrêtée */ } }
    voiceFailure = false;
    finishVoice();
    window.NathGPTVoice?.stop();
    window.NathGPTRings?.unmountCallRing();
    $('voice-panel').hidden = true;
    leaveCallFullscreen();
    $('voice-panel').classList.remove('is-listening');
    $('voice-finish').disabled = false;
  }
  function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    $('voice-panel').hidden = false;
    enterCallFullscreen();
    window.NathGPTRings?.mountCallRing();
    window.NathGPTRings?.setCallState('listening');
    setVoiceDirection(0);
    $('voice-transcript').textContent = 'Je vous écoute…';
    $('voice-hint').textContent = 'Parlez en français, puis terminez pour envoyer. La transcription peut utiliser le service vocal du navigateur.';
    showVoiceError('');
    if (!SpeechRecognition || !window.NathGPTVoice?.supported || !navigator.mediaDevices?.getUserMedia) {
      $('voice-transcript').textContent = 'Dictée indisponible';
      $('voice-hint').textContent = 'Ouvrez le site sur localhost dans un navigateur compatible.';
      $('voice-finish').disabled = true;
      showVoiceError('Ce navigateur ne prend pas en charge la reconnaissance vocale et le microphone sur cette page.');
      return;
    }
    voiceActive = true;
    voiceShouldSend = true;
    voiceFailure = false;
    island?.setActivity({
      id: 'voice', leading: 'mic', trailingGlyph: 'wave', tone: 'live', label: 'Écoute…',
      title: 'NathGPT vous écoute', text: 'Parlez, puis envoyez.',
      actions: [{ label: 'Annuler', onSelect: cancelVoice }, { label: 'Envoyer', tone: 'primary', onSelect: () => $('voice-finish').click() }],
    });
    $('voice-panel').classList.add('is-listening');
    window.NathGPTRings?.setCallState('listening');
    voiceTranscript = '';
    voiceBaseDraft = $('message-input').value.trim();
    recognition = new SpeechRecognition();
    recognition.lang = 'fr-FR';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      voiceTranscript = Array.from(event.results, (result) => result[0]?.transcript || '').join(' ').trim();
      $('voice-transcript').textContent = voiceTranscript || 'Je vous écoute…';
    };
    recognition.onerror = (event) => {
      voiceShouldSend = false;
      voiceFailure = true;
      const errors = { 'not-allowed': 'Autorisez le microphone pour utiliser la dictée.', 'audio-capture': 'Aucun microphone disponible.', network: 'La transcription vocale du navigateur est indisponible.' };
      showVoiceError(errors[event.error] || 'La dictée vocale a été interrompue.');
    };
    recognition.onend = finishVoice;
    try {
      const microphone = window.NathGPTVoice.start();
      microphone.then((stream) => {
        if (!stream && voiceActive) {
          voiceShouldSend = false;
          voiceFailure = true;
          showVoiceError('Impossible d’accéder au microphone. Vérifiez son autorisation.');
          recognition?.abort();
        }
      }).catch(() => { if (voiceActive) { voiceShouldSend = false; voiceFailure = true; recognition?.abort(); } });
      recognition.start();
    } catch {
      voiceShouldSend = false;
      voiceFailure = true;
      showVoiceError('Impossible de démarrer la dictée vocale.');
      finishVoice();
    }
  }
  window.NathGPT = { stop() { pendingRequest?.abort(); } };

  $('new-chat').addEventListener('click', newChat);
  $('topbar-new').addEventListener('click', newChat);
  $('chat-list').addEventListener('click', (event) => {
    const select = event.target.closest('[data-select-chat]');
    const remove = event.target.closest('[data-delete-chat]');
    if (select) { activeId = select.dataset.selectChat; renderAll(); closeSidebar(); }
    if (remove) {
      const removedId = remove.dataset.deleteChat;
      chats = chats.filter((chat) => chat.id !== removedId); if (activeId === removedId) activeId = null;
      dirtyChats.delete(removedId); saveChats(); renderAll();
      api(`/api/conversations/${encodeURIComponent(removedId)}`, { method: 'DELETE' }).catch(() => {});
    }
  });
  $('search-toggle').addEventListener('click', () => { $('search-input').hidden = !$('search-input').hidden; if (!$('search-input').hidden) $('search-input').focus(); else { $('search-input').value = ''; renderSidebar(); } });
  $('search-input').addEventListener('input', renderSidebar);
  $('message-input').addEventListener('input', () => { const input = $('message-input'); input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 180)}px`; hideModeWarning(); updateSendButton(); });
  $('message-input').addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendMessage(); } });
  $('send-button').addEventListener('click', () => { if (pendingRequest) pendingRequest.abort(); else sendMessage(); });
  $('usage-cost').addEventListener('click', () => {
    const opening = $('usage-info').hidden;
    closeMenu();
    $('usage-info').hidden = !opening;
    $('usage-cost').setAttribute('aria-expanded', String(opening));
  });
  document.addEventListener('pointerdown', (event) => { if (!event.target.closest('.usage-wrap')) closeUsageInfo(); });
  $('messages').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-message]');
    if (!button) return;
    const chat = chats.find((item) => item.id === activeId);
    const message = chat?.messages.find((item) => item.id === button.dataset.copyMessage);
    if (!message?.content) return;
    try { await navigator.clipboard.writeText(formattedMessage(chat, message)); button.textContent = 'Copié'; island?.flash({ leading: 'check', label: 'Réponse copiée' }, 1500); setTimeout(() => { button.innerHTML = `${icon('copy', 14)} Copier`; }, 1600); }
    catch { button.textContent = 'Copie indisponible'; }
  });
  voiceTrigger.addEventListener('click', startVoice);
  $('voice-finish').addEventListener('click', () => { if (recognition && voiceActive) { $('voice-finish').disabled = true; recognition.stop(); } });
  $('voice-cancel').addEventListener('click', cancelVoice);
  document.querySelector('.voice-direction-preview').addEventListener('click', (event) => {
    const button = event.target.closest('[data-call-direction]');
    if (button) setVoiceDirection(button.dataset.callDirection);
  });
  $('add-file').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', (event) => { attachments = [...attachments, ...Array.from(event.target.files || [])].slice(0, 5); event.target.value = ''; renderAttachments(); });
  $('attachments').addEventListener('click', (event) => { const button = event.target.closest('[data-remove-file]'); if (button) { attachments.splice(Number(button.dataset.removeFile), 1); renderAttachments(); } });
  $('open-sidebar').addEventListener('click', () => { $('sidebar').classList.add('sidebar-open'); $('sidebar-scrim').hidden = false; });
  $('close-sidebar').addEventListener('click', closeSidebar);
  $('sidebar-scrim').addEventListener('click', closeSidebar);

  function closeMenu() {
    openMenu = '';
    for (const name of ['profile', 'mode']) { $(`${name}-menu`).hidden = true; $(`${name}-button`).setAttribute('aria-expanded', 'false'); }
  }
  function setMode(next) {
    if (!['Agent', 'Chat', 'Image'].includes(next)) return;
    if (next !== mode) island?.flash({ leading: next === 'Image' ? 'image' : 'sparkles', label: `Mode ${next}` }, 1400);
    mode = next;
    $('mode-label').textContent = next;
    hideModeWarning();
    closeMenu();
    $('message-input').focus();
  }
  function toggleMenu(name) { const next = openMenu === name ? '' : name; closeMenu(); closeUsageInfo(); if (next) { openMenu = next; $(`${next}-menu`).hidden = false; $(`${next}-button`).setAttribute('aria-expanded', 'true'); } }
  for (const name of ['profile', 'mode']) $(`${name}-button`).addEventListener('click', () => toggleMenu(name));
  document.addEventListener('pointerdown', (event) => { if (openMenu && !event.target.closest('[data-menu]')) closeMenu(); });
  $('mode-menu').addEventListener('click', (event) => { const button = event.target.closest('[data-mode]'); if (button) setMode(button.dataset.mode); });
  $('logout-button').addEventListener('click', () => {
    pendingRequest?.abort();
    hideModeWarning();
    closeUsageInfo();
    clearTimeout(syncTimer);
    if (dirtyChats.size) flushChats();
    api('/api/session/logout', { method: 'POST' }).catch(() => {});
    account = null; chats = []; activeId = null; dirtyChats.clear(); closeMenu(); showAuth();
    island?.setActivity(null);
    island?.flash({ leading: 'user', label: 'Déconnecté' }, 1500);
  });
  window.addEventListener('beforeunload', () => pendingRequest?.abort());
  window.addEventListener('offline', () => island?.flash({ size: 'expanded', leading: 'offline', tone: 'error', haptic: 'error', title: 'Hors connexion', text: 'Vérifiez votre réseau.' }, 3600));
  window.addEventListener('online', () => island?.flash({ leading: 'check', label: 'De retour en ligne' }, 1800));
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && account) { event.preventDefault(); newChat(); }
    if (event.key === 'Escape') {
      if (!$('voice-panel').hidden) { event.preventDefault(); cancelVoice(); }
      else { closeMenu(); closeUsageInfo(); closeSidebar(); }
    }
  });
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && !$('voice-panel').hidden) cancelVoice();
  });

  // La session est un cookie httpOnly : on demande au serveur quel compte est connecté.
  api('/api/auth/me')
    .then((data) => {
      startSession(data.account);
      island?.flash({ leading: 'logo', label: `Bonjour, ${data.account.pseudo}` }, 2200);
    })
    .catch(() => showAuth());
})();
