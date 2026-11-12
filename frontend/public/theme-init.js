// Applies the saved theme before first paint (an external file, so the page's strict CSP holds).
(function () {
  var pref = "system";
  try {
    pref = localStorage.getItem("kestrel.theme") || "system";
  } catch (e) {}
  var dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
