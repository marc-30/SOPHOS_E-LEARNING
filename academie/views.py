from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import InscriptionForm
from .models import Achat, Categorie, Cours, Inscription, Lecon, LeconTerminee, Projet, SuiviCours


def accueil(request):
    cours = Cours.objects.publies()
    return render(request, "academie/accueil.html", {
        "vedettes": cours.filter(en_vedette=True).select_related("categorie")[:8],
        "cours_list": cours.filter(sur_accueil=True),
    })


def catalogue(request):
    q = request.GET.get("q", "").strip()
    cours = Cours.objects.publies()
    if q:
        cours = cours.filter(
            Q(titre__icontains=q) | Q(auteur__icontains=q) | Q(description__icontains=q) | Q(categorie__nom__icontains=q)
        )
    categories = [
        c for c in Categorie.objects.prefetch_related(Prefetch("cours", queryset=cours, to_attr="liste"))
        if c.liste
    ]
    return render(request, "academie/catalogue.html", {"categories": categories, "q": q})


def _modules(cours):
    return cours.modules.prefetch_related("lecons")


def cours_detail(request, slug):
    cours = get_object_or_404(Cours.objects.publies().select_related("categorie"), slug=slug)
    lecons = list(cours.lecons.all())
    return render(request, "academie/cours_detail.html", {
        "cours": cours,
        "modules": _modules(cours),
        "lecons": lecons,
        "nb_lecons": len(lecons),
        "premiere": lecons[0] if lecons else None,
        "achete": cours.a_acces(request.user),
    })


def lecon(request, slug, pk):
    cours = get_object_or_404(Cours.objects.publies(), slug=slug)
    lecon = get_object_or_404(cours.lecons, pk=pk)
    acces = cours.a_acces(request.user)
    if not lecon.apercu and not acces:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        messages.info(request, "Achetez ce cours pour accéder à cette leçon.")
        return redirect(cours)
    lecons = list(cours.lecons.all())
    i = lecons.index(lecon)
    terminees = set()
    if request.user.is_authenticated and not request.user.is_staff:
        SuiviCours.objects.get_or_create(eleve=request.user, cours=cours, jour=timezone.localdate())
        terminees = set(LeconTerminee.objects.filter(eleve=request.user, lecon__cours=cours).values_list("lecon_id", flat=True))
    return render(request, "academie/lecon.html", {
        "cours": cours,
        "lecon": lecon,
        "modules": _modules(cours),
        "lecons": lecons,
        "achete": acces,
        "terminees": terminees,
        "terminee": lecon.pk in terminees,
        "precedente": lecons[i - 1] if i > 0 else None,
        "suivante": lecons[i + 1] if i + 1 < len(lecons) else None,
        "peut_terminer": acces and request.user.is_authenticated and not request.user.is_staff,
    })


@login_required
@require_POST
def lecon_terminer(request, slug, pk):
    cours = get_object_or_404(Cours.objects.publies(), slug=slug)
    lecon = get_object_or_404(cours.lecons, pk=pk)
    if not cours.a_acces(request.user) or request.user.is_staff:
        raise Http404
    LeconTerminee.objects.get_or_create(eleve=request.user, lecon=lecon)
    lecons = list(cours.lecons.all())
    i = lecons.index(lecon)
    if i + 1 < len(lecons):
        return redirect(lecons[i + 1])
    messages.success(request, "Bravo, vous avez terminé ce cours !")
    return redirect("mes_cours")


def projets(request):
    return render(request, "academie/projets.html", {"projets": Projet.objects.filter(publie=True)})


def plus(request):
    return render(request, "academie/plus.html", {"images": Cours.objects.publies().filter(sur_accueil=True)[:4]})


@login_required
def mes_cours(request):
    inscriptions = list(request.user.inscriptions.select_related("cours"))
    ids = [i.cours_id for i in inscriptions]
    lecons_par_cours = {}
    for l in Lecon.objects.filter(cours_id__in=ids):
        lecons_par_cours.setdefault(l.cours_id, []).append(l)
    faites = set(LeconTerminee.objects.filter(eleve=request.user, lecon__cours_id__in=ids).values_list("lecon_id", flat=True))
    for ins in inscriptions:
        lecons = lecons_par_cours.get(ins.cours_id, [])
        ins.total = len(lecons)
        ins.faites = sum(1 for l in lecons if l.pk in faites)
        ins.pourcentage = round(ins.faites * 100 / ins.total) if ins.total else 0
        # « Reprendre » : première leçon pas encore terminée (sinon la première du cours)
        ins.reprise = next((l for l in lecons if l.pk not in faites), lecons[0] if lecons else None)
    return render(request, "academie/mes_cours.html", {"inscriptions": inscriptions})


def _inscrire_gratuitement(request, cours):
    _, cree = Inscription.objects.get_or_create(eleve=request.user, cours=cours, defaults={"gratuite": True})
    if cree:
        messages.success(request, f"Vous êtes inscrit à « {cours.titre} ». Bon apprentissage !")
    premiere = cours.lecons.first()
    return redirect(premiere or cours)


@login_required
@require_POST
def s_inscrire(request, slug):
    cours = get_object_or_404(Cours.objects.publies(), slug=slug)
    if not cours.est_gratuit:
        return redirect(cours)  # un cours payant ne s'ouvre jamais sans paiement confirmé
    return _inscrire_gratuitement(request, cours)


@login_required
@require_POST
def acheter(request, slug):
    cours = get_object_or_404(Cours.objects.publies(), slug=slug)
    if cours.a_acces(request.user):
        messages.info(request, "Vous avez déjà accès à ce cours.")
        return redirect(cours)
    if cours.est_gratuit:
        return _inscrire_gratuitement(request, cours)
    achat = Achat.objects.create(eleve=request.user, cours=cours, montant=cours.prix)
    return redirect("paiement", reference=achat.reference)


@login_required
def paiement(request, reference):
    achat = get_object_or_404(Achat, reference=reference, eleve=request.user)
    if achat.statut == Achat.PAYE:
        return redirect(achat.cours)
    if request.method == "POST":
        # Mode test uniquement : valide l'achat sans paiement réel.
        # Avec un vrai prestataire, l'achat est validé par sa notification (webhook), jamais ici.
        if settings.PAIEMENT_MODE != "test":
            raise Http404
        achat.marquer_paye()
        messages.success(request, f"Paiement confirmé. Bienvenue dans « {achat.cours} » !")
        return redirect(achat.cours)
    return render(request, "academie/paiement.html", {"achat": achat, "mode_test": settings.PAIEMENT_MODE == "test"})


def inscription(request):
    if request.user.is_authenticated:
        return redirect("mes_cours")
    form = InscriptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Votre compte est créé. Bienvenue !")
        suivant = request.GET.get("next", "")
        if url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}):
            return redirect(suivant)
        return redirect("mes_cours")
    return render(request, "registration/inscription.html", {"form": form})
