// Détection des demandes d’image : le site conseille le mode Image au bon moment.
const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'app.js'), 'utf8');
const start = src.indexOf('  function classifyPrompt(value) {');
const end = src.indexOf('  function modeMismatch(', start);
const classifyPrompt = new Function(src.slice(start, end) + '; return classifyPrompt;')();
const cases = [
  ['Créer une planche de stikers style scrap booking de 2 stikers aléatoire', true],
  ['Fais moi des stickers de chats', true],
  ['crée un fond d’écran de montagne', true],
  ['Génère une image de chat', true],
  ['Dessine un dragon', true],
  ['Comment créer des stickers avec Cricut ?', false],
  ['Explique moi le scrapbooking', false],
  ['Écris un poème sur les chats', false],
  ['Bonjour, comment ça va ?', false],
  ['Fais un résumé de ce texte', false],
];
let bad = 0;
for (const [prompt, expected] of cases) {
  const got = classifyPrompt(prompt).image;
  if (got !== expected) bad += 1;
  console.log(got === expected ? 'OK ' : 'ERR', expected ? 'image' : 'texte', '|', prompt);
}
process.exit(bad ? 1 : 0);
