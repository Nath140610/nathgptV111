/* NathGPT est réservé sur téléphone à son application ajoutée à l'écran d'accueil. */
(() => {
    if (document.body.classList.contains("staff-page")) {
        return;
    }

    const isMobile = /Android|iPhone|iPad|iPod|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;

    const requiresPwaInstall = isMobile && !isStandalone;

    if (!requiresPwaInstall) {
        const startNotificationGate = () => {
            if (!("Notification" in window)) {
                return;
            }
            if (Notification.permission === "granted") {
                syncNotificationSubscription().catch(() => {});
                return;
            }
            renderNotificationGate();
        };

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", startNotificationGate, { once: true });
        }
        else {
            startNotificationGate();
        }
        return;
    }

    document.documentElement.classList.add("pwa-install-required");
    let deferredInstallPrompt = null;

    // Permet au navigateur Android de proposer réellement l'installation,
    // même lorsque la personne arrive pour la première fois sur /login.
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    }

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;
        const installButton = document.querySelector("[data-pwa-install]");
        if (installButton) {
            installButton.hidden = false;
        }
    });

    const isAppleMobile = /iPhone|iPad|iPod/i.test(navigator.userAgent);

    function urlBase64ToUint8Array(value) {
        const padding = "=".repeat((4 - value.length % 4) % 4);
        const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
        const raw = window.atob(base64);
        return Uint8Array.from(raw, (character) => character.charCodeAt(0));
    }

    async function syncNotificationSubscription() {
        if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
            return;
        }

        const registration = await navigator.serviceWorker.register("/service-worker.js");
        const configResponse = await fetch("/api/notifications/config", { cache: "no-store" });
        const config = await configResponse.json();
        if (!configResponse.ok || !config.enabled || !config.public_key) {
            return;
        }

        let subscription = await registration.pushManager.getSubscription();
        if (!subscription) {
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(config.public_key)
            });
        }

        await fetch("/api/notifications/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscription)
        });
    }

    function renderNotificationGate() {
        if (document.getElementById("notificationRequiredGate")) {
            return;
        }

        const gate = document.createElement("main");
        gate.id = "notificationRequiredGate";
        gate.className = "pwa-install-gate notification-required-gate";
        gate.setAttribute("role", "dialog");
        gate.setAttribute("aria-modal", "true");
        gate.setAttribute("aria-label", "Activer les notifications");
        gate.innerHTML = `
            <div class="pwa-install-glow glow-one"></div><div class="pwa-install-glow glow-two"></div>
            <div class="pwa-install-card notification-required-card">
                <div class="notification-required-icon" aria-hidden="true">✦</div>
                <span class="pwa-install-kicker">NATHGPT</span>
                <h1>Active les notifications pour continuer</h1>
                <p>Tu recevras une alerte quand une image ou une demande Cricut est prete, meme si NathGPT est en arriere-plan.</p>
                <button type="button" class="pwa-install-button" data-enable-notifications>Activer les notifications</button>
                <small data-notification-help>Cette autorisation est necessaire pour utiliser NathGPT.</small>
            </div>
        `;

        const button = gate.querySelector("[data-enable-notifications]");
        const help = gate.querySelector("[data-notification-help]");

        const checkPermission = async () => {
            if (Notification.permission === "granted") {
                button.disabled = true;
                button.textContent = "Notifications activees";
                help.textContent = "Configuration de tes alertes...";
                try {
                    await syncNotificationSubscription();
                }
                catch (_) {
                    // L'alerte locale reste disponible si les push de fond ne sont pas configures.
                }
                gate.classList.add("is-leaving");
                window.setTimeout(() => gate.remove(), 320);
                return;
            }

            if (Notification.permission === "denied") {
                button.textContent = "Verifier l'autorisation";
                help.textContent = "Les notifications sont bloquees. Active-les dans les reglages du navigateur, puis appuie ici.";
                return;
            }

            button.disabled = true;
            button.textContent = "Demande d'autorisation...";
            const permission = await Notification.requestPermission();
            button.disabled = false;
            if (permission === "granted") {
                await checkPermission();
            }
            else {
                button.textContent = "Reessayer";
                help.textContent = "Sans cette autorisation, NathGPT ne peut pas continuer.";
            }
        };

        button.addEventListener("click", () => {
            checkPermission().catch(() => {
                button.disabled = false;
                button.textContent = "Reessayer";
                help.textContent = "Impossible d'activer les notifications sur cet appareil.";
            });
        });
        document.body.appendChild(gate);
    }

    const renderGate = () => {
        const gate = document.createElement("main");
        gate.id = "pwaInstallGate";
        gate.className = "pwa-install-gate";
        gate.setAttribute("role", "dialog");
        gate.setAttribute("aria-modal", "true");
        gate.setAttribute("aria-label", "Installer NathGPT");
        gate.innerHTML = `
            <div class="pwa-install-glow glow-one"></div><div class="pwa-install-glow glow-two"></div>
            <div class="pwa-install-card">
                <img src="/logo.png" alt="" class="pwa-install-logo">
                <span class="pwa-install-kicker">NATHGPT APP</span>
                <h1>Ouvre NathGPT comme une vraie application</h1>
                <p>Pour utiliser NathGPT sur téléphone, ajoute-le d’abord à ton écran d’accueil.</p>
                <ol class="pwa-install-steps"></ol>
                <button type="button" class="pwa-install-button" data-pwa-install hidden>Installer NathGPT</button>
                <small>Une fois ajouté, ouvre NathGPT depuis son icône sur l’écran d’accueil.</small>
            </div>
        `;

        const steps = gate.querySelector(".pwa-install-steps");
        const instructions = isAppleMobile
            ? [
                "Ouvre ce lien dans Safari.",
                "Appuie sur le bouton Partager en bas de l’écran.",
                "Choisis « Sur l’écran d’accueil », puis « Ajouter ».",
                "Ouvre ensuite l’icône NathGPT ajoutée à ton téléphone."
            ]
            : [
                "Ouvre le menu ⋮ de ton navigateur.",
                "Choisis « Installer l’application » ou « Ajouter à l’écran d’accueil ».",
                "Valide l’ajout, puis ouvre l’icône NathGPT sur ton écran d’accueil."
            ];

        instructions.forEach((instruction, index) => {
            const item = document.createElement("li");
            item.innerHTML = `<b>${index + 1}</b><span></span>`;
            item.querySelector("span").textContent = instruction;
            steps.appendChild(item);
        });

        gate.querySelector("[data-pwa-install]").addEventListener("click", async () => {
            if (!deferredInstallPrompt) {
                return;
            }
            const button = gate.querySelector("[data-pwa-install]");
            button.disabled = true;
            button.textContent = "Installation…";
            deferredInstallPrompt.prompt();
            await deferredInstallPrompt.userChoice;
            deferredInstallPrompt = null;
            button.hidden = true;
        });

        document.body.appendChild(gate);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", renderGate, { once: true });
    }
    else {
        renderGate();
    }
})();
