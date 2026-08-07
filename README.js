const chargeDescriptions = {
  express: "Express: prioritizes charging speed.",
  standard: "Standard: normal everyday charging policy.",
  adaptive: "Adaptive: firmware adjusts charging to usage patterns.",
  custom: "Custom: uses the thresholds below and becomes active when they are applied.",
};
const thermalDescriptions = {
  cool: "Cool: prioritizes lower surface temperature.",
  quiet: "Quiet: prioritizes lower fan noise.",
  balanced: "Balanced: general-purpose balance of performance and acoustics.",
  performance: "Performance: prioritizes sustained performance.",
};
const state = { chargeMode: "custom", chargeStart: 50, chargeEnd: 55, thermalMode: "balanced" };
const demoLog = document.querySelector("#demo-log");
function setPanel(panelId) {
  document.querySelectorAll(".demo-panel").forEach((panel) => panel.classList.toggle("active", panel.id === panelId));
  document.querySelectorAll(".demo-tab").forEach((button) => button.classList.toggle("active", button.dataset.panel === panelId));
}
function log(message) { demoLog.textContent = message; }
function updateChargeDescription() {
  const mode = document.querySelector("#demo-charge-mode").value;
  document.querySelector("#charge-mode-note").textContent = chargeDescriptions[mode] ?? "";
}
function updateThermalDescription(selectId, noteId) {
  const mode = document.querySelector(selectId).value;
  document.querySelector(noteId).textContent = thermalDescriptions[mode] ?? "";
}
function validThresholds(start, end) {
  return start >= 50 && start <= 95 && end >= 55 && end <= 100 && end - start >= 5;
}
document.querySelectorAll(".demo-tab").forEach((button) => button.addEventListener("click", () => setPanel(button.dataset.panel)));
document.querySelector("#demo-charge-mode").addEventListener("change", updateChargeDescription);
document.querySelector("#demo-apply-charge").addEventListener("click", () => {
  const mode = document.querySelector("#demo-charge-mode").value;
  state.chargeMode = mode;
  document.querySelector("#demo-current-charge").textContent = mode;
  log(`Simulated charge mode applied: ${mode}.`);
});
document.querySelector("#demo-apply-thresholds").addEventListener("click", () => {
  const start = Number(document.querySelector("#demo-start").value);
  const end = Number(document.querySelector("#demo-end").value);
  if (!validThresholds(start, end)) {
    log("Validation failed: start 50–95, end 55–100, minimum gap 5.");
    return;
  }
  state.chargeMode = "custom";
  state.chargeStart = start;
  state.chargeEnd = end;
  document.querySelector("#demo-charge-mode").value = "custom";
  document.querySelector("#demo-current-charge").textContent = "custom";
  document.querySelector("#demo-current-thresholds").textContent = `${start}–${end} %`;
  updateChargeDescription();
  log(`Simulated thresholds applied: ${start}% → ${end}%.`);
});
document.querySelector("#demo-thermal-mode").addEventListener("change", () => updateThermalDescription("#demo-thermal-mode", "#thermal-mode-note"));
document.querySelector("#demo-apply-thermal").addEventListener("click", () => {
  const mode = document.querySelector("#demo-thermal-mode").value;
  state.thermalMode = mode;
  document.querySelector("#demo-current-thermal").textContent = mode;
  log(`Simulated thermal profile applied: ${mode}.`);
});
document.querySelector("#demo-saver-thermal").addEventListener("change", () => updateThermalDescription("#demo-saver-thermal", "#saver-thermal-note"));
updateChargeDescription();
updateThermalDescription("#demo-thermal-mode", "#thermal-mode-note");
updateThermalDescription("#demo-saver-thermal", "#saver-thermal-note");
