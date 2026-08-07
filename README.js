const state = {
  chargeMode: "custom",
  chargeStart: 50,
  chargeEnd: 55,
  thermal: "quiet",
  saverActive: true,
};

const toast = document.querySelector("#toast");
const log = document.querySelector("#demo-log");
let toastTimer;

function announce(message) {
  log.textContent = message;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function openPanel(panelId) {
  document.querySelectorAll(".app-panel").forEach((panel) => {
    const selected = panel.id === panelId;
    panel.hidden = !selected;
  });
  document.querySelectorAll(".app-nav").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panelId);
  });
}

document.querySelectorAll(".app-nav").forEach((button) => {
  button.addEventListener("click", () => openPanel(button.dataset.panel));
});

document.querySelector("#apply-charge-mode").addEventListener("click", () => {
  state.chargeMode = document.querySelector("#charge-mode").value;
  announce(`Simulated charge mode verified: ${state.chargeMode}.`);
});

document.querySelector("#apply-thresholds").addEventListener("click", () => {
  const start = Number(document.querySelector("#start-threshold").value);
  const end = Number(document.querySelector("#end-threshold").value);

  if (start < 50 || start > 95 || end < 55 || end > 100 || end - start < 5) {
    announce("Validation failed: use a valid custom charging interval.");
    return;
  }

  state.chargeMode = "custom";
  state.chargeStart = start;
  state.chargeEnd = end;
  document.querySelector("#charge-mode").value = "custom";
  announce(`Simulated thresholds verified: ${start}% → ${end}%.`);
});

document.querySelector("#apply-thermal").addEventListener("click", () => {
  state.thermal = document.querySelector("#thermal-mode").value;
  document.querySelector("#thermal-current").textContent = state.thermal;
  announce(`Simulated thermal profile verified: ${state.thermal}.`);
});

document.querySelector("#saver-switch").addEventListener("change", (event) => {
  state.saverActive = event.target.checked;
  document.querySelector("#activation-source").textContent = state.saverActive
    ? "manual"
    : "inactive";
  announce(
    state.saverActive
      ? "Battery Saver enabled in the simulation."
      : "Battery Saver disabled; simulated owned values restored.",
  );
});

document.querySelector("#save-settings").addEventListener("click", () => {
  announce("Simulated Battery Saver settings saved.");
});

document.querySelector("#refresh-demo").addEventListener("click", () => {
  announce(
    `State refreshed: charge ${state.chargeMode}, thermal ${state.thermal}, saver ${state.saverActive ? "on" : "off"}.`,
  );
});
