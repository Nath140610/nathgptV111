"""Relais asynchrone entre NathGPT et un bot Discord."""

import asyncio
import io
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import threading
import time
import uuid


DEFAULT_CATEGORY_ID = 1539922989200576512
DEFAULT_TARGET_BOT_ID = 1539359893063209053
DEFAULT_STAFF_USER_ID = 1362876245381091471
TEXT_RESPONSE_SETTLE_SECONDS = 1.6
DISCORD_CATEGORY_CHANNEL_LIMIT = 50


def load_local_env(project_dir: Path):
    """Charge les variables Discord depuis .env sans dépendance supplémentaire."""
    env_path = project_dir / ".env"

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")

        if name in {
            "DISCORD_TOKEN",
            "DISCORD_CATEGORY_ID",
            "DISCORD_TARGET_BOT_ID",
            "DISCORD_STAFF_USER_ID",
        } and name not in os.environ:
            os.environ[name] = value


class DiscordBridge:
    """Gère un client Discord dans son propre thread et expose des jobs à Flask."""

    def __init__(self, data_dir: Path):
        load_local_env(data_dir.parent)
        self.token = os.environ.get("DISCORD_TOKEN", "").strip()
        self.category_id = int(os.environ.get("DISCORD_CATEGORY_ID", DEFAULT_CATEGORY_ID))
        self.target_bot_id = int(os.environ.get("DISCORD_TARGET_BOT_ID", DEFAULT_TARGET_BOT_ID))
        self.staff_user_id = int(os.environ.get("DISCORD_STAFF_USER_ID", DEFAULT_STAFF_USER_ID))
        self.response_timeout = max(
            30,
            int(os.environ.get("DISCORD_RESPONSE_TIMEOUT_SECONDS", "240"))
        )
        self.connect_timeout = min(
            90,
            max(30, int(os.environ.get("DISCORD_CONNECT_TIMEOUT_SECONDS", "60")))
        )
        self.reconnect_initial_delay = min(
            30,
            max(2, int(os.environ.get("DISCORD_RECONNECT_INITIAL_SECONDS", "3")))
        )
        self.disconnect_grace = min(
            180,
            max(20, int(os.environ.get("DISCORD_DISCONNECT_GRACE_SECONDS", "45")))
        )
        self.store_path = data_dir / "discord_conversations.json"
        self.image_store_path = data_dir / "discord_image_messages.json"
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._loop = None
        self._client = None
        self._thread = None
        self._discord = None
        self._started = False
        self._startup_error = None
        self._restart_requested = False
        self._result_handler = None
        self._connection_handler = None
        self._pending_staff_notifications = []
        self._jobs = {}
        self._channel_jobs = {}
        self._conversations = self._load_conversations()
        self._image_messages = self._load_image_messages()

    @property
    def enabled(self):
        return bool(self.token)

    def start(self):
        """Démarre le bot une seule fois, sans bloquer Flask."""
        with self._lock:
            if self._started and self._thread and self._thread.is_alive():
                return
            # Un thread arrêté ne doit jamais bloquer les nouvelles demandes :
            # Render peut reconnecter le bot après une période de veille.
            if self._started:
                self._started = False
                self._loop = None
                self._client = None

        if not self.token:
            print("Discord désactivé : définis DISCORD_TOKEN avant de lancer le serveur.")
            return

        try:
            import discord
        except ImportError as error:
            print(f"Discord désactivé : dépendance discord.py absente ({error}).")
            return

        with self._lock:
            self._discord = discord
            self._started = True
            self._startup_error = None
            self._restart_requested = False
        print("Connexion du bot Discord en cours...", flush=True)
        self._thread = threading.Thread(
            target=self._run,
            name="nathgpt-discord",
            daemon=True,
        )
        self._thread.start()

    def set_result_handler(self, handler):
        """Enregistre le résultat final, même sans client web connecté."""
        self._result_handler = handler

    def set_connection_handler(self, handler):
        """Informe Flask lorsque la liaison Discord devient disponible."""
        self._connection_handler = handler

    def _report_connection(self, connected):
        handler = self._connection_handler
        if not handler:
            return
        try:
            handler(bool(connected))
        except Exception:
            # Une notification de statut ne doit jamais arrêter le bot.
            pass

    def notify_staff_waiting(self, username):
        """Envoie/planifie une alerte privée au staff quand une personne attend."""
        if not self.enabled:
            raise RuntimeError("Le bot Discord n'est pas configuré.")

        with self._lock:
            if username not in self._pending_staff_notifications:
                self._pending_staff_notifications.append(username)
            loop = self._loop
            can_send = bool(self._ready.is_set() and loop and loop.is_running())

        if can_send:
            asyncio.run_coroutine_threadsafe(self._flush_staff_notifications(), loop)

    def category_has_capacity(self):
        """Vérifie la place disponible sans créer ni toucher un salon."""
        if not self.enabled:
            return False

        with self._lock:
            loop = self._loop
            can_check = bool(self._ready.is_set() and loop and loop.is_running())

        if not can_check:
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._category_has_capacity(),
                loop,
            )
            return bool(future.result(timeout=3))
        except Exception:
            return False

    async def _category_has_capacity(self):
        category = self._client.get_channel(self.category_id)
        if category is None:
            category = await self._client.fetch_channel(self.category_id)
        if not isinstance(category, self._discord.CategoryChannel):
            return False
        return len(category.channels) < DISCORD_CATEGORY_CHANNEL_LIMIT

    async def _flush_staff_notifications(self):
        with self._lock:
            waiting_users = list(self._pending_staff_notifications)
            self._pending_staff_notifications.clear()

        failed_users = []
        for username in waiting_users:
            try:
                await self._send_staff_waiting_notification(username)
            except Exception:
                failed_users.append(username)

        if failed_users:
            with self._lock:
                for username in failed_users:
                    if username not in self._pending_staff_notifications:
                        self._pending_staff_notifications.append(username)

    async def _send_staff_waiting_notification(self, username):
        staff_user = self._client.get_user(self.staff_user_id)
        if staff_user is None:
            staff_user = await self._client.fetch_user(self.staff_user_id)
        direct_messages = staff_user.dm_channel or await staff_user.create_dm()
        await direct_messages.send(
            f"<@{self.staff_user_id}> · {username} attend pendant une panne NathGPT."
        )

    def request_reconnect(self, reason=""):
        """Ferme le client Discord actuel pour que la boucle le recrée seule."""
        if not self.enabled:
            return

        with self._lock:
            if self._restart_requested:
                return
            self._restart_requested = True
            self._ready.clear()
            self._report_connection(False)
            client = self._client
            loop = self._loop
            thread_is_alive = bool(self._thread and self._thread.is_alive())

        print(
            "Redémarrage automatique du bot Discord demandé"
            + (f" : {reason}" if reason else ""),
            flush=True,
        )

        if client and loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop)
                return
            except RuntimeError:
                # La boucle vient de s'arrêter : le bloc suivant relancera le client.
                pass

        if not thread_is_alive:
            with self._lock:
                self._started = False
                self._restart_requested = False
            self.start()

    def start_turn(
        self,
        username,
        conversation_id,
        question,
        reference_images=None,
        expects_image=False,
        metadata=None,
    ):
        """Envoie une question et retourne immédiatement l'identifiant de son flux."""
        if not self.enabled:
            raise RuntimeError("Discord n'est pas configuré : DISCORD_TOKEN est manquant.")
        if not self._started:
            self.start()

        if self._startup_error:
            raise RuntimeError(self._startup_error)

        if not self._ready.wait(timeout=self.connect_timeout):
            if self._startup_error:
                raise RuntimeError(self._startup_error)

            raise RuntimeError(
                "Le bot Discord est toujours en cours de connexion. Réessaie "
                "dans quelques secondes ; si le problème persiste, vérifie le "
                "token et Message Content Intent dans Discord Developer Portal."
            )

        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "events": Queue(),
                "username": username,
                "conversation_id": conversation_id,
                "conversation_key": f"{username.casefold()}:{conversation_id}",
                "kind": "chat",
                "metadata": dict(metadata or {}),
                "expects_image": bool(expects_image),
                "text_messages": {},
                "text_message_order": [],
                "text_result_timer": None,
            }

        future = asyncio.run_coroutine_threadsafe(
            self._send_turn(
                job_id,
                username,
                conversation_id,
                question,
                reference_images or [],
            ),
            self._loop,
        )

        try:
            future.result(timeout=30)
        except Exception:
            with self._lock:
                self._jobs.pop(job_id, None)
            raise

        timeout_timer = threading.Timer(
            self.response_timeout,
            self._timeout_job,
            args=(job_id,)
        )
        timeout_timer.daemon = True
        timeout_timer.start()

        return job_id

    def start_cricut_job(
        self,
        username,
        image,
        metadata=None,
        conversation_id=None,
        reuse_channel=False,
    ):
        """Envoie une image Ã  dÃ©composer dans un salon Cricut dÃ©diÃ©."""
        if not self.enabled:
            raise RuntimeError("Discord n'est pas configurÃ© : DISCORD_TOKEN est manquant.")
        if not self._started:
            self.start()
        if self._startup_error:
            raise RuntimeError(self._startup_error)
        if not self._ready.wait(timeout=self.connect_timeout):
            if self._startup_error:
                raise RuntimeError(self._startup_error)
            raise RuntimeError(
                "Le bot Discord est toujours en cours de connexion. Réessaie dans quelques secondes."
            )

        job_id = uuid.uuid4().hex
        conversation_id = conversation_id or f"cricut-{job_id[:12]}"
        with self._lock:
            self._jobs[job_id] = {
                "events": Queue(),
                "username": username,
                "conversation_id": conversation_id,
                "conversation_key": f"{username.casefold()}:{conversation_id}",
                "kind": "cricut",
                "metadata": dict(metadata or {}),
                "cricut_total": 0,
                "cricut_current": 0,
                "cricut_images": [],
                "cricut_completion_timer": None,
            }

        future = asyncio.run_coroutine_threadsafe(
            self._send_cricut_job(
                job_id,
                username,
                conversation_id,
                image,
                reuse_channel=bool(reuse_channel),
            ),
            self._loop,
        )
        try:
            future.result(timeout=30)
        except Exception:
            with self._lock:
                self._jobs.pop(job_id, None)
            raise

        timeout_timer = threading.Timer(
            max(self.response_timeout, 60 * 60),
            self._timeout_job,
            args=(job_id,),
        )
        timeout_timer.daemon = True
        timeout_timer.start()
        return job_id

    def next_event(self, job_id, username, timeout=15):
        with self._lock:
            job = self._jobs.get(job_id)
        if not job or job["username"] != username:
            return {"type": "error", "message": "Cette génération n'existe plus."}

        try:
            return job["events"].get(timeout=timeout)
        except Empty:
            # Le navigateur peut fermer sa connexion exactement pendant la
            # dernière réponse. La conserver permet à Cricut de restaurer les
            # images et les téléchargements au prochain retour sur le site.
            with self._lock:
                current_job = self._jobs.get(job_id)
                if current_job and current_job.get("username") == username:
                    return current_job.get("final_event")
            return None

    def job_conversation(self, job_id, username):
        with self._lock:
            job = self._jobs.get(job_id)

        if not job or job["username"] != username:
            return None

        return job["conversation_id"]

    def _run(self):
        """Garde le client Discord vivant et le relance après toute coupure."""
        retry_delay = self.reconnect_initial_delay

        while self.enabled:
            try:
                asyncio.run(self._run_client())
                reason = "la connexion Discord s'est arrêtée"
            except Exception as error:
                reason = f"erreur Discord {type(error).__name__}"

            self._ready.clear()
            # Si la connexion échoue avant l'évènement on_disconnect, Flask
            # doit tout de même passer immédiatement en mode maintenance.
            self._report_connection(False)
            with self._lock:
                self._loop = None
                self._client = None
                # Une erreur transitoire ne bloque pas les tentatives suivantes.
                self._startup_error = None

            print(
                f"{reason} ; nouvelle tentative dans {retry_delay} secondes...",
                flush=True,
            )
            time.sleep(retry_delay)
            retry_delay = min(60, retry_delay * 2)

        with self._lock:
            self._started = False

    async def _run_client(self):
        self._loop = asyncio.get_running_loop()

        intents = self._discord.Intents.default()
        intents.message_content = True
        self._client = self._discord.Client(intents=intents)
        client = self._client
        disconnect_watchdog = None

        @client.event
        async def on_ready():
            nonlocal disconnect_watchdog
            if disconnect_watchdog and not disconnect_watchdog.done():
                disconnect_watchdog.cancel()
            disconnect_watchdog = None
            self._ready.set()
            self._startup_error = None
            self._restart_requested = False
            self._report_connection(True)
            asyncio.create_task(self._flush_staff_notifications())
            print(f"Bot Discord connecté : {client.user}", flush=True)

        @client.event
        async def on_disconnect():
            nonlocal disconnect_watchdog
            self._ready.clear()
            self._report_connection(False)

            # discord.py tente déjà de se reconnecter seul. Si son mécanisme
            # reste coincé trop longtemps, on ferme proprement le client afin
            # que la boucle _run() recrée une connexion neuve.
            if disconnect_watchdog and not disconnect_watchdog.done():
                return

            async def force_fresh_connection():
                try:
                    await asyncio.sleep(self.disconnect_grace)
                    if self._client is client and not self._ready.is_set():
                        print("Discord toujours déconnecté ; reconnexion forcée...", flush=True)
                        await client.close()
                except asyncio.CancelledError:
                    return

            disconnect_watchdog = asyncio.create_task(force_fresh_connection())

        @client.event
        async def on_message(message):
            await self._handle_message(message)

        @client.event
        async def on_message_edit(before, after):
            await self._handle_message(after)

        try:
            await client.start(self.token, reconnect=True)
        finally:
            self._ready.clear()
            if disconnect_watchdog and not disconnect_watchdog.done():
                disconnect_watchdog.cancel()

    def delete_user_conversations(self, username):
        """Supprime les salons Discord appartenant au compte indiquÃ©.

        La suppression locale n'est faite qu'aprÃ¨s la suppression des salons,
        afin d'Ã©viter de faire croire Ã  l'utilisateur que Discord a Ã©tÃ©
        effacÃ© lorsque le bot n'a pas les droits nÃ©cessaires.
        """
        prefix = f"{username.casefold()}:"

        with self._lock:
            conversation_entries = {
                key: channel_id
                for key, channel_id in self._conversations.items()
                if key.startswith(prefix)
            }

        if conversation_entries:
            if not self.enabled or not self._ready.is_set() or not self._loop:
                raise RuntimeError(
                    "Le bot Discord doit Ãªtre connectÃ© pour supprimer les salons de ce compte."
                )

            future = asyncio.run_coroutine_threadsafe(
                self._delete_channels(list(conversation_entries.values())),
                self._loop,
            )
            try:
                future.result(timeout=45)
            except Exception as error:
                raise RuntimeError(
                    "Impossible de supprimer tous les salons Discord de ce compte. "
                    "VÃ©rifie que le bot a la permission GÃ©rer les salons."
                ) from error

        with self._lock:
            for key in conversation_entries:
                self._conversations.pop(key, None)
            for key in list(self._image_messages):
                if key.startswith(prefix):
                    self._image_messages.pop(key, None)
            for channel_id in conversation_entries.values():
                self._channel_jobs.pop(channel_id, None)

            self._save_conversations()
            self._save_image_messages()

    def delete_configured_category_channels(self):
        """Supprime tous les salons présents dans la catégorie NathGPT configurée."""
        if not self.enabled or not self._ready.is_set() or not self._loop:
            raise RuntimeError(
                "Le bot Discord doit être connecté pour supprimer les salons de la catégorie."
            )

        future = asyncio.run_coroutine_threadsafe(
            self._delete_configured_category_channels(),
            self._loop,
        )
        try:
            deleted_ids, failed_count = future.result(timeout=90)
        except Exception as error:
            raise RuntimeError(
                "Impossible de supprimer les salons de la catégorie. "
                "Vérifie la permission Gérer les salons du bot."
            ) from error

        with self._lock:
            removed_keys = [
                key for key, channel_id in self._conversations.items()
                if channel_id in deleted_ids
            ]
            for key in removed_keys:
                self._conversations.pop(key, None)
                self._image_messages.pop(key, None)
            for channel_id in deleted_ids:
                self._channel_jobs.pop(channel_id, None)
            self._save_conversations()
            self._save_image_messages()

        if failed_count:
            raise RuntimeError(
                f"{len(deleted_ids)} salon(s) supprimé(s), mais {failed_count} n'ont pas pu être supprimé(s)."
            )
        return len(deleted_ids)

    def delete_non_cricut_category_channels(self):
        """Nettoie les salons de discussion en gardant les salons Cricut."""
        if not self.enabled or not self._ready.is_set() or not self._loop:
            raise RuntimeError(
                "Le bot Discord doit Ãªtre connectÃ© pour nettoyer les salons."
            )

        future = asyncio.run_coroutine_threadsafe(
            self._delete_non_cricut_category_channels(),
            self._loop,
        )
        try:
            deleted_ids, failed_count = future.result(timeout=90)
        except Exception as error:
            raise RuntimeError(
                "Impossible de nettoyer les salons Discord non Cricut."
            ) from error

        with self._lock:
            removed_keys = [
                key for key, channel_id in self._conversations.items()
                if channel_id in deleted_ids
            ]
            for key in removed_keys:
                self._conversations.pop(key, None)
                self._image_messages.pop(key, None)
            for channel_id in deleted_ids:
                self._channel_jobs.pop(channel_id, None)
            self._save_conversations()
            self._save_image_messages()

        if failed_count:
            raise RuntimeError(
                f"{len(deleted_ids)} salon(s) supprimÃ©(s), mais {failed_count} n'ont pas pu Ãªtre supprimÃ©s."
            )
        return len(deleted_ids)

    async def _delete_configured_category_channels(self):
        category = self._client.get_channel(self.category_id)
        if category is None:
            category = await self._client.fetch_channel(self.category_id)
        if not isinstance(category, self._discord.CategoryChannel):
            raise RuntimeError("DISCORD_CATEGORY_ID ne correspond pas à une catégorie Discord.")

        deleted_ids = []
        failed_count = 0
        for channel in list(category.channels):
            try:
                await channel.delete(reason="Nettoyage global demandé depuis le panneau staff NathGPT")
                deleted_ids.append(channel.id)
            except self._discord.NotFound:
                deleted_ids.append(channel.id)
            except self._discord.HTTPException:
                failed_count += 1

        return deleted_ids, failed_count

    async def _delete_non_cricut_category_channels(self):
        category = self._client.get_channel(self.category_id)
        if category is None:
            category = await self._client.fetch_channel(self.category_id)
        if not isinstance(category, self._discord.CategoryChannel):
            raise RuntimeError("DISCORD_CATEGORY_ID ne correspond pas Ã  une catÃ©gorie Discord.")

        deleted_ids = []
        failed_count = 0
        for channel in list(category.channels):
            channel_name = str(getattr(channel, "name", "")).casefold()
            channel_topic = str(getattr(channel, "topic", "")).casefold()
            is_cricut = (
                channel_name.startswith("cricut-")
                or "cricut" in channel_topic
            )
            if is_cricut:
                continue
            try:
                await channel.delete(reason="Nettoyage quotidien NathGPT : conservation des salons Cricut")
                deleted_ids.append(channel.id)
            except self._discord.NotFound:
                deleted_ids.append(channel.id)
            except self._discord.HTTPException:
                failed_count += 1

        return deleted_ids, failed_count

    def delete_conversation(self, username, conversation_id):
        """Efface une conversation de dÃ©verrouillage sans bloquer le site."""
        key = f"{username.casefold()}:{conversation_id}"
        with self._lock:
            channel_id = self._conversations.get(key)

        if channel_id and self.enabled and self._ready.is_set() and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._delete_channels([channel_id]), self._loop
                ).result(timeout=20)
            except Exception:
                # L'activation Cricut reste possible mÃªme si un ancien salon
                # Discord ne peut plus Ãªtre supprimÃ©.
                pass

        with self._lock:
            self._conversations.pop(key, None)
            self._image_messages.pop(key, None)
            if channel_id:
                self._channel_jobs.pop(channel_id, None)
            self._save_conversations()
            self._save_image_messages()

    async def _delete_channels(self, channel_ids):
        for channel_id in channel_ids:
            channel = self._client.get_channel(channel_id)

            if channel is None:
                try:
                    channel = await self._client.fetch_channel(channel_id)
                except self._discord.NotFound:
                    continue

            if isinstance(channel, self._discord.TextChannel):
                try:
                    await channel.delete(reason="Suppression d'un compte NathGPT")
                except self._discord.NotFound:
                    continue

    async def _send_turn(
        self,
        job_id,
        username,
        conversation_id,
        question,
        reference_images,
    ):
        channel = await self._get_or_create_channel(username, conversation_id)
        with self._lock:
            self._channel_jobs[channel.id] = job_id

        files = [
            self._discord.File(
                io.BytesIO(image["data"]),
                filename=image["filename"],
            )
            for image in reference_images
        ]

        is_image_follow_up = (
            question.startswith("modify:") or
            question == "png:"
        )

        if is_image_follow_up:
            conversation_key = f"{username.casefold()}:{conversation_id}"

            with self._lock:
                image_message_id = self._image_messages.get(conversation_key)

            if not image_message_id:
                async for message in channel.history(limit=50, oldest_first=False):
                    if (
                        message.author.id == self.target_bot_id and
                        self._image_url_from(message)
                    ):
                        image_message_id = message.id
                        with self._lock:
                            self._image_messages[conversation_key] = image_message_id
                            self._save_image_messages()
                        break

            if not image_message_id:
                raise RuntimeError("Aucune image de référence n'est disponible dans cette discussion.")

            await channel.get_partial_message(image_message_id).reply(
                question,
                files=files,
                mention_author=False,
                allowed_mentions=self._discord.AllowedMentions.none(),
            )

        else:
            await channel.send(
                question,
                files=files,
                allowed_mentions=self._discord.AllowedMentions.none(),
            )
        self._publish(job_id, {"type": "status", "message": "Demande envoyée au moteur d'image..."})

    async def _send_cricut_job(
        self,
        job_id,
        username,
        conversation_id,
        image,
        reuse_channel=False,
    ):
        category = self._client.get_channel(self.category_id)
        if category is None:
            category = await self._client.fetch_channel(self.category_id)
        if not isinstance(category, self._discord.CategoryChannel):
            raise RuntimeError("DISCORD_CATEGORY_ID ne correspond pas à une catégorie Discord.")

        if reuse_channel:
            channel = await self._get_or_create_channel(username, conversation_id)
        else:
            safe_user = re.sub(r"[^a-z0-9-]+", "-", username.casefold()).strip("-") or "utilisateur"
            channel = await category.create_text_channel(
                f"cricut-{safe_user}-{conversation_id[-8:]}"[:100],
                topic=f"Décomposition Cricut de {username}",
                reason="Nouvelle demande Cricut NathGPT",
            )

        with self._lock:
            self._conversations[f"{username.casefold()}:{conversation_id}"] = channel.id
            self._channel_jobs[channel.id] = job_id
            self._save_conversations()

        file = self._discord.File(
            io.BytesIO(image["data"]),
            filename=image["filename"],
        )
        await channel.send(
            "decomp_cricut",
            file=file,
            allowed_mentions=self._discord.AllowedMentions.none(),
        )
        self._publish(
            job_id,
            {"type": "cricut_status", "message": "Analyse de l'image et estimation du temps..."},
        )

    async def _get_or_create_channel(self, username, conversation_id):
        key = f"{username.casefold()}:{conversation_id}"
        with self._lock:
            channel_id = self._conversations.get(key)

        if channel_id:
            channel = self._client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self._client.fetch_channel(channel_id)
                except self._discord.HTTPException:
                    channel = None
            if isinstance(channel, self._discord.TextChannel):
                return channel

        category = self._client.get_channel(self.category_id)
        if category is None:
            category = await self._client.fetch_channel(self.category_id)
        if not isinstance(category, self._discord.CategoryChannel):
            raise RuntimeError("DISCORD_CATEGORY_ID ne correspond pas à une catégorie Discord.")

        safe_user = re.sub(r"[^a-z0-9-]+", "-", username.casefold()).strip("-") or "utilisateur"
        is_cricut = conversation_id.startswith("cricut-")
        channel_name = (
            f"cricut-{safe_user}-{conversation_id[-8:]}"
            if is_cricut
            else f"nathgpt-{safe_user}-{conversation_id[:8]}"
        )[:100]
        channel = await category.create_text_channel(
            channel_name,
            topic=(
                f"Décomposition Cricut de {username}"
                if is_cricut
                else f"Conversation NathGPT de {username}"
            ),
            reason=(
                "Nouvelle demande Cricut NathGPT"
                if is_cricut
                else "Nouvelle conversation NathGPT"
            ),
        )

        with self._lock:
            self._conversations[key] = channel.id
            self._save_conversations()
        return channel

    async def _handle_message(self, message):
        if message.author.id != self.target_bot_id:
            return

        with self._lock:
            job_id = self._channel_jobs.get(message.channel.id)

            job = self._jobs.get(job_id) if job_id else None

        if not job_id or not job:
            return

        if job.get("kind") == "cricut":
            self._handle_cricut_message(job_id, message)
            return

        image_url = self._image_url_from(message)
        if image_url:
            with self._lock:
                self._image_messages[job["conversation_key"]] = message.id
                self._save_image_messages()

            self._publish(job_id, {"type": "image", "url": image_url}, final=True)
            return

        content = (message.content or "").strip()
        if not content:
            return

        # Certains bots annoncent "Image gÃ©nÃ©rÃ©e" avant d'ajouter le vrai
        # fichier dans un second message. Pour une demande d'image, cette
        # annonce reste une Ã©tape d'attente : seul le fichier/embedd image
        # termine la gÃ©nÃ©ration cÃ´tÃ© site.
        if job.get("expects_image") and self._is_image_completion_notice(content):
            self._publish(
                job_id,
                {"type": "status", "message": "Image prÃªte, rÃ©ception du fichier..."},
            )
            return

        if self._is_progress(content):
            self._publish(job_id, {"type": "status", "message": content})
            return

        self._queue_text_response(job_id, message.id, content)

    def _queue_text_response(self, job_id, message_id, content):
        """Regroupe les messages successifs du bot dans une seule rÃ©ponse."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            text_messages = job["text_messages"]
            if message_id not in text_messages:
                job["text_message_order"].append(message_id)
            text_messages[message_id] = content

            previous_timer = job.get("text_result_timer")
            if previous_timer:
                previous_timer.cancel()

            result_timer = threading.Timer(
                TEXT_RESPONSE_SETTLE_SECONDS,
                self._publish_combined_text,
                args=(job_id,),
            )
            result_timer.daemon = True
            job["text_result_timer"] = result_timer
            result_timer.start()

    def _publish_combined_text(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            parts = [
                job["text_messages"][message_id]
                for message_id in job["text_message_order"]
                if job["text_messages"].get(message_id)
            ]
            job["text_result_timer"] = None

        if parts:
            self._publish(
                job_id,
                {"type": "text", "message": "\n\n".join(parts)},
                final=True,
            )

    def _handle_cricut_message(self, job_id, message):
        """Traduit les messages de progression Cricut en Ã©vÃ©nements web."""
        content = (message.content or "").strip()
        image_urls = self._image_urls_from(message)

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            for image_url in image_urls:
                if image_url not in job["cricut_images"]:
                    job["cricut_images"].append(image_url)

        plan_match = re.search(
            r"(\d+)\s+images?\s+[àa]\s+g[ée]n[ée]rer.*?"
            r"(?:image\s+g[ée]n[ée]r[ée]e?\s*)?(\d+)\s*/\s*(\d+)",
            content,
            re.I | re.S,
        )
        sticker_match = re.search(
            r"(?:sticker|image)\s*(\d+)\s*/\s*(\d+)",
            content,
            re.I,
        )

        if plan_match:
            total = int(plan_match.group(1))
            current = int(plan_match.group(2))
            denominator = int(plan_match.group(3))
            total = denominator if denominator else total
            remaining_match = re.search(r"temps\s+restant\s*:?\s*(.+?)(?:\s+image\s+g|$)", content, re.I | re.S)
            remaining = remaining_match.group(1).strip() if remaining_match else "Estimation en cours"
            self._publish_cricut_progress(job_id, current, total, remaining, plan=True)
        elif sticker_match:
            self._publish_cricut_progress(
                job_id,
                int(sticker_match.group(1)),
                int(sticker_match.group(2)),
                None,
                plan=False,
            )
        elif content:
            self._publish(job_id, {"type": "cricut_status", "message": content})

    def _publish_cricut_progress(self, job_id, current, total, remaining, plan):
        current = max(0, current)
        total = max(1, total)
        current = min(current, total)

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["cricut_current"] = max(job.get("cricut_current", 0), current)
            job["cricut_total"] = max(job.get("cricut_total", 0), total)
            current = job["cricut_current"]
            total = job["cricut_total"]

        self._publish(
            job_id,
            {
                "type": "cricut_plan" if plan else "cricut_progress",
                "current": current,
                "total": total,
                "remaining": remaining,
            },
        )

        if current >= total:
            self._schedule_cricut_completion(job_id)

    def _schedule_cricut_completion(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            previous_timer = job.get("cricut_completion_timer")
            if previous_timer:
                previous_timer.cancel()
            timer = threading.Timer(2.0, self._publish_cricut_completion, args=(job_id,))
            timer.daemon = True
            job["cricut_completion_timer"] = timer
            timer.start()

    def _publish_cricut_completion(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["cricut_completion_timer"] = None
            images = list(job.get("cricut_images", []))

        self._publish(
            job_id,
            {"type": "cricut_complete", "images": images},
            final=True,
        )

    def _image_urls_from(self, message):
        urls = []
        for attachment in message.attachments:
            content_type = attachment.content_type or ""
            filename = getattr(attachment, "filename", "") or ""
            if (
                content_type.startswith("image/") or
                re.search(r"\.(png|jpe?g|webp|gif|avif)(?:\?|$)", filename, re.I) or
                re.search(r"\.(png|jpe?g|webp|gif|avif)(?:\?|$)", attachment.url, re.I)
            ):
                urls.append(attachment.url)

        for embed in message.embeds:
            if embed.image and embed.image.url:
                urls.append(embed.image.url)
            if embed.thumbnail and embed.thumbnail.url:
                urls.append(embed.thumbnail.url)
            if getattr(embed, "type", "") == "image" and getattr(embed, "url", None):
                urls.append(embed.url)

        urls.extend(re.findall(
            r"https?://\S+\.(?:png|jpe?g|webp|gif|avif)(?:\?\S*)?",
            message.content or "",
            re.I,
        ))
        return list(dict.fromkeys(urls))

    def _image_url_from(self, message):
        urls = self._image_urls_from(message)
        return urls[0] if urls else None

    @staticmethod
    def _is_image_completion_notice(content):
        text = " ".join((content or "").casefold().split())
        text = text.replace("**", "").replace("__", "")
        return bool(re.search(
            r"(?:image\s+(?:g[ée]n[ée]r[ée]e?|generee|pr[ée]te|prete|"
            r"termin[ée]e?|finie)|r[ée]ponds?\s+[àa]\s+cette\s+image|"
            r"(?:modify:|png:)\s*(?:ton|votre|le|la)?)",
            text,
            re.I,
        ))

    @staticmethod
    def _is_progress(content):
        """Retourne True uniquement pour les messages de progression.

        Une rÃ©ponse normale peut parler d'une image "gÃ©nÃ©rÃ©e" ou d'une
        "crÃ©ation". Ces mots seuls ne doivent jamais masquer une rÃ©ponse
        finale : seuls les courts messages indiquant explicitement une attente
        ou un pourcentage sont traitÃ©s comme une progression.
        """
        text = " ".join((content or "").split())
        if not text:
            return False

        # Une vraie rÃ©ponse peut exceptionnellement citer un pourcentage ;
        # les statuts de gÃ©nÃ©ration, eux, restent volontairement courts.
        if len(text) > 320:
            return False

        return bool(re.search(
            r"(?:\b\d{1,3}\s*%|demande\s+en\s+attente|request\s+pending|"
            r"r[ée]flexion\s+en\s+cours|\bthinking\b|\bqueued?\b|\bqueue\b|"
            r"(?:g[ée]n[ée]ration|generation|cr[ée]ation|creation|image)"
            r".{0,80}(?:en\s+cours|charg|processing|render|patiente|attend))",
            text,
            re.I,
        ))

    def _publish(self, job_id, event, final=False):
        result_handler = None
        result_context = None

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["events"].put(event)
            if final:
                job["final_event"] = event
                cricut_completion_timer = job.get("cricut_completion_timer")
                if cricut_completion_timer:
                    cricut_completion_timer.cancel()
                    job["cricut_completion_timer"] = None
                text_result_timer = job.get("text_result_timer")
                if text_result_timer:
                    text_result_timer.cancel()
                    job["text_result_timer"] = None
                result_handler = self._result_handler
                result_context = (
                    job["username"],
                    job["conversation_id"],
                    dict(job.get("metadata") or {}),
                )
                for channel_id, active_job_id in list(self._channel_jobs.items()):
                    if active_job_id == job_id:
                        del self._channel_jobs[channel_id]
                cleanup_timer = threading.Timer(
                    900,
                    self._forget_job,
                    args=(job_id,)
                )
                cleanup_timer.daemon = True
                cleanup_timer.start()

        if result_handler and result_context:
            enriched_event = dict(event)
            if result_context[2]:
                enriched_event["_job_metadata"] = result_context[2]
            result_handler(
                result_context[0],
                result_context[1],
                enriched_event,
            )

    def _forget_job(self, job_id):
        with self._lock:
            self._jobs.pop(job_id, None)

    def _timeout_job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)

            if not job or job_id not in self._channel_jobs.values():
                return

        self._publish(
            job_id,
            {
                "type": "error",
                "message": (
                    "Le bot Discord n'a pas donné de résultat final. "
                    "Réessaie dans quelques instants."
                ),
            },
            final=True,
        )

    def _load_conversations(self):
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_conversations(self):
        temporary = self.store_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._conversations, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.store_path)

    def _load_image_messages(self):
        try:
            return json.loads(self.image_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_image_messages(self):
        temporary = self.image_store_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._image_messages, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.image_store_path)
