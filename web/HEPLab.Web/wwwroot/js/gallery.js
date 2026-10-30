(() => {
  const gallery = document.querySelector(".zgallery");
  if (!gallery) return;
  const cards = [...gallery.querySelectorAll(".zgallery-card")];
  gallery.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => {
    const selected = button.dataset.filter;
    gallery.querySelectorAll("[data-filter]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    cards.forEach(card => { card.hidden = selected !== "all" && card.dataset.kind !== selected; });
    const visible = cards.filter(card => !card.hidden).length;
    gallery.querySelector('#gallery-count').textContent = `${visible} ${visible === 1 ? 'example' : 'examples'} · ${button.textContent.trim()}`;
  }));
})();
