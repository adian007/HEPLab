(() => {
  let theme = "dark";
  try { theme = localStorage.getItem("heplab-theme") || theme; } catch { /* Storage is optional. */ }
  if (!["dark", "light", "auto"].includes(theme)) theme = "dark";
  const resolved = theme === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : theme;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.bsTheme = resolved;
})();
