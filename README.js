const chargeDescriptions = {
  express:
    "Express (Fast): prioritizes charging speed using Dell fast-charge behavior.",
  standard:
    "Standard: balances normal charge time with everyday battery use.",
  adaptive:
    "Adaptive: firmware adjusts charging around the typical usage pattern.",
  custom:
    "Custom: uses the start and stop thresholds below. Applying thresholds also activates Custom mode.",
};

const thermalDescriptions = {
  cool:
    "Cool: prioritizes lower surface temperature and can increase fan activity.",
  quiet:
    "Quiet: prioritizes lower fan noise and can trade some performance for acoustics.",
  balanced:
    "Balanced: balances performance, fan noise and system temperature for normal use.",
  performance:
    "Performance: prioritizes sustained performance and can use more aggressive cooling.",
};

const state = {
  chargeMode: "custom",
  chargeStart: 50,
  chargeEnd: 55,
  thermalMode: "balanced",
  saverEnabled: false,
};

const toast = document.querySelector("#toast");
const demoLog = document.querySelector("#demo-log");
let toastTimer;

function announce(message) {
  demoLog.textContent = message;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toast.classList.remove("show");
  }, 2200);
}

function setDemoPanel(panelId) {
  document.querySelectorAll(".demo-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === panelId);
  });

  document.querySelectorAll(".demo-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panelId);
  });
}

function updateChargeDescription() {
  const mode = document.querySelector("#demo-charge-mode").value;
  document.querySelector("#charge-mode-note").textContent =
    chargeDescriptions[mode] ?? "";
}

function updateThermalDescription(selectId, noteId) {
  const mode = document.querySelector(selectId).value;
  document.querySelector(noteId).textContent =
    thermalDescriptions[mode] ?? "";
}

function validThresholds(start, end) {
  return (
    start >= 50 &&
    start <= 95 &&
    end >= 55 &&
    end <= 100 &&
    end - start >= 5
  );
}

document.querySelectorAll(".demo-tab").forEach((button) => {
  button.addEventListener("click", () => {
    setDemoPanel(button.dataset.panel);
  });
});

document.querySelector("#demo-charge-mode").addEventListener("change", () => {
  updateChargeDescription();
});

document.querySelector("#demo-apply-charge").addEventListener("click", () => {
  const mode = document.querySelector("#demo-charge-mode").value;
  state.chargeMode = mode;
  document.querySelector("#demo-current-charge").textContent = mode;
  announce(`Simulated charging mode applied and verified: ${mode}.`);
});

document
  .querySelector("#demo-apply-thresholds")
  .addEventListener("click", () => {
    const start = Number(document.querySelector("#demo-start").value);
    const end = Number(document.querySelector("#demo-end").value);

    if (!validThresholds(start, end)) {
      announce(
        "Validation failed: start 50–95%, end 55–100%, with at least a 5% gap.",
      );
      return;
    }

    state.chargeMode = "custom";
    state.chargeStart = start;
    state.chargeEnd = end;

    document.querySelector("#demo-charge-mode").value = "custom";
    document.querySelector("#demo-current-charge").textContent = "custom";
    document.querySelector("#demo-current-thresholds").textContent =
      `${start}–${end} %`;
    updateChargeDescription();

    announce(`Simulated thresholds applied and verified: ${start}% → ${end}%.`);
  });

document.querySelector("#demo-thermal-mode").addEventListener("change", () => {
  updateThermalDescription("#demo-thermal-mode", "#thermal-mode-note");
});

document.querySelector("#demo-apply-thermal").addEventListener("click", () => {
  const mode = document.querySelector("#demo-thermal-mode").value;
  state.thermalMode = mode;
  document.querySelector("#demo-current-thermal").textContent = mode;
  announce(`Simulated cooling profile applied and verified: ${mode}.`);
});

document.querySelector("#demo-saver-thermal").addEventListener("change", () => {
  updateThermalDescription("#demo-saver-thermal", "#saver-thermal-note");
});

document.querySelector("#demo-saver-switch").addEventListener("change", (event) => {
  state.saverEnabled = event.target.checked;
  announce(
    state.saverEnabled
      ? "Simulated Battery Saver session enabled."
      : "Simulated Battery Saver session disabled and owned values restored.",
  );
});

document.querySelector("#demo-refresh").addEventListener("click", () => {
  announce(
    `State refreshed: charge ${state.chargeMode}, thermal ${state.thermalMode}, saver ${
      state.saverEnabled ? "on" : "off"
    }.`,
  );
});

updateChargeDescription();
updateThermalDescription("#demo-thermal-mode", "#thermal-mode-note");
updateThermalDescription("#demo-saver-thermal", "#saver-thermal-note");
