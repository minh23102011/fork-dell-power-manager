const state = {
  chargeMode: "custom",
  chargeStart: 50,
  chargeEnd: 80,
  thermal: "balanced",
  saverActive: false,
  savedSettings: false,
};

const selectors = {
  tabs: ".app-tab, .footer-tab",
  panels: ".app-panel",
};

const toast = document.querySelector("#toast");
const log = document.querySelector("#demo-log");
let toastTimer;

function announce(message) {
  log.textContent = message;
  toast.textContent = message;
  toast.classList.add("show");

  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(
    () => toast.classList.remove("show"),
    2300,
  );
}

function openPanel(panelId) {
  document.querySelectorAll(selectors.panels).forEach((panel) => {
    const selected = panel.id === panelId;
    panel.hidden = !selected;
    panel.classList.toggle("active", selected);
  });

  document.querySelectorAll(selectors.tabs).forEach((tab) => {
    const selected = tab.dataset.panel === panelId;
    tab.classList.toggle("active", selected);

    if (tab.matches(".app-tab")) {
      tab.setAttribute("aria-selected", String(selected));
    }
  });
}

document.querySelectorAll(selectors.tabs).forEach((tab) => {
  tab.addEventListener("click", () => {
    openPanel(tab.dataset.panel);
  });
});

document.querySelector("#apply-charge-mode").addEventListener(
  "click",
  () => {
    const mode = document.querySelector("#charge-mode").value;
    state.chargeMode = mode;
    announce(
      `Simulated charge mode verified: ${mode}. Previous raw mode was saved for rollback.`,
    );
  },
);

document.querySelector("#apply-thresholds").addEventListener(
  "click",
  () => {
    const start = Number(
      document.querySelector("#start-threshold").value,
    );
    const end = Number(
      document.querySelector("#end-threshold").value,
    );

    if (start < 50 || start > 95) {
      announce("Validation failed: start must be between 50% and 95%.");
      return;
    }

    if (end < 55 || end > 100) {
      announce("Validation failed: end must be between 55% and 100%.");
      return;
    }

    if (end - start < 5) {
      announce(
        "Validation failed: end must be at least 5% above start.",
      );
      return;
    }

    state.chargeMode = "custom";
    state.chargeStart = start;
    state.chargeEnd = end;
    document.querySelector("#charge-mode").value = "custom";

    announce(
      `Simulated custom thresholds verified: ${start}% → ${end}%.`,
    );
  },
);

document.querySelector("#apply-thermal").addEventListener(
  "click",
  () => {
    const profile = document.querySelector("#thermal-mode").value;
    state.thermal = profile;
    document.querySelector("#thermal-current").textContent = profile;

    const detail = profile === "cool"
      ? "The simulated cooling response increased."
      : "Kernel read-back matched the requested profile.";

    announce(`Simulated thermal profile verified: ${profile}. ${detail}`);
  },
);

document.querySelector("#saver-switch").addEventListener(
  "change",
  (event) => {
    const active = event.target.checked;
    state.saverActive = active;

    const activation = document.querySelector("#activation-source");
    activation.textContent = active ? "manual" : "inactive";

    if (active) {
      const brightness = document.querySelector("#brightness-cap").value;
      const refresh = document.querySelector("#refresh-rate").value;
      const cpu = document.querySelector("#cpu-cap").value;
      const profile = document.querySelector(
        "#saver-power-profile",
      ).value;
      const thermal = document.querySelector(
        "#saver-thermal-profile",
      ).value;

      document.querySelector(
        "#power-profile-current",
      ).textContent = profile;
      document.querySelector("#thermal-current").textContent = thermal;

      announce(
        `Battery Saver enabled: ${brightness}% brightness, ${refresh} Hz, ${cpu}% CPU cap.`,
      );
      return;
    }

    document.querySelector(
      "#power-profile-current",
    ).textContent = "balanced";
    document.querySelector("#thermal-current").textContent = state.thermal;

    announce(
      "Battery Saver disabled. Simulated settings still owned by PowerDeck were restored.",
    );
  },
);

document.querySelector("#save-settings").addEventListener(
  "click",
  () => {
    state.savedSettings = true;
    announce("Simulated Battery Saver settings saved.");
  },
);

document.querySelector("#refresh-demo").addEventListener(
  "click",
  () => {
    announce(
      `State refreshed: charge ${state.chargeMode}, thermal ${state.thermal}, saver ${state.saverActive ? "on" : "off"}.`,
    );
  },
);

document.querySelector("#close-demo").addEventListener(
  "click",
  () => {
    announce(
      "This is an embedded simulation, so the demo window remains open.",
    );
  },
);
