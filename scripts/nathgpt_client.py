#!/usr/bin/env python3
"""Client de l'API NathGPT v1 — uniquement la bibliothèque standard Python.

En ligne de commande :
    python nathgpt_client.py login --url https://VOTRE-DOMAINE --username nath
    python nathgpt_client.py chat "Bonjour NathGPT"
    python nathgpt_client.py image "Un chat vert dans l'espace" -o chat.png
    python nathgpt_client.py usage
    python nathgpt_client.py keys
    python nathgpt_client.py logout

`login` enregistre l'URL et le token dans ~/.nathgpt.json (ou le fichier donné par
NATHGPT_CONFIG). Les variables NATHGPT_URL et NATHGPT_API_KEY sont prioritaires.

Depuis une autre application Python :
    from nathgpt_client import NathGPT
    api = NathGPT("https://VOTRE-DOMAINE", api_key="ngt_...")
    # ou : api = NathGPT.login("https://VOTRE-DOMAINE", "pseudo", "mot de passe")
    print(api.chat("Bonjour"))
    open("image.png", "wb").write(api.image("Un chat vert"))
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("NATHGPT_CONFIG") or Path.home() / ".nathgpt.json")
DEFAULT_TIMEOUT = 600  # les réponses passent par le bot Discord et peuvent être longues


class NathGPTError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status} {code}] {message}")
        self.status, self.code, self.message = status, code, message


class NathGPT:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.api_key = api_key
        self.timeout = timeout

    # --- transport -------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None, auth: bool = True):
        headers = {"Accept": "application/json", "User-Agent": "nathgpt-client/1.0"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.api_key:
                raise NathGPTError(0, "missing_api_key", "Aucun token : lance d'abord `login`.")
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                err = json.loads(raw).get("error", {})
            except (ValueError, AttributeError):
                err = {}
            raise NathGPTError(exc.code, err.get("code", "http_error"), err.get("message", raw[:300])) from None
        except urllib.error.URLError as exc:
            raise NathGPTError(0, "network_error", str(exc.reason)) from None

    # --- authentification ------------------------------------------------
    @classmethod
    def login(cls, base_url: str, username: str, password: str, name: str = "Script API", **kwargs):
        client = cls(base_url, **kwargs)
        result = client._request(
            "POST", "/v1/auth/token",
            {"pseudo": username, "password": password, "name": name},
            auth=False,
        )
        client.api_key = result["token"]
        return client

    def logout(self):
        """Révoque le token utilisé : il ne fonctionnera plus."""
        return self._request("DELETE", "/v1/auth/token")

    def keys(self):
        return self._request("GET", "/v1/auth/keys")

    # --- fonctionnalités -------------------------------------------------
    def usage(self):
        return self._request("GET", "/v1/usage")

    def models(self):
        return self._request("GET", "/v1/models")

    def chat_completion(self, messages: list[dict], model: str = "nathgpt", conversation_id: str | None = None):
        body = {"model": model, "messages": messages}
        if conversation_id:
            body["conversation_id"] = conversation_id  # pour continuer une conversation côté NathGPT
        return self._request("POST", "/v1/chat/completions", body)

    def chat(self, prompt: str, history: list[dict] | None = None) -> str:
        messages = list(history or []) + [{"role": "user", "content": prompt}]
        return self.chat_completion(messages)["choices"][0]["message"]["content"]

    def image(self, prompt: str, model: str = "nathgpt-image") -> bytes:
        """Octets de l'image générée (PNG, JPEG ou WebP)."""
        result = self._request("POST", "/v1/images/generations", {"model": model, "prompt": prompt, "n": 1})
        return base64.b64decode(result["data"][0]["b64_json"])


# --- configuration locale ------------------------------------------------
def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_config(config: dict):
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)  # lisible uniquement par toi (sans effet sous Windows)
    except OSError:
        pass


def _client_from_config(url_override: str | None = None) -> NathGPT:
    config = _load_config()
    url = url_override or os.environ.get("NATHGPT_URL") or config.get("url")
    if not url:
        raise NathGPTError(0, "missing_url", "URL inconnue : passe --url ou lance `login`.")
    return NathGPT(url, os.environ.get("NATHGPT_API_KEY") or config.get("api_key"))


def main(argv=None):
    # --url / --json acceptés avant ou après la commande (SUPPRESS : la commande n'écrase pas la valeur globale).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS, help="URL du site NathGPT (Render)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Afficher la réponse JSON brute")
    parser = argparse.ArgumentParser(description="Client de l'API NathGPT", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", parents=[common], help="Obtenir un token avec pseudo + mot de passe")
    p_login.add_argument("--username", "-u")
    p_login.add_argument("--name", default="Script API", help="Nom de la clé (visible dans Paramètres)")
    p_chat = sub.add_parser("chat", parents=[common], help="Envoyer un message")
    p_chat.add_argument("prompt", nargs="+")
    p_image = sub.add_parser("image", parents=[common], help="Générer une image")
    p_image.add_argument("prompt", nargs="+")
    p_image.add_argument("--output", "-o", default="nathgpt_image.png", help="Fichier où enregistrer l'image")
    sub.add_parser("usage", parents=[common], help="Voir le quota restant")
    sub.add_parser("keys", parents=[common], help="Lister les clés du compte")
    sub.add_parser("logout", parents=[common], help="Révoquer le token enregistré")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # console Windows (cp1252) : jamais de plantage sur un caractère
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args.url = getattr(args, "url", None)
    args.json = getattr(args, "json", False)

    try:
        if args.command == "login":
            url = args.url or os.environ.get("NATHGPT_URL") or _load_config().get("url") or input("URL NathGPT : ")
            username = args.username or input("Pseudo : ")
            password = os.environ.get("NATHGPT_PASSWORD") or getpass.getpass("Mot de passe : ")
            client = NathGPT.login(url, username, password, name=args.name)
            _save_config({"url": client.base_url, "api_key": client.api_key})
            print(f"Connecté. Token enregistré dans {CONFIG_FILE}")
            return 0

        client = _client_from_config(args.url)
        if args.command == "chat":
            prompt = " ".join(args.prompt)
            if args.json:
                result = client.chat_completion([{"role": "user", "content": prompt}])
            else:
                print(client.chat(prompt))
                return 0
        elif args.command == "image":
            prompt = " ".join(args.prompt)
            if args.json:
                result = client._request("POST", "/v1/images/generations",
                                         {"model": "nathgpt-image", "prompt": prompt, "n": 1})
            else:
                Path(args.output).write_bytes(client.image(prompt))
                print(f"Image enregistrée dans {args.output}")
                return 0
        elif args.command == "usage":
            result = client.usage()
            if not args.json:
                print(f"{result['tokens_used']} tokens utilisés (~ {result['saved_eur']} € économisés)")
                return 0
        elif args.command == "keys":
            result = client.keys()
            if not args.json:
                for key in result["data"]:
                    mark = "*" if key["id"] == result["current_key_id"] else " "
                    state = "active" if key["active"] else "révoquée"
                    print(f"{mark} {key['id']}  {key['prefix']:<16} {key['name']:<20} {state}")
                return 0
        elif args.command == "logout":
            result = client.logout()
            config = _load_config()
            config.pop("api_key", None)
            _save_config(config)
            if not args.json:
                print("Token révoqué.")
                return 0

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except NathGPTError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nAnnulé.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
