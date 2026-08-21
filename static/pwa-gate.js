/* NathGPT est réservé sur téléphone à son application ajoutée à l'écran d'accueil. */
(() => {
    const isMobile = /Android|iPhone|iPad|iPod|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;

    if (!isMobile || isStandalone) {
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
