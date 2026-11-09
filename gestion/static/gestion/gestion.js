/* Administration Sophos — JavaScript sans dépendance. Toute donnée affichée passe par textContent (jamais innerHTML). */
(function () {
  'use strict';

  // ---------- Menu mobile ----------
  var burger = document.getElementById('burger'), menu = document.getElementById('menu');
  if (burger && menu) {
    burger.addEventListener('click', function () { menu.classList.toggle('ouvert'); });
    document.addEventListener('click', function (e) {
      if (menu.classList.contains('ouvert') && !menu.contains(e.target) && e.target !== burger) menu.classList.remove('ouvert');
    });
  }

  // ---------- Cours gratuit : grise les champs de prix ----------
  var caseGratuit = document.getElementById('id_gratuit');
  if (caseGratuit) {
    var champsPrix = ['id_prix', 'id_prix_barre', 'id_reduction'].map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var appliquerGratuit = function () {
      champsPrix.forEach(function (c) {
        c.disabled = caseGratuit.checked;
        c.closest('.champ').classList.toggle('champ--grise', caseGratuit.checked);
      });
    };
    caseGratuit.addEventListener('change', appliquerGratuit);
    appliquerGratuit();
  }

  // ---------- Modules et leçons d'un cours : ajouter des lignes ----------
  var zoneModules = document.getElementById('modules');
  if (zoneModules) {
    var radiosStructure = document.querySelectorAll('input[name="avec_modules"]');
    var appliquerStructure = function () {
      var avec = document.querySelector('input[name="avec_modules"]:checked');
      zoneModules.classList.toggle('modules--plat', !avec || avec.value !== 'True');
    };
    radiosStructure.forEach(function (r) { r.addEventListener('change', appliquerStructure); });
    appliquerStructure();
    var listeModules = document.getElementById('modules-liste');
    var modeleModule = document.getElementById('module-modele');
    var totalModules = document.getElementById('id_' + zoneModules.dataset.prefixe + '-TOTAL_FORMS');
    var inserer = function (parent, html, ordre) {
      var tmp = document.createElement('template');
      tmp.innerHTML = html;
      var ajoute = tmp.content.firstElementChild;
      parent.appendChild(tmp.content);
      var champOrdre = ajoute.querySelector('input[name$="-ordre"]');
      if (champOrdre) champOrdre.value = ordre;
      return ajoute;
    };
    document.getElementById('module-ajouter').addEventListener('click', function () {
      var n = parseInt(totalModules.value, 10);
      // Le préfixe des leçons (lecons-__m__) devient lecons-N ; le __prefix__ des leçons est laissé tel quel
      var html = modeleModule.innerHTML.split('modules-__prefix__').join('modules-' + n).split('__m__').join(String(n));
      var bloc = inserer(listeModules, html, n);
      totalModules.value = n + 1;
      var champ = bloc.querySelector('input[type=text]');
      if (champ) champ.focus();
    });
    listeModules.addEventListener('click', function (e) {
      var bouton = e.target.closest('.lecon-ajouter');
      if (!bouton) return;
      var bloc = bouton.closest('.module-bloc');
      var total = bloc.querySelector('input[name$="-TOTAL_FORMS"][name^="lecons-"]');
      var n = parseInt(total.value, 10);
      var html = bloc.querySelector('.lecon-modele').innerHTML.split('__prefix__').join(String(n));
      var ajoutee = inserer(bloc.querySelector('.lecons-liste'), html, n);
      total.value = n + 1;
      var champ = ajoutee.querySelector('input[type=text]');
      if (champ) champ.focus();
    });
  }

  // ---------- Tableau de bord ----------
  var tdb = document.getElementById('tdb');
  if (!tdb) return;

  var NS = 'http://www.w3.org/2000/svg';
  var devise = tdb.dataset.devise;
  var champMetrique = document.getElementById('f-metrique');
  var boutons = Array.prototype.slice.call(document.querySelectorAll('.segment'));
  var blocDates = document.getElementById('f-dates');
  var champDebut = document.getElementById('f-debut'), champFin = document.getElementById('f-fin');
  var graphe = document.getElementById('graphe'), legende = document.getElementById('legende');
  var etat = { metrique: 'actifs', periode: '30j', debut: '', fin: '' };
  var requete = null, minuteur = null;

  var METRIQUES = ['actifs', 'inscriptions', 'ventes', 'revenus', 'cours'];
  var PERIODES = ['7j', '30j', '90j', '12m', 'perso'];
  var params = new URLSearchParams(window.location.search);
  if (METRIQUES.indexOf(params.get('metrique')) >= 0) etat.metrique = params.get('metrique');
  if (PERIODES.indexOf(params.get('periode')) >= 0) etat.periode = params.get('periode');
  if (/^\d{4}-\d{2}-\d{2}$/.test(params.get('debut') || '')) etat.debut = params.get('debut');
  if (/^\d{4}-\d{2}-\d{2}$/.test(params.get('fin') || '')) etat.fin = params.get('fin');

  function el(nom, attrs, parent) {
    var n = document.createElementNS(NS, nom);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function html(nom, classe, texte, parent) {
    var n = document.createElement(nom);
    if (classe) n.className = classe;
    if (texte !== undefined) n.textContent = texte;
    if (parent) parent.appendChild(n);
    return n;
  }
  var nombre = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 });
  function fmt(v, unite) { return nombre.format(v) + (unite ? ' ' + unite : ''); }
  function date(iso) { var p = iso.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function libelle(iso, gran, long) {
    var opts = gran === 'mois' ? { month: 'short', year: 'numeric' } : (long ? { weekday: 'short', day: 'numeric', month: 'long' } : { day: 'numeric', month: 'short' });
    return date(iso).toLocaleDateString('fr-FR', opts);
  }

  function synchroniserControles() {
    champMetrique.value = etat.metrique;
    boutons.forEach(function (b) { b.classList.toggle('actif', b.dataset.periode === etat.periode); });
    blocDates.hidden = etat.periode !== 'perso';
    if (etat.debut) champDebut.value = etat.debut;
    if (etat.fin) champFin.value = etat.fin;
  }

  function charger() {
    clearTimeout(minuteur);
    minuteur = setTimeout(function () {
      if (etat.periode === 'perso' && !(etat.debut && etat.fin)) return;
      var q = new URLSearchParams({ metrique: etat.metrique, periode: etat.periode });
      if (etat.periode === 'perso') { q.set('debut', etat.debut); q.set('fin', etat.fin); }
      window.history.replaceState(null, '', '?' + q.toString());
      if (requete) requete.abort();
      requete = new AbortController();
      graphe.classList.add('charge');
      fetch(tdb.dataset.url + '?' + q.toString(), { credentials: 'same-origin', headers: { 'Accept': 'application/json' }, signal: requete.signal })
        .then(function (r) {
          if (r.redirected || r.status === 403) { window.location.reload(); throw new Error('session'); }
          if (!r.ok) throw new Error('http ' + r.status);
          return r.json();
        })
        .then(function (d) { afficher(d); graphe.classList.remove('charge'); })
        .catch(function (e) { if (e.name !== 'AbortError') graphe.classList.remove('charge'); });
    }, 120);
  }

  var derniere = null;
  function afficher(d) {
    derniere = d;
    document.getElementById('graphe-titre').textContent = d.titre;
    document.getElementById('graphe-periode').textContent = 'Du ' + date(d.debut).toLocaleDateString('fr-FR') + ' au ' + date(d.fin).toLocaleDateString('fr-FR');
    kpis(d); courbe(d); classement(d);
  }

  function kpis(d) {
    var conteneur = document.getElementById('kpis');
    conteneur.textContent = '';
    d.kpis.forEach(function (k) {
      var c = html('button', 'kpi' + (k.cle === d.metrique ? ' actif' : ''), undefined, conteneur);
      c.type = 'button';
      html('span', 'kpi__nom', k.nom, c);
      html('strong', 'kpi__valeur', fmt(k.valeur, k.cle === 'revenus' ? devise : ''), c);
      var v = k.variation;
      html('span', 'kpi__var' + (v > 0 ? ' kpi__var--haut' : v < 0 ? ' kpi__var--bas' : ''),
        v === null ? 'Pas de période précédente' : (v > 0 ? '▲ +' : v < 0 ? '▼ ' : '') + nombre.format(v) + ' % vs période précédente', c);
      c.addEventListener('click', function () { etat.metrique = k.cle; synchroniserControles(); charger(); });
    });
  }

  function classement(d) {
    var corps = document.querySelector('#classement tbody');
    corps.textContent = '';
    if (!d.classement.length) {
      var tr = html('tr', '', undefined, corps), td = html('td', 'vide', 'Aucune activité sur cette période.', tr);
      td.colSpan = 3; return;
    }
    d.classement.forEach(function (l, i) {
      var tr = html('tr', '', undefined, corps);
      html('td', 'rang', String(i + 1), tr);
      html('td', '', l.cours__titre, tr);
      html('td', 'num', nombre.format(l.nombre), tr);
    });
  }

  // Courbe lissée sans dépassement (interpolation monotone)
  function cheminLisse(pts) {
    if (pts.length < 3) return 'M' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join('L');
    var n = pts.length, dx = [], m = [], t = [], i;
    for (i = 0; i < n - 1; i++) { dx.push(pts[i + 1][0] - pts[i][0]); m.push((pts[i + 1][1] - pts[i][1]) / dx[i]); }
    t[0] = m[0]; t[n - 1] = m[n - 2];
    for (i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
    for (i = 0; i < n - 1; i++) {
      if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
      var a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
      if (s > 9) { var k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
    }
    var chemin = 'M' + pts[0][0] + ',' + pts[0][1];
    for (i = 0; i < n - 1; i++) {
      var h = dx[i] / 3;
      chemin += 'C' + (pts[i][0] + h) + ',' + (pts[i][1] + t[i] * h) + ' ' + (pts[i + 1][0] - h) + ',' + (pts[i + 1][1] - t[i + 1] * h) + ' ' + pts[i + 1][0] + ',' + pts[i + 1][1];
    }
    return chemin;
  }

  function plafond(max) {
    if (max <= 0) return 4;
    var p = Math.pow(10, Math.floor(Math.log10(max))), f = max / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 4 ? 4 : f <= 5 ? 5 : 10) * p;
  }

  function courbe(d) {
    graphe.textContent = ''; legende.textContent = '';
    var tous = [].concat.apply([], d.courbes.map(function (c) { return c.valeurs; }));
    if (!d.courbes.length || !tous.some(function (v) { return v > 0; })) {
      html('div', 'graphe__vide', 'Aucune donnée sur cette période.', graphe); return;
    }
    var L = graphe.clientWidth, H = graphe.clientHeight;
    var m = { g: 52, d: 16, h: 14, b: 30 }, w = L - m.g - m.d, h = H - m.h - m.b;
    var max = plafond(Math.max.apply(null, tous)), n = d.labels.length;
    var svg = el('svg', { viewBox: '0 0 ' + L + ' ' + H, preserveAspectRatio: 'none' }, graphe);
    var x = function (i) { return m.g + (n === 1 ? w / 2 : i * w / (n - 1)); };
    var y = function (v) { return m.h + h - v / max * h; };

    for (var t = 0; t <= 4; t++) {
      var val = max * t / 4, yy = y(val);
      el('line', { x1: m.g, x2: m.g + w, y1: yy, y2: yy, 'class': 'grille-ligne' }, svg);
      var tx = el('text', { x: m.g - 10, y: yy + 4, 'text-anchor': 'end', 'class': 'axe-texte' }, svg);
      tx.textContent = nombre.format(val);
    }
    var pas = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 80))));
    d.labels.forEach(function (iso, i) {
      if (i % pas) return;
      var tx = el('text', { x: x(i), y: H - 8, 'text-anchor': 'middle', 'class': 'axe-texte' }, svg);
      tx.textContent = libelle(iso, d.granularite);
    });

    var defs = el('defs', {}, svg);
    d.courbes.forEach(function (c, k) {
      var pts = c.valeurs.map(function (v, i) { return [x(i), y(v)]; }), couleur = 'currentColor';
      var g = el('g', { 'class': 'c' + (k % 5) }, svg);
      if (d.courbes.length === 1) {
        var id = 'degrade' + k, lg = el('linearGradient', { id: id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
        el('stop', { offset: '0%', 'stop-color': '#e52b08', 'stop-opacity': 0.22 }, lg);
        el('stop', { offset: '100%', 'stop-color': '#e52b08', 'stop-opacity': 0 }, lg);
        el('path', { d: cheminLisse(pts) + 'L' + x(n - 1) + ',' + (m.h + h) + 'L' + x(0) + ',' + (m.h + h) + 'Z', fill: 'url(#' + id + ')', 'class': 'zone' }, g);
        couleur = '#e52b08';
      }
      el('path', { d: cheminLisse(pts), fill: 'none', stroke: couleur, pathLength: 1, 'class': 'courbe', 'stroke-linecap': 'round' }, g);
      var li = html('li', '', undefined, legende);
      html('i', 'bg' + (d.courbes.length === 1 ? 1 : k % 5), undefined, li);
      html('span', '', c.nom, li);
    });

    // Survol : repère vertical + points + infobulle
    var repere = el('line', { y1: m.h, y2: m.h + h, 'class': 'repere', visibility: 'hidden' }, svg);
    var points = d.courbes.map(function (c, k) {
      return el('circle', { r: 5, 'class': 'point c' + (k % 5), fill: d.courbes.length === 1 ? '#e52b08' : 'currentColor', visibility: 'hidden' }, svg);
    });
    var bulle = html('div', 'infobulle', undefined, graphe); bulle.hidden = true;
    var zoneSouris = el('rect', { x: m.g, y: m.h, width: w, height: h, fill: 'transparent', stroke: 'none' }, svg);
    zoneSouris.addEventListener('pointermove', function (e) {
      var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * L / r.width;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - m.g) / w * (n - 1))));
      repere.setAttribute('x1', x(i)); repere.setAttribute('x2', x(i)); repere.setAttribute('visibility', 'visible');
      bulle.textContent = ''; bulle.hidden = false;
      html('strong', '', libelle(d.labels[i], d.granularite, true), bulle);
      d.courbes.forEach(function (c, k) {
        points[k].setAttribute('cx', x(i)); points[k].setAttribute('cy', y(c.valeurs[i])); points[k].setAttribute('visibility', 'visible');
        var ligne = html('span', '', undefined, bulle);
        html('i', 'bg' + (d.courbes.length === 1 ? 1 : k % 5), undefined, ligne);
        html('span', '', (d.courbes.length > 1 ? c.nom + ' : ' : '') + fmt(c.valeurs[i], d.unite), ligne);
      });
      var gauche = x(i) * r.width / L + 14;
      if (gauche + bulle.offsetWidth > r.width) gauche = x(i) * r.width / L - bulle.offsetWidth - 14;
      bulle.style.left = Math.max(0, gauche) + 'px';
      bulle.style.top = Math.max(0, (e.clientY - r.top) - bulle.offsetHeight - 10) + 'px';
    });
    zoneSouris.addEventListener('pointerleave', function () {
      repere.setAttribute('visibility', 'hidden'); bulle.hidden = true;
      points.forEach(function (p) { p.setAttribute('visibility', 'hidden'); });
    });
  }

  // ---------- Événements des filtres ----------
  champMetrique.addEventListener('change', function () { etat.metrique = champMetrique.value; charger(); });
  boutons.forEach(function (b) {
    b.addEventListener('click', function () {
      etat.periode = b.dataset.periode;
      if (etat.periode === 'perso' && !etat.debut) {
        var f = new Date(), d0 = new Date(f.getTime() - 29 * 864e5), iso = function (x) { return x.toISOString().slice(0, 10); };
        etat.debut = iso(d0); etat.fin = iso(f);
      }
      synchroniserControles(); charger();
    });
  });
  champDebut.addEventListener('change', function () { etat.debut = champDebut.value; charger(); });
  champFin.addEventListener('change', function () { etat.fin = champFin.value; charger(); });
  var redim = null;
  window.addEventListener('resize', function () { clearTimeout(redim); redim = setTimeout(function () { if (derniere) courbe(derniere); }, 150); });

  synchroniserControles();
  charger();
})();
