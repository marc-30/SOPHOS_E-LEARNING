// SOPHOS ACADÉMIE — petits comportements du site

// Menu mobile (bouton ☰)
const entete = document.querySelector(".entete");
const burger = document.querySelector(".burger");
if (burger) {
  burger.addEventListener("click", () => entete.classList.toggle("menu-ouvert"));
}

// Menu « Cours » : ouverture au clic (utile sur mobile et tablette)
const deroulant = document.querySelector(".deroulant");
if (deroulant) {
  deroulant.querySelector(".menu__declencheur").addEventListener("click", () => {
    deroulant.classList.toggle("ouvert");
  });
  document.addEventListener("click", (e) => {
    if (!deroulant.contains(e.target)) deroulant.classList.remove("ouvert");
  });
}

// Carrousel du bandeau d'accueil : défilement automatique, flèches, points et glissement au doigt
const carrousel = document.querySelector(".carrousel");
if (carrousel) {
  const piste = carrousel.querySelector(".carrousel__piste");
  const diapos = [...carrousel.querySelectorAll(".carrousel__diapo")];
  const points = [...carrousel.querySelectorAll(".carrousel__point")];
  const DELAI = 2000; // millisecondes entre deux diapositives
  const mouvementReduit = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let actuel = 0;
  let minuteur = null;

  const afficher = (n) => {
    actuel = (n + diapos.length) % diapos.length;
    piste.style.transform = `translateX(-${actuel * 100}%)`;
    diapos.forEach((d, i) => { d.inert = i !== actuel; });
    points.forEach((p, i) => p.setAttribute("aria-current", i === actuel));
  };
  const demarrer = () => {
    if (mouvementReduit || diapos.length < 2) return;
    arreter();
    minuteur = setInterval(() => afficher(actuel + 1), DELAI);
  };
  const arreter = () => clearInterval(minuteur);

  carrousel.querySelector("[data-precedent]")?.addEventListener("click", () => { afficher(actuel - 1); demarrer(); });
  carrousel.querySelector("[data-suivant]")?.addEventListener("click", () => { afficher(actuel + 1); demarrer(); });
  points.forEach((p) => p.addEventListener("click", () => { afficher(Number(p.dataset.point)); demarrer(); }));

  // Pause quand la souris ou le clavier est dans le carrousel
  carrousel.addEventListener("mouseenter", arreter);
  carrousel.addEventListener("mouseleave", demarrer);
  carrousel.addEventListener("focusin", arreter);
  carrousel.addEventListener("focusout", demarrer);

  // Glissement au doigt sur mobile
  let departX = null;
  carrousel.addEventListener("touchstart", (e) => { departX = e.touches[0].clientX; arreter(); }, { passive: true });
  carrousel.addEventListener("touchend", (e) => {
    if (departX === null) return;
    const ecart = e.changedTouches[0].clientX - departX;
    if (Math.abs(ecart) > 50) afficher(actuel + (ecart < 0 ? 1 : -1));
    departX = null;
    demarrer();
  });

  afficher(0);
  demarrer();
}
