"""Importe le contenu de démonstration du site Framer (catégories, cours, leçons, projets).

Utilisation :  python manage.py importer_demo
Sans risque à relancer : ce qui existe déjà n'est pas dupliqué.
"""
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from academie.models import Categorie, Cours, Lecon, Module, Projet

IMAGES = Path(settings.BASE_DIR) / "static" / "images"

CATEGORIES = [
    ("illustration", "Illustration et dessin"),
    ("photographie", "Photographie et vidéo"),
    ("design", "Design graphique"),
    ("animation", "3D et animation"),
    ("marketing", "Marketing et management"),
    ("musique", "Musique et audio"),
    ("mode", "Mode et couture"),
    ("artisanat", "Artisanat et gravure"),
    ("ia-video", "IA générative et vidéo"),
    ("anglais", "Anglais"),
    ("community", "Community management"),
]

DEMO = "Cours de démonstration · Débutant"
EN_LIGNE = "Cours en ligne · À votre rythme"
NV, MV = "NOUVEAU", "MEILLEURE VENTE"

# (catégorie, image, badge, durée, titre, auteur, sous-titre, sur l'accueil)
COURS = [
    ("photographie", "photographie.jpg", MV, "2 h 31 min", "Photographie professionnelle pour les réseaux sociaux", "Studio Sophos Académie", DEMO, True),
    ("design", "photoshop.jpg", MV, "6 h 54 min", "Introduction à Adobe Photoshop", "Studio Sophos Académie", DEMO, True),
    ("musique", "musique.jpg", MV, "3 h 33 min", "Créez des musiques accrocheuses pour vos vidéos", "Studio Sophos Académie", DEMO, True),
    # --- IA générative et vidéo
    ("ia-video", "motion-design.jpg", NV, "5 h 20 min", "IA générative vidéo : créez vos premières vidéos de A à Z", "Studio Sophos Académie", EN_LIGNE, True),
    ("ia-video", "motion-design.jpg", NV, "4 h 10 min", "Écrire des prompts efficaces pour générer des vidéos par IA", "Studio Sophos Académie", EN_LIGNE, True),
    ("ia-video", "motion-design.jpg", NV, "6 h 45 min", "Montage et post-production de vidéos générées par IA", "Studio Sophos Académie", EN_LIGNE, True),
    ("ia-video", "motion-design.jpg", NV, "3 h 30 min", "Créer des publicités et des clips avec l’IA générative", "Studio Sophos Académie", EN_LIGNE, True),
    # --- Marketing management
    ("marketing", "photoshop.jpg", MV, "7 h 15 min", "Marketing management : construire une stratégie gagnante", "Studio Sophos Académie", EN_LIGNE, True),
    ("marketing", "photoshop.jpg", MV, "5 h 40 min", "Piloter une équipe marketing et ses indicateurs de performance", "Studio Sophos Académie", EN_LIGNE, True),
    ("marketing", "photoshop.jpg", MV, "4 h 01 min", "Créer des publicités Google et Facebook de A à Z", "Studio Sophos Académie", DEMO, True),
    # --- Anglais
    ("anglais", "livre.jpg", MV, "8 h 30 min", "Anglais pour débutants : parlez avec confiance", "Atelier Sophos Académie", EN_LIGNE, True),
    ("anglais", "livre.jpg", MV, "6 h 20 min", "Anglais professionnel : e-mails, réunions et présentations", "Atelier Sophos Académie", EN_LIGNE, True),
    ("anglais", "livre.jpg", NV, "5 h 00 min", "Anglais de la vie quotidienne : voyager et échanger", "Atelier Sophos Académie", EN_LIGNE, True),
    # --- Community management
    ("community", "photographie.jpg", MV, "6 h 30 min", "Community manager : le métier de A à Z", "Studio Sophos Académie", EN_LIGNE, True),
    ("community", "photographie.jpg", MV, "4 h 09 min", "Création de contenu pour les stories Instagram", "Studio Sophos Académie", DEMO, True),
    ("community", "photographie.jpg", NV, "5 h 15 min", "Animer et faire grandir une communauté sur les réseaux sociaux", "Studio Sophos Académie", EN_LIGNE, True),
]

PROJETS = [
    ("illustration-personnages.jpg", "Illustration", "Carnet de personnages imaginaires"),
    ("mode-asie.jpg", "Mode", "Collection textile : contrastes"),
    ("croquis.jpg", "Dessin", "Journal botanique"),
    ("gravure.jpg", "Artisanat", "Premières impressions gravées"),
    ("photographie.jpg", "Photographie", "Lumières et objets du quotidien"),
    ("aquarelle.jpg", "Illustration", "Couleurs à l’aquarelle"),
]

# Cours affichés dans le carrousel de l'accueil, en plus de « Spécialisation en couture et design »
VEDETTES = {
    "IA générative vidéo : créez vos premières vidéos de A à Z",
    "Anglais pour débutants : parlez avec confiance",
    "Photographie professionnelle pour les réseaux sociaux",
    "Introduction à Adobe Photoshop",
    "Créez des musiques accrocheuses pour vos vidéos",
}

LECONS = ["Bienvenue dans le cours", "Le matériel et les outils", "Premier exercice guidé", "Projet final"]


def image(champ, nom):
    with open(IMAGES / nom, "rb") as f:
        champ.save(nom, File(f), save=False)


class Command(BaseCommand):
    help = "Importe les cours, catégories et projets de démonstration."

    def handle(self, *args, **options):
        cats = {}
        for i, (slug, nom) in enumerate(CATEGORIES):
            cats[slug], _ = Categorie.objects.get_or_create(slug=slug, defaults={"nom": nom, "ordre": i})

        vedette = [("mode", "hero-couture.jpg", "", "12 h 00 min", "Spécialisation en couture et design", "Atelier Sophos Académie",
                    "19 628 élèves · 4,9 / 5 (80 avis)", False)]
        nouveaux = 0
        for i, (cat, img, badge, duree, titre, auteur, sous_titre, accueil) in enumerate(vedette + COURS):
            slug = slugify(titre)
            if Cours.objects.filter(slug=slug).exists():
                continue
            cours = Cours(
                categorie=cats[cat], titre=titre, slug=slug, badge=badge, duree=duree, auteur=auteur,
                sous_titre=sous_titre, prix=Decimal("0.50"), prix_barre=Decimal("94.99"),
                reduction="Remise de 99 %", avec_modules=True, sur_accueil=accueil, en_vedette=(i == 0 or titre in VEDETTES), ordre=i,
                description=(
                    "Maîtrisez les techniques de couture : de l’utilisation d’une machine à coudre "
                    "à la création de vos propres vêtements." if i == 0 else
                    f"Un cours pratique pour progresser pas à pas en {cats[cat].nom.lower()}, à votre rythme."
                ),
            )
            image(cours.image, img)
            cours.save()
            modules = [Module.objects.create(cours=cours, titre=t, ordre=k) for k, t in enumerate(["Introduction", "Pratique"])]
            for n, titre_lecon in enumerate(LECONS):
                Lecon.objects.create(
                    cours=cours, module=modules[n // 2], titre=titre_lecon, ordre=n, apercu=(n == 0),
                    contenu="Contenu de démonstration : remplacez ce texte et ajoutez le lien de la vidéo dans l’admin.",
                )
            nouveaux += 1

        projets = 0
        for i, (img, cat, titre) in enumerate(PROJETS):
            if Projet.objects.filter(titre=titre).exists():
                continue
            projet = Projet(titre=titre, categorie=cat, ordre=i)
            image(projet.image, img)
            projet.save()
            projets += 1

        self.stdout.write(self.style.SUCCESS(f"{nouveaux} cours et {projets} projets importés."))
