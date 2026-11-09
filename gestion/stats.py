"""Chiffres du tableau de bord. Uniquement l'ORM Django : toutes les requêtes sont paramétrées."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from academie.models import Achat, Activite, Cours, SuiviCours

PERIODES = {"7j": 7, "30j": 30, "90j": 90, "12m": 365}
METRIQUES = {
    "actifs": "Étudiants actifs",
    "inscriptions": "Nouvelles inscriptions",
    "ventes": "Ventes",
    "revenus": "Revenus",
    "cours": "Cours les plus suivis",
}
MAX_JOURS = 366 * 3


def lire_periode(parametres):
    """Valide les paramètres reçus (liste blanche) et renvoie (clé, début, fin) ; jamais d'erreur."""
    fin = timezone.localdate()
    cle = parametres.get("periode", "30j")
    if cle == "perso":
        try:
            debut = date.fromisoformat(parametres.get("debut", ""))
            fin = min(date.fromisoformat(parametres.get("fin", "")), fin)
            if debut > fin or (fin - debut).days > MAX_JOURS:
                raise ValueError
            return cle, debut, fin
        except ValueError:
            cle = "30j"
    if cle not in PERIODES:
        cle = "30j"
    return cle, fin - timedelta(days=PERIODES[cle] - 1), fin


def _mois_suivant(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _intervalles(debut, fin):
    """Liste des (clé, libellé ISO) du graphique : un point par jour, ou par mois si la période dépasse 92 jours."""
    if (fin - debut).days <= 92:
        n = (fin - debut).days + 1
        return "jour", [debut + timedelta(days=i) for i in range(n)]
    pts, d = [], date(debut.year, debut.month, 1)
    while d <= fin:
        pts.append(d)
        d = _mois_suivant(d)
    return "mois", pts


def _compter(queryset, champ_date, granularite, agregat):
    if granularite == "jour":
        # « jour » est déjà un DateField ; les autres champs sont des DateTimeField à ramener au jour
        point = F(champ_date) if champ_date == "jour" else TruncDate(champ_date)
    else:
        point = TruncMonth(champ_date)
    lignes = queryset.annotate(point=point).values("point").annotate(v=agregat).values_list("point", "v")
    out = {}
    for point, v in lignes:
        out[point.date() if hasattr(point, "date") else point] = v or 0
    return out


def _requete_metrique(metrique, debut, fin):
    """Renvoie (queryset, champ date, agrégat) d'une métrique simple sur [debut, fin]."""
    Utilisateur = get_user_model()
    if metrique == "actifs":
        return Activite.objects.filter(jour__range=(debut, fin)), "jour", Count("eleve", distinct=True)
    if metrique == "inscriptions":
        qs = Utilisateur.objects.filter(is_staff=False, date_joined__date__range=(debut, fin))
        return qs, "date_joined", Count("id")
    payes = Achat.objects.filter(statut=Achat.PAYE, paye_le__date__range=(debut, fin))
    if metrique == "ventes":
        return payes, "paye_le", Count("id")
    return payes, "paye_le", Sum("montant")


def total_metrique(metrique, debut, fin):
    qs, _, agregat = _requete_metrique(metrique, debut, fin)
    if metrique == "actifs":
        return qs.values("eleve").distinct().count()
    valeur = qs.aggregate(v=agregat)["v"] or 0
    return float(valeur)


def classement_cours(debut, fin, limite=10):
    return list(
        SuiviCours.objects.filter(jour__range=(debut, fin))
        .values("cours_id", "cours__titre")
        .annotate(nombre=Count("eleve", distinct=True))
        .order_by("-nombre", "cours__titre")[:limite]
    )


def _variation(actuel, precedent):
    if precedent:
        return round((actuel - precedent) / precedent * 100, 1)
    return None if not actuel else 100.0


def kpis(debut, fin):
    duree = (fin - debut).days + 1
    prec_fin, prec_debut = debut - timedelta(days=1), debut - timedelta(days=duree)
    Utilisateur = get_user_model()
    cartes = []
    for cle, nom in [("actifs", "Étudiants actifs"), ("inscriptions", "Nouvelles inscriptions"),
                     ("ventes", "Ventes"), ("revenus", "Revenus")]:
        actuel = total_metrique(cle, debut, fin)
        cartes.append({"cle": cle, "nom": nom, "valeur": actuel,
                       "variation": _variation(actuel, total_metrique(cle, prec_debut, prec_fin))})
    return cartes, {
        "etudiants": Utilisateur.objects.filter(is_staff=False).count(),
        "cours": Cours.objects.publies().count(),
    }


def serie(metrique, debut, fin):
    """Données du graphique en courbe : un jeu de points par courbe."""
    granularite, points = _intervalles(debut, fin)
    labels = [p.isoformat() for p in points]
    if metrique == "cours":
        top = classement_cours(debut, fin, 5)
        qs = SuiviCours.objects.filter(jour__range=(debut, fin))
        courbes = []
        for ligne in top:
            valeurs = _compter(qs.filter(cours_id=ligne["cours_id"]), "jour", granularite, Count("eleve", distinct=True))
            courbes.append({"nom": ligne["cours__titre"], "valeurs": [valeurs.get(p, 0) for p in points]})
        return granularite, labels, courbes
    qs, champ, agregat = _requete_metrique(metrique, debut, fin)
    valeurs = _compter(qs, champ, granularite, agregat)
    return granularite, labels, [{"nom": METRIQUES[metrique], "valeurs": [float(valeurs.get(p, 0)) for p in points]}]
