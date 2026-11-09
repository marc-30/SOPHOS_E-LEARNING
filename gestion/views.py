import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from academie.models import Achat, Categorie, Cours, Professeur, ProfilEleve

from . import securite, stats, twofa
from .decorators import staff_requis
from .forms import CategorieForm, CodeForm, ConnexionForm, CoursForm, ModuleFormSet, ModuleFormSetNouveau, EtudiantForm, ProfesseurForm, aplatir_cours, MODULE_PAR_DEFAUT

logger = logging.getLogger("gestion.securite")
PAR_PAGE = 15


def _page(request, queryset):
    return Paginator(queryset, PAR_PAGE).get_page(request.GET.get("page"))


def _recherche(request):
    return request.GET.get("q", "").strip()[:100]


# ---------- Connexion (mot de passe, puis code du téléphone) ----------

CLE_ATTENTE = "gestion_attente"      # étape 1 réussie, code pas encore saisi
CLE_2FA_OK = "gestion_2fa"           # id du compte dont le code a été vérifié
DUREE_ATTENTE = 5 * 60


def _mettre_en_attente(request, user, suivant):
    request.session.flush()  # nouvelle session : rien de l'ancienne ne survit
    request.session[CLE_ATTENTE] = {"uid": user.pk, "backend": user.backend, "t": int(time.time()), "next": suivant}


def _en_attente(request):
    """Compte ayant passé l'étape du mot de passe depuis moins de 5 minutes, sinon None."""
    data = request.session.get(CLE_ATTENTE)
    if not data or time.time() - data.get("t", 0) > DUREE_ATTENTE:
        request.session.pop(CLE_ATTENTE, None)
        return None
    user = get_user_model().objects.filter(pk=data["uid"], is_active=True, is_staff=True).first()
    return user


def _terminer_connexion(request, user):
    data = request.session.pop(CLE_ATTENTE)
    login(request, user, backend=data["backend"])
    request.session[CLE_2FA_OK] = user.pk
    request.session.set_expiry(60 * 60 * 8)
    suivant = data.get("next", "")
    if url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(suivant)
    return redirect("gestion:tableau_de_bord")


@never_cache
def connexion(request):
    if request.user.is_authenticated and request.user.is_staff and request.session.get(CLE_2FA_OK) == request.user.pk:
        return redirect("gestion:tableau_de_bord")
    form = ConnexionForm(request.POST or None, request=request)
    if request.method == "POST":
        identifiant = request.POST.get("username", "")
        if securite.est_bloque(request, identifiant):
            logger.warning("Connexion admin bloquée (ip=%s)", securite.ip_client(request))
            form.add_error(None, "Trop de tentatives. Réessayez dans 15 minutes.")
        elif form.is_valid():
            securite.effacer_echecs(request, identifiant)
            _mettre_en_attente(request, form.user, request.POST.get("next", ""))
            if not settings.ADMIN_2FA_REQUISE:  # phase de démonstration : le mot de passe suffit
                return _terminer_connexion(request, form.user)
            appareil = twofa.appareil_de(form.user)
            return redirect("gestion:verification" if appareil and appareil.confirme else "gestion:activation")
        else:
            securite.enregistrer_echec(request, identifiant)
    return render(request, "gestion/connexion.html", {"form": form, "next": request.GET.get("next", "")})


def _verifier_saisie(request, user, appareil):
    """Contrôle le code saisi (application ou code de secours) avec limitation des essais."""
    cle = f"2fa-{user.pk}"
    if securite.est_bloque(request, cle):
        return "Trop de tentatives. Réessayez dans 15 minutes."
    form = CodeForm(request.POST)
    code = form.cleaned_data["code"] if form.is_valid() else ""
    if twofa.verifier_code(appareil, code) or twofa.utiliser_code_secours(appareil, code):
        securite.effacer_echecs(request, cle)
        return None
    securite.enregistrer_echec(request, cle)
    return "Code incorrect ou expiré."


@never_cache
def verification(request):
    user = _en_attente(request) if settings.ADMIN_2FA_REQUISE else None
    appareil = twofa.appareil_de(user) if user else None
    if not (appareil and appareil.confirme):
        return redirect("gestion:connexion")
    erreur = None
    if request.method == "POST":
        erreur = _verifier_saisie(request, user, appareil)
        if erreur is None:
            return _terminer_connexion(request, user)
    return render(request, "gestion/verification.html", {"erreur": erreur})


@never_cache
def activation(request):
    """Première connexion : l'utilisateur relie son téléphone, puis reçoit ses codes de secours."""
    user = _en_attente(request) if settings.ADMIN_2FA_REQUISE else None
    if not user:
        return redirect("gestion:connexion")
    appareil = twofa.preparer_appareil(user)
    if appareil.confirme:
        return redirect("gestion:verification")
    erreur = None
    if request.method == "POST":
        cle = f"2fa-{user.pk}"
        form = CodeForm(request.POST)
        if securite.est_bloque(request, cle):
            erreur = "Trop de tentatives. Réessayez dans 15 minutes."
        elif form.is_valid() and twofa.verifier_code(appareil, form.cleaned_data["code"]):
            securite.effacer_echecs(request, cle)
            appareil.confirme = True
            appareil.save(update_fields=["confirme"])
            codes = twofa.generer_codes_secours(appareil)
            _terminer_connexion(request, user)
            request.session["gestion_codes_secours"] = codes
            return redirect("gestion:codes_secours")
        else:
            securite.enregistrer_echec(request, cle)
            erreur = "Code incorrect. Vérifiez l'heure de votre téléphone et réessayez."
    return render(request, "gestion/activation.html", {"secret": twofa.secret_affichable(appareil), "erreur": erreur})


@never_cache
def activation_qr(request):
    user = _en_attente(request)
    appareil = twofa.appareil_de(user) if user else None
    if not appareil or appareil.confirme:
        raise Http404
    return HttpResponse(twofa.qr_svg(appareil), content_type="image/svg+xml")


@staff_requis
def codes_secours(request):
    codes = request.session.pop("gestion_codes_secours", None)
    if not codes:
        return redirect("gestion:tableau_de_bord")
    return render(request, "gestion/codes_secours.html", {"codes": codes, "section": "compte"})


@staff_requis
@require_POST
def regenerer_codes(request):
    appareil = twofa.appareil_de(request.user)
    form = CodeForm(request.POST)
    if appareil and form.is_valid() and twofa.verifier_code(appareil, form.cleaned_data["code"]):
        request.session["gestion_codes_secours"] = twofa.generer_codes_secours(appareil)
        return redirect("gestion:codes_secours")
    messages.error(request, "Code incorrect : les codes de secours n'ont pas été modifiés.")
    return redirect("gestion:mot_de_passe")


@require_POST
def deconnexion(request):
    logout(request)
    return redirect("gestion:connexion")


@staff_requis
def mot_de_passe(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "Mot de passe modifié.")
        return redirect("gestion:tableau_de_bord")
    appareil = twofa.appareil_de(request.user)
    return render(request, "gestion/mot_de_passe.html", {
        "form": form, "section": "compte", "nb_codes": len(appareil.codes_secours) if appareil else 0,
    })


# ---------- Tableau de bord ----------

@staff_requis
def tableau_de_bord(request):
    return render(request, "gestion/tableau_de_bord.html", {
        "section": "tableau", "metriques": stats.METRIQUES, "devise": settings.DEVISE,
    })


@staff_requis
@require_GET
def api_stats(request):
    metrique = request.GET.get("metrique", "actifs")
    if metrique not in stats.METRIQUES:
        metrique = "actifs"
    periode, debut, fin = stats.lire_periode(request.GET)
    granularite, labels, courbes = stats.serie(metrique, debut, fin)
    cartes, totaux = stats.kpis(debut, fin)
    return JsonResponse({
        "periode": periode, "debut": debut.isoformat(), "fin": fin.isoformat(),
        "metrique": metrique, "titre": stats.METRIQUES[metrique],
        "granularite": granularite, "labels": labels, "courbes": courbes,
        "unite": settings.DEVISE if metrique == "revenus" else "",
        "kpis": cartes, "totaux": totaux,
        "classement": stats.classement_cours(debut, fin),
    })


# ---------- Cours ----------

@staff_requis
def cours_liste(request):
    q = _recherche(request)
    cours = Cours.objects.select_related("categorie", "professeur").annotate(
        nb_eleves=Count("inscriptions", distinct=True),
        nb_modules=Count("modules", distinct=True),
        nb_lecons=Count("lecons", distinct=True),
    )
    if q:
        cours = cours.filter(Q(titre__icontains=q) | Q(auteur__icontains=q) | Q(categorie__nom__icontains=q))
    return render(request, "gestion/cours_liste.html", {"page": _page(request, cours), "q": q, "section": "cours"})


@staff_requis
def cours_form(request, pk=None):
    cours = get_object_or_404(Cours, pk=pk) if pk else None
    form = CoursForm(request.POST or None, request.FILES or None, instance=cours)
    if cours and cours.modules.exists():
        formset = ModuleFormSet(request.POST or None, instance=cours)
    else:
        formset = ModuleFormSetNouveau(
            request.POST or None, instance=cours, initial=[{"titre": MODULE_PAR_DEFAUT, "ordre": 0}]
        )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            cours = form.save()
            formset.instance = cours
            formset.save()
            if not cours.avec_modules:
                aplatir_cours(cours)
        messages.success(request, "Cours enregistré.")
        return redirect("gestion:cours_liste")
    return render(request, "gestion/cours_form.html", {"form": form, "formset": formset, "cours": cours, "section": "cours"})


@staff_requis
@require_POST
def cours_publier(request, pk):
    cours = get_object_or_404(Cours, pk=pk)
    cours.publie = not cours.publie
    cours.save(update_fields=["publie"])
    messages.success(request, f"« {cours.titre} » est {'publié' if cours.publie else 'masqué'}.")
    return redirect("gestion:cours_liste")


@staff_requis
def cours_supprimer(request, pk):
    cours = get_object_or_404(Cours, pk=pk)
    if request.method == "POST":
        try:
            cours.delete()
            messages.success(request, "Cours supprimé.")
        except ProtectedError:
            messages.error(request, "Ce cours a déjà été acheté : masquez-le plutôt que de le supprimer.")
        return redirect("gestion:cours_liste")
    return render(request, "gestion/confirmer.html", {"objet": cours, "titre": "Supprimer ce cours", "retour": "gestion:cours_liste", "section": "cours"})


# ---------- Étudiants ----------

@staff_requis
def etudiants_liste(request):
    q = _recherche(request)
    etudiants = get_user_model().objects.filter(is_staff=False).select_related("profil").annotate(
        nb_cours=Count("inscriptions", distinct=True)
    ).order_by("-date_joined")
    if q:
        etudiants = etudiants.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    return render(request, "gestion/etudiants_liste.html", {"page": _page(request, etudiants), "q": q, "section": "etudiants"})


@staff_requis
def etudiant_detail(request, pk):
    etudiant = get_object_or_404(get_user_model().objects.filter(is_staff=False), pk=pk)
    achats = etudiant.achats.select_related("cours")
    profil = ProfilEleve.objects.filter(eleve=etudiant).first()
    return render(request, "gestion/etudiant_detail.html", {
        "etudiant": etudiant, "profil": profil, "achats": achats, "section": "etudiants",
        "inscriptions": etudiant.inscriptions.select_related("cours"),
        "depense": achats.filter(statut=Achat.PAYE).aggregate(t=Sum("montant"))["t"] or 0,
        "jours_actifs": etudiant.activites.count(),
    })


@staff_requis
def etudiant_modifier(request, pk):
    etudiant = get_object_or_404(get_user_model().objects.filter(is_staff=False), pk=pk)
    form = EtudiantForm(request.POST or None, request.FILES or None, instance=etudiant)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "Étudiant enregistré.")
        return redirect("gestion:etudiant_detail", pk=pk)
    return render(request, "gestion/etudiant_form.html", {"form": form, "etudiant": etudiant, "section": "etudiants"})


@staff_requis
@require_POST
def etudiant_statut(request, pk):
    etudiant = get_object_or_404(get_user_model().objects.filter(is_staff=False), pk=pk)
    etudiant.is_active = not etudiant.is_active
    etudiant.save(update_fields=["is_active"])
    messages.success(request, f"Compte {'réactivé' if etudiant.is_active else 'désactivé'}.")
    return redirect("gestion:etudiant_detail", pk=pk)


# ---------- Professeurs ----------

@staff_requis
def professeurs_liste(request):
    q = _recherche(request)
    profs = Professeur.objects.annotate(nb_cours=Count("cours"))
    if q:
        profs = profs.filter(Q(nom__icontains=q) | Q(email__icontains=q))
    return render(request, "gestion/professeurs_liste.html", {"page": _page(request, profs), "q": q, "section": "professeurs"})


@staff_requis
def professeur_form(request, pk=None):
    prof = get_object_or_404(Professeur, pk=pk) if pk else None
    form = ProfesseurForm(request.POST or None, request.FILES or None, instance=prof)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            prof = form.save()
            prof.cours.update(auteur=prof.nom)
        messages.success(request, "Professeur enregistré.")
        return redirect("gestion:professeurs_liste")
    return render(request, "gestion/professeur_form.html", {"form": form, "prof": prof, "section": "professeurs"})


@staff_requis
def professeur_supprimer(request, pk):
    prof = get_object_or_404(Professeur, pk=pk)
    if request.method == "POST":
        prof.delete()
        messages.success(request, "Professeur supprimé. Ses cours restent en ligne.")
        return redirect("gestion:professeurs_liste")
    return render(request, "gestion/confirmer.html", {"objet": prof, "titre": "Supprimer ce professeur", "retour": "gestion:professeurs_liste", "section": "professeurs"})


# ---------- Catégories ----------

@staff_requis
def categories_liste(request):
    categories = Categorie.objects.annotate(nb_cours=Count("cours"))
    return render(request, "gestion/categories_liste.html", {"categories": categories, "section": "categories"})


@staff_requis
def categorie_form(request, pk=None):
    categorie = get_object_or_404(Categorie, pk=pk) if pk else None
    form = CategorieForm(request.POST or None, instance=categorie)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie enregistrée.")
        return redirect("gestion:categories_liste")
    return render(request, "gestion/categorie_form.html", {"form": form, "categorie": categorie, "section": "categories"})


@staff_requis
def categorie_supprimer(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk)
    if request.method == "POST":
        try:
            categorie.delete()
        except ProtectedError:
            messages.error(request, "Cette catégorie contient des cours : déplacez-les ou supprimez-les d’abord.")
        else:
            messages.success(request, "Catégorie supprimée.")
        return redirect("gestion:categories_liste")
    return render(request, "gestion/confirmer.html", {"objet": categorie, "titre": "Supprimer cette catégorie", "retour": "gestion:categories_liste", "section": "categories"})


# ---------- Ventes (lecture seule) ----------

@staff_requis
def ventes_liste(request):
    statut = request.GET.get("statut", "")
    achats = Achat.objects.select_related("eleve", "cours")
    if statut in dict(Achat.STATUTS):
        achats = achats.filter(statut=statut)
    else:
        statut = ""
    return render(request, "gestion/ventes_liste.html", {
        "page": _page(request, achats), "statut": statut, "statuts": Achat.STATUTS, "section": "ventes", "devise": settings.DEVISE,
    })
