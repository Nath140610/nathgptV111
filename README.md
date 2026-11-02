# NathGPT

Site de conversation NathGPT : interface HTML/CSS/JavaScript (adaptée aux téléphones, avec une Dynamic Island sur iPhone), servie par un serveur Python FastAPI. Le serveur relaie les messages vers l'API NathGPT V4 en streaming (SSE). Les comptes, les sessions, le compteur d'économies et l'historique des conversations sont stockés dans Supabase en production, ou dans un fichier SQLite en local.

```
Navigateur ──► Render (server.py) ──► API NathGPT (HTTPS + jeton Bearer)
                    │
                    └──► Supabase (comptes, sessions, conversations)
```

## Déployer sur Render

1. **Supabase.** Créez un projet, puis ouvrez *SQL Editor › New query* et exécutez [`supabase/schema.sql`](supabase/schema.sql). Ensuite, dans *Project Settings › API*, notez l'URL du projet et la **clé secrète** (`sb_secret_…`, ou l'ancienne clé `service_role`).
2. **Render.** Créez un *Web Service* sur ce dépôt, ou un *Blueprint*, qui lira [`render.yaml`](render.yaml) :
   - Build : `pip install -r requirements.txt`
   - Démarrage : `gunicorn --config gunicorn.conf.py server:app`
   - Health check : `/api/health`
3. **Variables d'environnement** (Render › Environment) :

   | Variable | Valeur |
   |---|---|
   | `PYTHON_VERSION` | `3.12.8` |
   | `NATHGPT_API_URL` | URL **HTTPS** publique de l'API NathGPT |
   | `NATHGPT_API_TOKEN` | Jeton Bearer de l'API NathGPT |
   | `SUPABASE_URL` | `https://<projet>.supabase.co` |
   | `SUPABASE_SECRET_KEY` | Clé secrète Supabase (jamais côté navigateur) |

`/api/health` indique `"storage": "supabase"` quand Supabase est bien branché.

**L'API NathGPT doit être joignable depuis Internet en HTTPS.** L'adresse `http://127.0.0.1:18765` du tunnel SSH n'existe que sur le PC Windows : Render ne peut pas l'utiliser. Il faut donc exposer l'API du serveur Nest (port local `8765`) derrière un reverse proxy HTTPS, par exemple le Caddy de Nest sur un sous-domaine `*.hackclub.app` ou un tunnel Cloudflare. Le jeton Bearer reste obligatoire.

## Reprendre les données de l'ancien site

[`supabase/convertir_ancien_site.py`](supabase/convertir_ancien_site.py) convertit le dossier `data/` de l'ancien site (`users.json`, `conversations.json`) en un fichier SQL à exécuter **après** `schema.sql` :

```powershell
python supabase/convertir_ancien_site.py CHEMIN\vers\data supabase\import_ancien_site.local.sql
```

Les anciens mots de passe restent valables : le format Werkzeug `scrypt` est reconnu. Les adresses IP, les jetons API, les données Discord et les images ne sont pas repris. Le fichier produit contient des données personnelles : `*.local.sql` est ignoré par git.

## Lancer en local (PowerShell)

```powershell
python -m pip install -r requirements.txt
$env:NATHGPT_API_URL = 'http://127.0.0.1:18765'
$env:NATHGPT_API_TOKEN = (Get-Content -LiteralPath 'C:\Users\natha\Desktop\NATHGPT_NEST\TOKEN_API_LOCAL.txt' -Raw).Trim()
python -m uvicorn server:app --host 127.0.0.1 --port 4173
```

Ouvrez http://127.0.0.1:4173/. Sans `SUPABASE_URL`, les comptes sont enregistrés dans `data/nathgpt.sqlite3`.

## Page Admin

Dans Supabase > Table Editor > `nathgpt_accounts`, coche `is_admin` sur ton compte (après avoir relancé `supabase/schema.sql`).
Reconnecte-toi : le menu du profil affiche « Administration » (état de la VM, écran en direct, logs, bouton « Relancer NathGPT »).
Le droit est vérifié à chaque demande : décocher la case coupe l'accès tout de suite. L'API de la VM doit être à jour (`TOUT_FAIRE_TOUT_SEUL.bat`).

## Sécurité

- Mots de passe hachés côté serveur (scrypt), 10 tentatives de connexion par minute et par IP.
- Session dans un cookie `httpOnly` / `Secure` / `SameSite=Lax` ; seule son empreinte SHA-256 est stockée.
- Tables Supabase fermées par RLS : seule la clé secrète du serveur y accède.
- Une conversation n'est lisible et modifiable que par son propriétaire.
- Limites : 12 messages par minute et par session, 3 générations simultanées.

## iPhone

Le site respecte les zones sûres (encoche, Dynamic Island, barre d'accueil) et le clavier iOS. Ajouté à l'écran d'accueil (Safari › Partager › *Sur l'écran d'accueil*), l'îlot NathGPT se superpose à la Dynamic Island de l'appareil et y affiche l'activité : réflexion, rédaction, réponse prête, dictée vocale.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
node tests/test_frontend_stream.cjs
```
