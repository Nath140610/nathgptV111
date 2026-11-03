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
    scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
    power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
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
  let preparingFiles = false;
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
    $('admin-button').hidden = !account.isAdmin;
    $('cricut-button').hidden = !account.cricut;
    renderUsageCost();
    renderAll();
  }
  function startSession(data) {
    account = { key: data.key, pseudo: data.pseudo, tokensUsed: Number(data.tokens_used) || 0, usageEstimated: Boolean(data.usage_estimated), isAdmin: data.is_admin === true, cricut: data.cricut === true };
    chats = restoreChats(account.key);
    activeId = null;
    dirtyChats.clear();
    showApp();
    syncConversations();
    setTimeout(askForNotifications, 4200);
    ensurePushSubscription();
    // Ouverture depuis une notification push (« Tes stickers sont prêts »).
    const params = new URLSearchParams(location.search);
    if (params.get('view') === 'cricut') {
      history.replaceState(null, '', location.pathname);
      openCricut();
    }
  }

  // Notifications : prévenir quand une réponse ou une image est prête et que l'app est en arrière-plan.
  const NOTIF_SNOOZE_KEY = 'nathgpt.notifications.snooze';
  const isAppleDevice = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function snoozeNotifications(days) { localStorage.setItem(NOTIF_SNOOZE_KEY, String(Date.now() + days * 86400000)); }
  function notificationBanner(title, text, actions) {
    document.querySelector('.notif-banner')?.remove();
    const banner = document.createElement('div');
    banner.className = 'notif-banner';
    banner.setAttribute('role', 'dialog');
    banner.innerHTML = `<strong>${escapeHtml(title)}</strong><p>${escapeHtml(text)}</p><div class="notif-actions"></div>`;
    for (const action of actions) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = action.label;
      if (action.primary) button.className = 'is-primary';
      button.addEventListener('click', () => { banner.remove(); action.onSelect(); });
      banner.querySelector('.notif-actions').append(button);
    }
    document.body.append(banner);
  }
  function askForNotifications(force = false) {
    if (!account || !('Notification' in window) || Notification.permission === 'granted') return;
    if (!force && Date.now() < Number(localStorage.getItem(NOTIF_SNOOZE_KEY) || 0)) return;
    if (Notification.permission === 'denied') {
      notificationBanner('Notifications bloquées',
        isAppleDevice ? 'Active-les dans Réglages › Notifications › NathGPT.' : 'Autorise-les dans les réglages du site (icône à gauche de l’adresse).',
        [{ label: 'Compris', primary: true, onSelect: () => snoozeNotifications(1) }]);
      return;
    }
    notificationBanner('Activer les notifications ?', 'NathGPT te prévient quand une réponse ou une image est prête.', [
      { label: 'Plus tard', onSelect: () => snoozeNotifications(3) },
      { label: 'Activer', primary: true, onSelect: () => {
        // Appel direct dans le toucher : obligatoire pour que le navigateur affiche sa demande.
        Promise.resolve(Notification.requestPermission()).then((result) => {
          if (result === 'granted') ensurePushSubscription();
          else { snoozeNotifications(1); askForNotifications(); }
        });
      } },
    ]);
  }
  async function notifyIfHidden(title, body, chatId) {
    if (document.visibilityState !== 'hidden' || !('Notification' in window) || Notification.permission !== 'granted') return;
    const options = { body: body || 'Touchez pour ouvrir NathGPT.', icon: '/logo.png', badge: '/logo.png', tag: chatId, data: { chatId } };
    try {
      const registration = await navigator.serviceWorker?.getRegistration();
      if (registration) await registration.showNotification(title, options);
      else new Notification(title, options);
    } catch { /* notifications indisponibles sur cet appareil */ }
  }
  navigator.serviceWorker?.register('/sw.js').catch(() => {});
  navigator.serviceWorker?.addEventListener('message', (event) => {
    if (event.data?.type === 'open-view' && event.data.view === 'cricut') { openCricut(); return; }
    const chatId = event.data?.type === 'open-chat' ? event.data.chatId : '';
    if (chatId && chats.some((chat) => chat.id === chatId)) { activeId = chatId; renderAll(); }
  });
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
        const images = renderImages(message);
        const copy = message.content && !thinking ? `<button class="copy-answer" data-copy-message="${escapeHtml(message.id)}" type="button" aria-label="Copier la réponse">${icon('copy', 14)} Copier</button>` : '';
        return `<div class="message-row assistant-message ${isImage ? 'image-processing-message' : ''}" data-message-id="${escapeHtml(message.id)}">${visual}<div class="message-body">${status}${content}${images}${error}${copy}</div></div>`;
      }
      return `<div class="message-row user-message"><span class="message-avatar">${escapeHtml(account.pseudo[0].toUpperCase())}</span><div class="message-body"><div class="message-author">Vous</div>${message.content ? `<div class="message-text">${escapeHtml(message.content)}</div>` : ''}${message.attachments?.length ? `<div class="message-files">${message.attachments.map((file) => `<span>${icon('file', 16)} ${escapeHtml(file.name)}</span>`).join('')}</div>` : ''}</div></div>`;
    }).join('')}`;
    window.NathGPTOrbs?.mountAll();
    window.NathGPTRings?.mountAll();
    if (nearBottom) $('messages').scrollTop = $('messages').scrollHeight;
  }
  function safeImages(message) {
    return (Array.isArray(message.images) ? message.images : []).filter((image) => /^\/api\/images\/[a-f0-9]{32}\.(png|jpg|webp)$/.test(image?.url || ''));
  }
  function renderImages(message) {
    const images = safeImages(message);
    if (!images.length) return '';
    return `<div class="message-images">${images.map((image, index) => `<figure class="generated-image"><a href="${escapeHtml(image.url)}" target="_blank" rel="noopener"><img src="${escapeHtml(image.url)}" alt="Image générée ${index + 1}" loading="lazy"></a><a class="image-download" href="${escapeHtml(image.url)}" download="${escapeHtml(image.filename || `nathgpt-${index + 1}.png`)}">${icon('arrow-up', 14)} Télécharger</a></figure>`).join('')}<p class="image-ttl">Image gardée 24 h : télécharge-la pour la conserver.</p></div>`;
  }
  // Images de plus d'un jour : supprimées du serveur, on affiche un encart à la place d'une image cassée.
  document.addEventListener('error', (event) => {
    const figure = event.target instanceof HTMLImageElement ? event.target.closest('.generated-image') : null;
    if (!figure || figure.classList.contains('is-expired')) return;
    figure.classList.add('is-expired');
    figure.innerHTML = `<div class="image-expired">${icon('file', 20)}<span>Image expirée</span><small>Les images sont gardées 24 h.</small></div>`;
  }, true);
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
    if (!content || pendingRequest || preparingFiles) return;
    const requiredMode = modeMismatch(mode, content);
    if (requiredMode) { showModeWarning(requiredMode); return; }
    hideModeWarning();
    const accountKey = account.key;
    const now = Date.now();
    const id = activeId || newId();
    const imageTask = mode === 'Image';
    const sending = attachments;
    let files;
    preparingFiles = true;
    try { files = await encodeFiles(sending); }
    catch (error) { showComposerError(error.message); return; }
    finally { preparingFiles = false; }
    const message = { id: newId(), role: 'user', content, task: imageTask ? 'image' : 'chat', attachments: sending.map((file) => ({ name: file.name, size: file.size })), createdAt: now };
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
    let donePayload = {};
    try {
      const response = await fetch('/api/chat', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ prompt: content, conversation_id: id, request_id: assistant.id, stream: true, mode: imageTask ? 'Image' : mode, ...(files.length ? { files } : {}) }), signal: controller.signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw serverFailure(serverError(response.status, payload.detail));
      }
      if (!response.body) throw new Error('Ce navigateur ne prend pas en charge le streaming.');
      let completed = false;
      for await (const event of parseSSE(response.body)) {
        let payload;
        try { payload = JSON.parse(event.data); } catch { continue; }
        if (event.event === 'delta') assistant.content += String(payload.text || '');
        else if (event.event === 'replace') assistant.content = String(payload.text || '');
        else if (event.event === 'image') {
          assistant.images = [...safeImages(assistant), { url: String(payload.url || ''), filename: String(payload.filename || '') }];
          if (updated.id === activeId) renderWorkspace();
          continue;
        }
        else if (event.event === 'error') throw serverFailure(serverError(502, payload.message));
        else if (event.event === 'done') {
          donePayload = payload || {};
          completed = true;
          break;
        }
        else continue;
        updateAssistant(updated, assistant);
      }
      if (!completed) throw new Error('La réponse a été interrompue.');
      await finishReply();
    } catch (error) {
      if (error.name === 'AbortError') assistant.error = 'Réponse arrêtée.';
      else if (error.fromServer) assistant.error = error.message;
      else {
        // Connexion coupée (« Load failed », app en arrière-plan…) : le serveur a continué, on récupère la réponse.
        try {
          const result = await recoverReply(assistant.id, controller.signal, (partial) => applyResult(partial));
          if (!result) throw error;
          applyResult(result);
          if (result.error) throw serverFailure(serverError(502, result.error.message));
          donePayload = result.done || {};
          await finishReply();
        } catch (failure) {
          assistant.error = failure.name === 'AbortError' ? 'Réponse arrêtée.' : (failure.message || 'Connexion interrompue.');
        }
      }
    } finally {
      assistant.state = 'done';
      pendingRequest = null;
      saveChats(updated.id); updateAssistant(updated, assistant); updateSendButton();
    }
    function applyResult(result) {
      assistant.content = String(result.answer || '');
      assistant.images = safeImages({ images: (result.images || []).map((image) => ({ url: String(image?.url || ''), filename: String(image?.filename || '') })) });
      if (updated.id === activeId) renderWorkspace();
    }
    async function finishReply() {
      const imageCount = safeImages(assistant).length;
      if (!displayAssistantContent(assistant.content).trim() && !imageCount) throw serverFailure('NathGPT a renvoyé une réponse vide.');
      recordUsage(accountKey, content, assistant.content, donePayload);
      notifyIfHidden(imageCount ? 'Ton image est prête' : 'Réponse de NathGPT', imageCount ? title : displayAssistantContent(assistant.content).replace(/\s+/g, ' ').slice(0, 140), id);
    }
  }
  // Fichiers joints : lus en base64 puis envoyés avec le message jusqu'à ChatGPT.
  const MAX_FILE_BYTES = 15 * 1024 * 1024;
  const MAX_FILES_TOTAL_BYTES = 25 * 1024 * 1024;
  function readAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
      reader.onerror = () => reject(new Error(`Impossible de lire « ${file.name} ».`));
      reader.readAsDataURL(file);
    });
  }
  async function encodeFiles(list) {
    let total = 0;
    for (const file of list) {
      if (!file.size) throw new Error(`« ${file.name} » est vide.`);
      if (file.size > MAX_FILE_BYTES) throw new Error(`« ${file.name} » dépasse 15 Mo.`);
      total += file.size;
    }
    if (total > MAX_FILES_TOTAL_BYTES) throw new Error('Fichiers trop volumineux : 25 Mo maximum au total.');
    return Promise.all(list.map(async (file) => ({ name: file.name, type: file.type || '', base64: await readAsBase64(file) })));
  }
  function showComposerError(text) {
    const note = document.createElement('p');
    note.textContent = text;
    modeWarning.replaceChildren(note);
    modeWarning.hidden = false;
  }
  function serverFailure(message) {
    const error = new Error(message);
    error.fromServer = true;
    return error;
  }
  // Interroge le serveur jusqu'à la fin de la réponse (6 min max). null si le serveur ne la connaît pas.
  async function recoverReply(requestId, signal, onPartial) {
    const deadline = Date.now() + 6 * 60 * 1000;
    while (Date.now() < deadline) {
      if (signal.aborted) throw new DOMException('Réponse arrêtée.', 'AbortError');
      try {
        const result = await api(`/api/chat/result/${encodeURIComponent(requestId)}`);
        if (result.finished) return result;
        onPartial(result);
      } catch (error) {
        if (error.status === 404 || error.status === 401) return null;
        /* réseau encore coupé (app en veille) : on réessaie */
      }
      await wait(2500);
    }
    return null;
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
    try { await navigator.clipboard.writeText(formattedMessage(chat, message)); button.textContent = 'Copié'; setTimeout(() => { button.innerHTML = `${icon('copy', 14)} Copier`; }, 1600); }
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
    closeAdmin();
    closeCricut();
    cricutJob = null;
    account = null; chats = []; activeId = null; dirtyChats.clear(); closeMenu(); showAuth();
  });

  // Administration : écran de la VM, état, logs et relance de NathGPT (comptes is_admin uniquement).
  let adminTimer = 0;
  let adminShot = '';
  let adminRestartArmed = 0;
  function formatDuration(seconds) {
    const days = Math.floor(seconds / 86400), hours = Math.floor(seconds % 86400 / 3600), minutes = Math.floor(seconds % 3600 / 60);
    return days ? `${days} j ${hours} h` : hours ? `${hours} h ${minutes} min` : `${minutes} min`;
  }
  function adminMessage(text, tone = '') {
    $('admin-message').textContent = text;
    $('admin-message').className = `admin-message ${tone}`;
    $('admin-message').hidden = !text;
  }
  function renderAdminStatus(data) {
    const vm = data.vm || {};
    const memory = vm.memory?.total ? `${((vm.memory.total - vm.memory.available) / 1073741824).toFixed(1)} / ${(vm.memory.total / 1073741824).toFixed(1)} Go` : '—';
    const chips = data.online ? [
      ['API', 'En ligne', 'ok'],
      ['Chromium', vm.chromium ? 'Ouvert' : 'Arrêté', vm.chromium ? 'ok' : 'bad'],
      ['État', vm.busy ? 'Génère une réponse' : 'Libre', vm.busy ? 'busy' : 'ok'],
      ['Actif depuis', formatDuration(Number(vm.uptime) || 0), ''],
      ['Mémoire', memory, ''],
      ['Charge', Array.isArray(vm.load) ? vm.load.join(' · ') : '—', ''],
    ] : [['API', data.message || 'Hors ligne', 'bad']];
    if (data.image_storage) chips.push(['Stockage images', data.image_storage === 'ok' ? 'OK' : data.image_storage, data.image_storage === 'ok' ? 'ok' : 'bad']);
    $('admin-status').innerHTML = chips.map(([label, value, tone]) => `<div class="admin-chip ${tone}"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></div>`).join('');
    return Boolean(data.online);
  }
  async function refreshAdminStatus() {
    try { return renderAdminStatus(await api('/api/admin/status')); }
    catch (error) { renderAdminStatus({ online: false, message: error.message }); return false; }
  }
  async function refreshAdminScreen() {
    try {
      const response = await fetch('/api/admin/screenshot', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(serverError(response.status, (await response.json().catch(() => ({}))).detail));
      const url = URL.createObjectURL(await response.blob());
      if (adminShot) URL.revokeObjectURL(adminShot);
      adminShot = url;
      $('admin-screen').src = url;
      $('admin-screen').hidden = false;
      $('admin-screen-caption').textContent = `Écran de la VM · ${new Date().toLocaleTimeString('fr-FR')}`;
    } catch (error) {
      $('admin-screen-caption').textContent = `Écran indisponible : ${error.message}`;
    }
  }
  async function refreshAdminLogs() {
    if (!$('admin-logs-box').open) return;
    try {
      const { lines } = await api('/api/admin/logs');
      const box = $('admin-logs');
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 30;
      box.textContent = lines.length ? lines.join('\n') : 'Aucun log.';
      if (atBottom) box.scrollTop = box.scrollHeight;
    } catch (error) { $('admin-logs').textContent = error.message; }
  }
  function refreshAdmin() {
    return Promise.all([refreshAdminStatus(), refreshAdminScreen(), refreshAdminLogs()]);
  }
  function scheduleAdmin(delay = adminControl ? 1500 : 3000) {
    clearTimeout(adminTimer);
    adminTimer = setTimeout(async () => {
      if ($('admin-panel').hidden) return;
      if (document.visibilityState === 'visible') await refreshAdmin();
      scheduleAdmin();
    }, delay);
  }
  function openAdmin() {
    if (!account?.isAdmin) return;
    closeMenu(); closeSidebar();
    adminMessage('');
    $('admin-panel').hidden = false;
    refreshAdmin().finally(() => scheduleAdmin());
  }
  function closeAdmin() {
    clearTimeout(adminTimer);
    $('admin-panel').hidden = true;
    disarmRestart();
  }
  function disarmRestart() {
    clearTimeout(adminRestartArmed);
    adminRestartArmed = 0;
    $('admin-restart').classList.remove('is-armed');
    $('admin-restart-label').textContent = 'Relancer NathGPT';
  }
  async function restartNathGPT() {
    if (!adminRestartArmed) {
      // Deux touchers : évite une relance accidentelle pendant une réponse.
      $('admin-restart').classList.add('is-armed');
      $('admin-restart-label').textContent = 'Toucher pour confirmer';
      adminRestartArmed = setTimeout(disarmRestart, 4000);
      return;
    }
    disarmRestart();
    $('admin-restart').disabled = true;
    adminMessage('Relance en cours… NathGPT redémarre, ça prend environ 30 secondes.', 'busy');
    try {
      await api('/api/admin/restart', { method: 'POST' });
      const deadline = Date.now() + 120000;
      await wait(5000);
      let back = false;
      while (!back && Date.now() < deadline && !$('admin-panel').hidden) {
        back = await refreshAdminStatus();
        if (!back) await wait(3000);
      }
      if (back) { adminMessage('NathGPT est relancé.', 'ok'); refreshAdminScreen(); }
      else if (!$('admin-panel').hidden) adminMessage('NathGPT ne répond toujours pas après 2 minutes. Regarde les logs.', 'bad');
    } catch (error) {
      adminMessage(`Relance impossible : ${error.message}`, 'bad');
    } finally {
      $('admin-restart').disabled = false;
    }
  }
  $('admin-button').addEventListener('click', openAdmin);
  $('admin-close').addEventListener('click', closeAdmin);
  $('admin-refresh').addEventListener('click', () => { refreshAdmin(); scheduleAdmin(); });
  $('admin-restart').addEventListener('click', restartNathGPT);
  $('admin-logs-box').addEventListener('toggle', refreshAdminLogs);
  // Contrôle à distance : toucher l'écran = cliquer sur la VM au même endroit.
  let adminControl = false;
  let adminClickKind = 'left';
  let adminPointer = { x: 640, y: 400 };
  async function sendAdminInput(action) {
    try {
      await api('/api/admin/input', { method: 'POST', body: JSON.stringify(action) });
      setTimeout(refreshAdminScreen, 450);
      setTimeout(refreshAdminScreen, 1500);
    } catch (error) {
      adminMessage(`Action impossible : ${error.message}`, 'bad');
    }
  }
  $('admin-control').addEventListener('change', (event) => {
    adminControl = event.target.checked;
    $('admin-remote').hidden = !adminControl;
    $('admin-click-kind').hidden = !adminControl;
    document.querySelector('.admin-screen').classList.toggle('is-control', adminControl);
    if (adminControl) adminMessage('Mode contrôle : touche l’écran pour cliquer sur la VM. Évite pendant qu’une réponse est en cours.', '');
    else adminMessage('');
    scheduleAdmin(300);
  });
  $('admin-click-kind').addEventListener('click', (event) => {
    const button = event.target.closest('[data-click]');
    if (!button) return;
    adminClickKind = button.dataset.click;
    for (const item of $('admin-click-kind').children) item.classList.toggle('is-active', item === button);
  });
  $('admin-screen').addEventListener('click', (event) => {
    const image = event.currentTarget;
    if (!adminControl) { if (adminShot) window.open(adminShot, '_blank', 'noopener'); return; }
    const box = image.getBoundingClientRect();
    const x = Math.round((event.clientX - box.left) * image.naturalWidth / box.width);
    const y = Math.round((event.clientY - box.top) * image.naturalHeight / box.height);
    adminPointer = { x, y };
    const tap = $('admin-tap');
    tap.style.left = `${event.clientX - box.left}px`;
    tap.style.top = `${event.clientY - box.top}px`;
    tap.hidden = false;
    restartAnimation(tap, 'is-on');
    sendAdminInput({ action: 'click', x, y, button: adminClickKind === 'right' ? 'right' : 'left', double: adminClickKind === 'double' });
  });
  $('admin-type-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const text = $('admin-type-text').value;
    if (!text) return;
    $('admin-type-text').value = '';
    sendAdminInput({ action: 'text', text });
  });
  $('admin-remote').addEventListener('click', (event) => {
    const key = event.target.closest('[data-key]')?.dataset.key;
    const scroll = Number(event.target.closest('[data-scroll]')?.dataset.scroll);
    if (key) sendAdminInput({ action: 'key', key });
    else if (scroll) sendAdminInput({ action: 'scroll', x: adminPointer.x, y: adminPointer.y, steps: scroll });
  });
  // Mode Cricut : Cricutastrophe découpe une planche de stickers en un PNG par sticker (travail fait sur la VM).
  const CRICUT_ACTIVE = ['waiting', 'numbering', 'counting', 'stickers'];
  const CRICUT_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
  let cricutJob = null;
  let cricutFile = null;
  let cricutNote = '';
  let cricutWantsNew = false;
  let cricutTimer = 0;
  let cricutBot = null;
  let cricutBotLoading = null;
  let cricutGridKey = '';
  function loadCricutBot() {
    if (window.NathGPTBot) return Promise.resolve(window.NathGPTBot);
    cricutBotLoading ||= new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/cricut-bot.bundle.js';
      script.onload = () => resolve(window.NathGPTBot);
      script.onerror = () => { cricutBotLoading = null; reject(new Error('bot indisponible')); };
      document.head.append(script);
    });
    return cricutBotLoading;
  }
  async function showCricutBot(state) {
    try {
      const library = await loadCricutBot();
      if (!cricutBot) cricutBot = library.mount($('cricut-bot'), { type: 'droid', face: 'mouth', size: 84, state, theme: 'dark', hat: 'beret' });
      else cricutBot.update({ state });
    } catch { $('cricut-bot').classList.add('is-fallback'); }
  }
  function cricutBotState(job) {
    if (job && CRICUT_ACTIVE.includes(job.phase)) return 'working';
    if (job?.phase === 'deleted') return 'sleeping';
    return 'default';
  }
  function cricutSays(job) {
    if (cricutNote) return cricutNote;
    if (!job || cricutWantsNew) {
      return cricutFile ? 'Jolie planche ! Appuie sur « Lancer Cricutastrophe » et je découpe chaque sticker.'
        : 'Salut, moi c’est Cricutastrophe ! Choisis une planche de stickers dans ta galerie : je la découpe en un PNG par sticker.';
    }
    const plural = (count, word) => `${count} ${word}${count > 1 ? 's' : ''}`;
    switch (job.phase) {
      case 'waiting': return 'Je fais la queue… je commence dès que NathGPT est libre.';
      case 'numbering': return 'Je redessine ta planche avec un numéro autour de chaque sticker…';
      case 'counting': return 'Planche numérotée ! Je compte les stickers…';
      case 'stickers': return `J’ai trouvé ${job.total} stickers ! Je découpe le n°${job.current}/${job.total}… (une nouvelle conversation par sticker)`;
      case 'finished': {
        if (job.delete_at) {
          const minutes = Math.max(0, Math.ceil((job.delete_at * 1000 - Date.now()) / 60000));
          return `Tout est téléchargé, merci ! Je supprime les fichiers de la VM dans ${minutes} min.`;
        }
        const missing = job.failed.length ? ` (${plural(job.failed.length, 'raté')})` : '';
        return `Terminé ! ${plural(job.completed, 'sticker')} sur ${job.total}${missing}. Télécharge-les : je les supprime de la VM 10 minutes après.`;
      }
      case 'error': return `Oups… ${job.error || 'je me suis arrêté.'}`;
      case 'deleted': return 'Fichiers supprimés de la VM. On recommence avec une nouvelle planche ?';
      default: return '';
    }
  }
  const cricutUrl = (name, download = false) => `/api/cricut/jobs/${cricutJob.id}/files/${name}${download ? '?download=1' : ''}`;
  function renderCricutStickers(job) {
    const visible = job && !cricutWantsNew && job.phase !== 'deleted' && (job.total || job.files.length);
    const key = visible ? JSON.stringify([job.id, job.total, job.files, job.failed, job.downloaded, job.phase]) : '';
    if (key === cricutGridKey) return;
    cricutGridKey = key;
    if (!visible) { $('cricut-stickers').replaceChildren(); return; }
    const tiles = [];
    for (let index = 1; index <= Math.max(job.total, job.files.length); index += 1) {
      const name = `sticker_${String(index).padStart(2, '0')}.png`;
      if (job.files.includes(name)) {
        const done = job.downloaded.includes(name);
        tiles.push(`<figure class="cricut-sticker ${done ? 'is-done' : ''}"><img src="${cricutUrl(name)}" alt="Sticker ${index}" loading="lazy"><figcaption>n°${index}</figcaption><a class="cricut-dl" href="${cricutUrl(name, true)}" download="${name}" aria-label="Télécharger le sticker ${index}">${done ? icon('check', 15) : icon('arrow-up', 15)}</a></figure>`);
      } else if (job.failed.includes(index)) {
        tiles.push(`<figure class="cricut-sticker is-failed"><span>Raté</span><figcaption>n°${index}</figcaption></figure>`);
      } else {
        tiles.push(`<figure class="cricut-sticker is-pending ${job.phase === 'stickers' && job.current === index ? 'is-current' : ''}"><span>${index}</span><figcaption>n°${index}</figcaption></figure>`);
      }
    }
    $('cricut-stickers').innerHTML = tiles.join('');
  }
  function renderCricut() {
    const job = cricutWantsNew ? null : cricutJob;
    const active = Boolean(job && CRICUT_ACTIVE.includes(job.phase));
    $('cricut-say').textContent = cricutSays(job);
    showCricutBot(cricutBotState(job));
    const steps = (job?.total || 0) + 2;
    const done = job ? Number(job.numbered) + Number(job.total > 0) + job.completed + job.failed.length : 0;
    const percent = !job ? 0 : ['finished', 'deleted'].includes(job.phase) ? 100 : Math.round(done / Math.max(steps, 3) * 100);
    $('cricut-progress').hidden = !job || job.phase === 'error';
    $('cricut-bar').style.width = `${percent}%`;
    $('cricut-progress-text').textContent = job?.total ? `${job.completed} / ${job.total} stickers` : (active ? 'Préparation…' : '');
    $('cricut-upload').hidden = Boolean(job) && !['error', 'deleted'].includes(job.phase);
    $('cricut-start').disabled = !cricutFile;
    const showPlanche = Boolean(job?.numbered) && job.phase !== 'deleted';
    $('cricut-planche-box').hidden = !showPlanche;
    if (showPlanche && $('cricut-planche').dataset.job !== job.id) {
      $('cricut-planche').dataset.job = job.id;
      $('cricut-planche').src = cricutUrl('planche_numerotee.png');
    }
    renderCricutStickers(job);
    const finished = job?.phase === 'finished' && job.files.length > 0;
    $('cricut-actions').hidden = !job || active;
    $('cricut-zip').hidden = !finished;
    $('cricut-all').hidden = !finished;
    if (finished) {
      $('cricut-zip').href = `/api/cricut/jobs/${job.id}/zip`;
      $('cricut-all').textContent = `Tout télécharger (${job.files.length} images)`;
      prefetchCricutFiles(job);
    }
    $('cricut-delete').hidden = !job || job.phase === 'deleted';
  }
  async function refreshCricut() {
    try {
      if (cricutJob) cricutJob = (await api(`/api/cricut/jobs/${cricutJob.id}`)).job;
      else cricutJob = (await api('/api/cricut/jobs')).jobs[0] || null;
    } catch (error) {
      if (error.status === 404) cricutJob = null;
      else cricutNote = error.message;
    }
    renderCricut();
  }
  function scheduleCricut(delay) {
    clearTimeout(cricutTimer);
    if ($('cricut-panel').hidden) return;
    const active = cricutJob && CRICUT_ACTIVE.includes(cricutJob.phase);
    cricutTimer = setTimeout(async () => {
      const before = cricutJob?.phase;
      if (document.visibilityState === 'visible' || active) await refreshCricut();
      if (before && CRICUT_ACTIVE.includes(before) && cricutJob?.phase === 'finished') {
        notifyIfHidden('Tes stickers sont prêts ✂️', `${cricutJob.completed} stickers à télécharger.`, '');
      }
      scheduleCricut();
    }, delay ?? (active ? 4000 : 15000));
  }
  function openCricut() {
    if (!account?.cricut) return;
    closeMenu(); closeSidebar(); closeAdmin();
    cricutNote = '';
    $('cricut-panel').hidden = false;
    renderCricut();
    refreshCricut().finally(() => scheduleCricut());
  }
  function closeCricut() {
    clearTimeout(cricutTimer);
    $('cricut-panel').hidden = true;
  }
  async function prepareCricutImage(file) {
    if (CRICUT_TYPES.includes(file.type) && file.size <= 20 * 1024 * 1024) return { blob: file, type: file.type };
    // HEIC ou image trop lourde : convertie dans le navigateur (PNG pour garder la transparence).
    const url = URL.createObjectURL(file);
    try {
      const image = await new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error('Image illisible : choisis une photo PNG ou JPEG.')); img.src = url; });
      const scale = Math.min(1, 4096 / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(image.naturalWidth * scale);
      canvas.height = Math.round(image.naturalHeight * scale);
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      let blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      if (blob && blob.size <= 20 * 1024 * 1024) return { blob, type: 'image/png' };
      blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
      if (!blob) throw new Error('Conversion de l’image impossible.');
      return { blob, type: 'image/jpeg' };
    } finally { URL.revokeObjectURL(url); }
  }
  $('cricut-input').addEventListener('change', (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) { cricutNote = 'Il me faut une image (photo de ta planche de stickers).'; renderCricut(); return; }
    cricutFile = file;
    cricutNote = '';
    const preview = $('cricut-preview');
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    $('cricut-drop-text').hidden = true;
    renderCricut();
  });
  $('cricut-start').addEventListener('click', async () => {
    if (!cricutFile) return;
    $('cricut-start').disabled = true;
    cricutNote = 'J’envoie ta planche à la VM…';
    renderCricut();
    try {
      const { blob, type } = await prepareCricutImage(cricutFile);
      const image = await readAsBase64(blob);
      const data = await api('/api/cricut/jobs', { method: 'POST', body: JSON.stringify({ image, type, name: cricutFile.name }) });
      cricutJob = data.job;
      cricutFile = null;
      cricutWantsNew = false;
      cricutNote = '';
      $('cricut-preview').hidden = true;
      $('cricut-drop-text').hidden = false;
      if ('Notification' in window && Notification.permission === 'default') askForNotifications(true);
      else ensurePushSubscription();
    } catch (error) {
      cricutNote = `Oups… ${error.message}`;
    }
    renderCricut();
    scheduleCricut(1500);
  });
  // « Tout télécharger » : sur iPhone, menu de partage (« Enregistrer N images » dans Photos) ;
  // ailleurs, un téléchargement par PNG. Les images sont préchargées pour que le partage parte
  // directement dans le toucher (iOS refuse un partage lancé après une longue attente).
  let cricutCache = { id: '', files: [] };
  async function prefetchCricutFiles(job) {
    const key = `${job.id}:${job.files.join(',')}`;
    if (cricutCache.key === key) return cricutCache.ready;
    cricutCache = { key, id: job.id, files: [] };
    cricutCache.ready = Promise.all(job.files.map(async (name) => {
      const response = await fetch(cricutUrl(name), { credentials: 'same-origin' });
      if (!response.ok) throw new Error('Image indisponible');
      return new File([await response.blob()], name, { type: 'image/png' });
    })).then((files) => { if (cricutCache.key === key) cricutCache.files = files; return files; }).catch(() => []);
    return cricutCache.ready;
  }
  function markCricutDownloaded(job) {
    // Le ZIP marque toutes les images comme téléchargées (et lance la suppression dans 10 min).
    fetch(`/api/cricut/jobs/${job.id}/zip`, { credentials: 'same-origin' }).catch(() => {}).finally(() => setTimeout(refreshCricut, 800));
  }
  $('cricut-all').addEventListener('click', async () => {
    const job = cricutJob;
    if (!job?.files.length) return;
    let files = cricutCache.id === job.id ? cricutCache.files : [];
    const canShareFiles = (list) => list.length && navigator.canShare?.({ files: list });
    if (canShareFiles(files)) {
      try {
        await navigator.share({ files, title: 'Stickers Cricut' });
        markCricutDownloaded(job);
      } catch (error) {
        if (error.name !== 'AbortError') cricutNote = 'Le partage a échoué : essaie « Télécharger en ZIP ».';
        renderCricut();
      }
      return;
    }
    if (!files.length && navigator.canShare) {
      cricutNote = 'Je prépare tes images… touche encore « Tout télécharger » dans un instant.';
      renderCricut();
      files = await prefetchCricutFiles(job);
      cricutNote = files.length ? 'Images prêtes : touche « Tout télécharger » pour les enregistrer.' : 'Images indisponibles : essaie « Télécharger en ZIP ».';
      renderCricut();
      if (canShareFiles(files)) return;
    }
    // Ordinateur : un téléchargement par image, espacés pour que le navigateur les accepte tous.
    for (const name of job.files) {
      const link = document.createElement('a');
      link.href = cricutUrl(name, true);
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      await wait(350);
    }
    setTimeout(refreshCricut, 1500);
  });
  $('cricut-new').addEventListener('click', () => { cricutWantsNew = true; cricutNote = ''; renderCricut(); });
  $('cricut-delete').addEventListener('click', async () => {
    if (!cricutJob || !window.confirm('Supprimer cette planche et ses stickers de la VM ?')) return;
    try { await api(`/api/cricut/jobs/${cricutJob.id}`, { method: 'DELETE' }); } catch (error) { cricutNote = error.message; }
    await refreshCricut();
  });
  // Après un téléchargement, on met à jour les coches et le compte à rebours de suppression.
  $('cricut-panel').addEventListener('click', (event) => {
    if (event.target.closest('.cricut-dl, #cricut-zip')) setTimeout(refreshCricut, 2500);
  });
  $('cricut-button').addEventListener('click', openCricut);
  $('cricut-close').addEventListener('click', closeCricut);

  // Notifications push : abonne l'appareil pour être prévenu même app fermée.
  function base64UrlBytes(value) {
    const text = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
    return Uint8Array.from(text, (character) => character.charCodeAt(0));
  }
  async function ensurePushSubscription() {
    if (!account || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window) || Notification.permission !== 'granted') return;
    try {
      const { key } = await api('/api/push/key');
      if (!key) return;
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      const options = { userVisibleOnly: true, applicationServerKey: base64UrlBytes(key) };
      if (!subscription) {
        subscription = await registration.pushManager.subscribe(options);
      }
      await api('/api/push/subscribe', { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
    } catch { /* notifications push indisponibles sur cet appareil */ }
  }
  window.addEventListener('beforeunload', () => pendingRequest?.abort());
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && account) { event.preventDefault(); newChat(); }
    if (event.key === 'Escape') {
      if (!$('voice-panel').hidden) { event.preventDefault(); cancelVoice(); }
      else if (!$('admin-panel').hidden) closeAdmin();
      else if (!$('cricut-panel').hidden) closeCricut();
      else { closeMenu(); closeUsageInfo(); closeSidebar(); }
    }
  });
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && !$('voice-panel').hidden) cancelVoice();
  });

  // iPhone / iPad : NathGPT ne s'utilise que depuis l'écran d'accueil (mode app plein écran).
  function requiresHomeScreen(nav = navigator, standaloneMedia = matchMedia('(display-mode: standalone)').matches) {
    const ios = /iPhone|iPad|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1);
    return ios && nav.standalone !== true && !standaloneMedia;
  }
  function showInstallGate() {
    const ua = navigator.userAgent;
    const inApp = ua.match(/Instagram|FBAN|FBAV|Snapchat|TikTok|musical_ly|BytedanceWebview|Discord|LinkedInApp|Line\/|Twitter|GSA\//);
    if (inApp) {
      const app = { FBAN: 'Facebook', FBAV: 'Facebook', musical_ly: 'TikTok', BytedanceWebview: 'TikTok', LinkedInApp: 'LinkedIn', 'Line/': 'LINE', 'GSA/': 'Google' }[inApp[0]] || inApp[0];
      $('ios-install-browser').textContent = `Tu es dans ${app} : l’ajout à l’écran d’accueil n’y est pas possible. Ouvre d’abord ce lien dans Safari (menu ••• › Ouvrir dans Safari).`;
      $('ios-install-browser').hidden = false;
    } else if (/CriOS|FxiOS|EdgiOS/.test(ua)) {
      $('ios-install-share-hint').textContent = 'Dans la barre d’adresse en haut, ou ouvre ce lien dans Safari.';
    }
    const ipad = !/iPhone|iPod/.test(ua);
    $('ios-install').classList.toggle('is-ipad', ipad || /CriOS|FxiOS|EdgiOS/.test(ua));
    $('ios-install').classList.toggle('no-pointer', Boolean(inApp));
    $('auth-page').hidden = true;
    $('app-shell').hidden = true;
    $('ios-install').hidden = false;
  }

  if (requiresHomeScreen()) showInstallGate();
  else {
    // La session est un cookie httpOnly : on demande au serveur quel compte est connecté.
    api('/api/auth/me')
      .then((data) => {
        startSession(data.account);
      })
      .catch(() => showAuth());
  }
})();
