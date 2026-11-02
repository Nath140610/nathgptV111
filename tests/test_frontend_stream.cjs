const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
const start = source.indexOf('  async function* parseSSE(stream)');
const end = source.indexOf('  function serverError(', start);
assert(start >= 0 && end > start);
const parseSSE = new Function(`${source.slice(start, end)}; return parseSSE;`)();
const displayLine = source.split('\n').find((line) => line.includes('const displayAssistantContent ='));
assert(displayLine);
const displayAssistantContent = new Function(`${displayLine}; return displayAssistantContent;`)();
assert.equal(displayAssistantContent('ChatGPT said: Pong! 🏓'), 'Pong! 🏓');
assert.equal(displayAssistantContent('Pong! 🏓'), 'Pong! 🏓');
assert.equal(displayAssistantContent('Une phrase avec ChatGPT said: au milieu.'), 'Une phrase avec ChatGPT said: au milieu.');
const modeStart = source.indexOf('  function classifyPrompt(');
const modeEnd = source.indexOf('  function formatAssistantContent(', modeStart);
assert(modeStart >= 0 && modeEnd > modeStart);
const modeMismatch = new Function(`${source.slice(modeStart, modeEnd)}; return modeMismatch;`)();
assert.equal(modeMismatch('Agent', 'Génère une image de chat'), 'Image');
assert.equal(modeMismatch('Chat', 'Peux-tu me dessiner un chat ?'), 'Image');
assert.equal(modeMismatch('Agent', 'Je veux une photo réaliste'), 'Image');
assert.equal(modeMismatch('Agent', 'Explique comment générer une image'), null);
assert.equal(modeMismatch('Image', 'Écris un poème sur les étoiles'), 'Chat');
assert.equal(modeMismatch('Image', 'Bonjour, comment vas-tu ?'), 'Chat');
assert.equal(modeMismatch('Image', 'Un chat dans l’espace, style aquarelle'), null);
assert.equal(modeMismatch('Image', 'Génère une image de chat'), null);
const formatStart = source.indexOf('  function formatAssistantContent(');
const formatEnd = source.indexOf('  function formattedMessage(', formatStart);
assert(formatStart >= 0 && formatEnd > formatStart);
const formatAssistantContent = new Function(`${displayLine}\n${source.slice(formatStart, formatEnd)}; return formatAssistantContent;`)();
const poem = '🌙 Le murmure des étoiles ✨ Quand le soleil s’endort derrière les montagnes, La lune se réveille et doucement l’accompagne. Les étoiles brillent comme des diamants, Et le vent raconte des secrets oubliés du temps.';
assert.match(formatAssistantContent(poem, 'Crée un poème'), /✨\n\nQuand/);
assert.match(formatAssistantContent(poem, 'Crée un poème'), /montagnes,\nLa lune/);
const prose = 'Voici une première idée qui mérite une explication claire et assez longue pour être comprise. Une deuxième phrase développe le sujet avec un exemple concret et facile à suivre. Une troisième phrase ajoute une précision utile avant de terminer. Enfin, cette dernière phrase conclut la réponse avec un conseil pratique.';
assert(formatAssistantContent(prose).includes('\n\n'));
assert.equal(formatAssistantContent('# Titre\n\nDéjà mis en page.'), '# Titre\n\nDéjà mis en page.');
assert.equal(formatAssistantContent('Pong! 🏓'), 'Pong! 🏓');
const usageStart = source.indexOf('  const estimateTokens =');
const usageEnd = source.indexOf('  const restoreChats =', usageStart);
assert(usageStart >= 0 && usageEnd > usageStart);
const createUsage = new Function('$', 'account', 'PRICE_PER_TOKEN_EUR', `${source.slice(usageStart, usageEnd)}; return { renderUsageCost, recordUsage };`);
const costNode = { textContent: '', title: '' };
const tokenNode = { textContent: '' };
const alice = { key: 'alice', tokensUsed: 0, usageEstimated: false };
const usage = createUsage((id) => id === 'usage-cost' ? costNode : tokenNode, alice, 0.00000892);
usage.renderUsageCost();
assert.equal(costNode.textContent, '0,00 €');
assert.match(tokenNode.textContent, /0 tokens/);
// Sans total serveur : estimation locale.
usage.recordUsage('alice', 'ping', 'Pong', {});
assert.equal(alice.tokensUsed, 2);
assert.equal(costNode.textContent, '≈ 0,00 €');
usage.recordUsage('alice', 'question', 'answer', { total_tokens: 12 });
assert.equal(alice.tokensUsed, 14);
// Total renvoyé par le serveur (Supabase) : il fait foi.
usage.recordUsage('alice', 'question', 'answer', { account_tokens_used: 2514, usage_estimated: false });
assert.equal(alice.tokensUsed, 2514);
assert.equal(costNode.textContent, '0,02 €');
usage.recordUsage('bob', 'question', 'answer', { account_tokens_used: 99 });
assert.equal(alice.tokensUsed, 2514);

(async () => {
  const bytes = new TextEncoder().encode('event: delta\r\ndata: {"text":"B"}\r\n\r\nevent: delta\ndata: {"text":"on"}\n\nevent: replace\ndata: {"text":"Bonjour 🌟"}\n\nevent: done\ndata: {}\n\n');
  let index = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (index === bytes.length) return controller.close();
      controller.enqueue(bytes.slice(index, index + 1));
      index += 1;
    },
  });
  const events = [];
  for await (const event of parseSSE(stream)) events.push([event.event, JSON.parse(event.data)]);
  assert.deepEqual(events, [
    ['delta', { text: 'B' }],
    ['delta', { text: 'on' }],
    ['replace', { text: 'Bonjour 🌟' }],
    ['done', {}],
  ]);
  console.log('Frontend SSE parser: OK');
})().catch((error) => { console.error(error); process.exitCode = 1; });
