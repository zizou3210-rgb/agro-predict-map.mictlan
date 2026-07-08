let deferredInstallPrompt = null;

const statusNode = document.getElementById("launcher-status");
const installButton = document.getElementById("install-app");
const iosHint = document.getElementById("ios-install-hint");

const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
const isStandalone =
  window.matchMedia("(display-mode: standalone)").matches ||
  window.navigator.standalone === true;

const setStatus = (message) => {
  if (statusNode) {
    statusNode.textContent = message;
  }
};

const updateLauncherState = () => {
  if (!installButton) {
    return;
  }

  if (isStandalone) {
    installButton.hidden = true;
    if (iosHint) {
      iosHint.hidden = true;
    }
    setStatus("The app is already installed and running in standalone mode.");
    return;
  }

  if (deferredInstallPrompt) {
    installButton.hidden = false;
    setStatus("You can install this app as a standalone launcher on this device.");
    return;
  }

  if (isIos) {
    installButton.hidden = true;
    if (iosHint) {
      iosHint.hidden = false;
    }
    setStatus("On iOS, install from Safari using Share > Add to Home Screen.");
    return;
  }

  installButton.hidden = true;
  setStatus("If your browser supports it, the install option will appear for this app.");
};

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  updateLauncherState();
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  updateLauncherState();
});

if (installButton) {
  installButton.addEventListener("click", async () => {
    if (!deferredInstallPrompt) {
      updateLauncherState();
      return;
    }

    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    updateLauncherState();
  });
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      if ("caches" in window) {
        const cacheKeys = await window.caches.keys();
        await Promise.all(cacheKeys.map((key) => window.caches.delete(key)));
      }
      setStatus("Offline cache was disabled for this development build. Reload if you were using a cached copy.");
    } catch (error) {
      console.error("Could not clear service workers or caches", error);
      setStatus("The app loads, but the browser cache could not be fully cleared.");
    }
  });
}

updateLauncherState();
