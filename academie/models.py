import re
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Categorie(models.Model):
    nom = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, help_text="Identifiant dans l'adresse, ex. « illustration »")
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "catégorie"

    def __str__(self):
        return self.nom


class ProfilEleve(models.Model):
    """Informations complémentaires d'un élève (photo ajoutée depuis l'administration)."""
    eleve = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil")
    photo = models.ImageField(upload_to="etudiants/", blank=True)

    class Meta:
        verbose_name = "profil élève"
        verbose_name_plural = "profils élèves"

    def __str__(self):
        return f"Profil de {self.eleve}"


class Professeur(models.Model):
    nom = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    bio = models.TextField("biographie", blank=True)
    photo = models.ImageField(upload_to="professeurs/", blank=True)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class CoursQuerySet(models.QuerySet):
    def publies(self):
        return self.filter(publie=True)


class Cours(models.Model):
    BADGES = [
        ("", "Aucun"),
        ("NOUVEAU", "Nouveau"),
        ("MEILLEURE VENTE", "Meilleure vente"),
    ]

    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="cours")
    titre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    professeur = models.ForeignKey(
        Professeur, null=True, blank=True, on_delete=models.SET_NULL, related_name="cours"
    )
    image = models.ImageField(upload_to="cours/")
    video_bienvenue = models.FileField(
        "vidéo de bienvenue", upload_to="videos-bienvenue/", blank=True,
        help_text="Aperçu visible par tous sur la page du cours (MP4 ou WebM).",
    )
    badge = models.CharField(max_length=20, choices=BADGES, blank=True)
    niveau = models.CharField(max_length=50, default="Débutant")
    duree = models.CharField("durée", max_length=30, help_text="ex. « 3 h 20 min »")
    auteur = models.CharField(max_length=120)
    sous_titre = models.CharField(
        max_length=200, blank=True, help_text="Petite ligne grise, ex. « Cours en ligne · À votre rythme »"
    )
    description = models.TextField(blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    prix_barre = models.DecimalField(
        "prix barré", max_digits=10, decimal_places=2, null=True, blank=True, help_text="Ancien prix affiché barré"
    )
    reduction = models.CharField(max_length=40, blank=True, help_text="ex. « Remise de 99 % »")
    avec_modules = models.BooleanField(
        "organisé en modules", default=False,
        help_text="Décoché : le cours est une simple liste de leçons. Coché : les leçons sont regroupées en modules.",
    )
    sur_accueil = models.BooleanField("afficher sur l'accueil", default=False)
    en_vedette = models.BooleanField("en vedette (grand bandeau)", default=False)
    ordre = models.PositiveIntegerField(default=0)
    publie = models.BooleanField("publié", default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    objects = CoursQuerySet.as_manager()

    class Meta:
        ordering = ["ordre", "-cree_le"]
        verbose_name = "cours"
        verbose_name_plural = "cours"

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse("cours_detail", args=[self.slug])

    @property
    def est_gratuit(self):
        return self.prix == 0

    def a_acces(self, user):
        """Vrai si l'élève est inscrit (cours payé OU gratuit) ; l'équipe voit tout."""
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        return self.inscriptions.filter(eleve=user).exists()


class Module(models.Model):
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name="modules")
    titre = models.CharField(max_length=200)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "id"]

    def __str__(self):
        return self.titre


class Lecon(models.Model):
    # « cours » est toujours celui du module (renseigné par save) : il sert aux accès directs cours.lecons
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name="lecons", editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lecons")
    titre = models.CharField(max_length=200)
    ordre = models.PositiveIntegerField(default=0)
    video_url = models.URLField(
        "lien de la vidéo", blank=True,
        help_text="Collez simplement le lien YouTube ou Vimeo (ou un lien d'intégration Bunny Stream)",
    )
    contenu = models.TextField(blank=True, help_text="Texte de la leçon")
    apercu = models.BooleanField("aperçu gratuit", default=False, help_text="Visible sans acheter le cours")

    class Meta:
        ordering = ["module__ordre", "module_id", "ordre", "id"]
        verbose_name = "leçon"

    @property
    def video_integree(self):
        """Adresse à mettre dans l'iframe : un lien YouTube/Vimeo « normal » est converti en lien d'intégration."""
        url = self.video_url.strip()
        youtube = re.match(
            r"https://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})", url
        )
        if youtube:
            return f"https://www.youtube-nocookie.com/embed/{youtube.group(1)}"
        vimeo = re.match(r"https://(?:www\.)?vimeo\.com/(?:video/)?(\d+)", url)
        if vimeo:
            return f"https://player.vimeo.com/video/{vimeo.group(1)}"
        return url

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.module_id:  # leçon créée sans module : on la range dans un module par défaut
            self.module, _ = Module.objects.get_or_create(cours_id=self.cours_id, ordre=0, defaults={"titre": "Contenu du cours"})
        self.cours_id = self.module.cours_id
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("lecon", args=[self.cours.slug, self.pk])


class Projet(models.Model):
    titre = models.CharField(max_length=200)
    categorie = models.CharField("catégorie", max_length=60)
    image = models.ImageField(upload_to="projets/")
    note = models.CharField(max_length=200, blank=True, default="Projet de démonstration")
    ordre = models.PositiveIntegerField(default=0)
    publie = models.BooleanField("publié", default=True)

    class Meta:
        ordering = ["ordre", "id"]

    def __str__(self):
        return self.titre


class Achat(models.Model):
    EN_ATTENTE = "en_attente"
    PAYE = "paye"
    ANNULE = "annule"
    STATUTS = [(EN_ATTENTE, "En attente"), (PAYE, "Payé"), (ANNULE, "Annulé")]

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="achats")
    cours = models.ForeignKey(Cours, on_delete=models.PROTECT, related_name="achats")
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    statut = models.CharField(max_length=20, choices=STATUTS, default=EN_ATTENTE)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    paye_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.eleve} — {self.cours}"

    def marquer_paye(self):
        self.statut = self.PAYE
        self.paye_le = timezone.now()
        self.save(update_fields=["statut", "paye_le"])
        # L'accès au cours est donné ici, et seulement ici, une fois le paiement confirmé.
        Inscription.objects.get_or_create(eleve=self.eleve, cours=self.cours, defaults={"achat": self})


class Activite(models.Model):
    """Un élève est « actif » un jour donné quand il s'est servi du site ce jour-là."""

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activites")
    jour = models.DateField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["eleve", "jour"], name="activite_unique_par_jour")]


class SuiviCours(models.Model):
    """Un élève a ouvert une leçon d'un cours un jour donné (sert au classement des cours les plus suivis)."""

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suivis")
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name="suivis")
    jour = models.DateField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["eleve", "cours", "jour"], name="suivi_unique_par_jour")]


class Inscription(models.Model):
    """Droit d'accès d'un élève à un cours, payant ou gratuit. « Mes cours » affiche ces lignes."""

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inscriptions")
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name="inscriptions")
    achat = models.OneToOneField(Achat, null=True, blank=True, on_delete=models.SET_NULL, related_name="inscription")
    gratuite = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]
        constraints = [models.UniqueConstraint(fields=["eleve", "cours"], name="inscription_unique")]

    def __str__(self):
        return f"{self.eleve} → {self.cours}"


class LeconTerminee(models.Model):
    """Leçon marquée comme terminée par un élève (sert à la progression)."""

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecons_terminees")
    lecon = models.ForeignKey(Lecon, on_delete=models.CASCADE, related_name="terminees")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["eleve", "lecon"], name="lecon_terminee_unique")]
