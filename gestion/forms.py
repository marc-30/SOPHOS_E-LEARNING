from decimal import Decimal

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import URLValidator
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.text import slugify

from academie.models import Categorie, Cours, Lecon, Module, Professeur, ProfilEleve

TAILLE_MAX_IMAGE = 5 * 1024 * 1024
FORMATS_IMAGE = {"JPEG", "PNG", "WEBP", "GIF"}


def _verifier_image(fichier):
    if isinstance(fichier, UploadedFile):  # nouveau fichier envoyé (pas une image déjà enregistrée)
        if fichier.size > TAILLE_MAX_IMAGE:
            raise forms.ValidationError("Image trop lourde (5 Mo maximum).")
        image = getattr(fichier, "image", None)
        if image is not None and image.format not in FORMATS_IMAGE:
            raise forms.ValidationError("Format non accepté : JPEG, PNG, WebP ou GIF uniquement.")
    return fichier


TAILLE_MAX_VIDEO = 500 * 1024 * 1024
EXTENSIONS_VIDEO = {".mp4", ".webm", ".mov"}


def _verifier_video(fichier):
    """Contrôle d'un fichier vidéo envoyé : extension, taille et signature réelle (pas seulement le nom)."""
    if isinstance(fichier, UploadedFile):
        nom = fichier.name.lower()
        if not any(nom.endswith(ext) for ext in EXTENSIONS_VIDEO):
            raise forms.ValidationError("Format non accepté : MP4, WebM ou MOV uniquement.")
        if fichier.size > TAILLE_MAX_VIDEO:
            raise forms.ValidationError("Vidéo trop lourde (500 Mo maximum).")
        debut = fichier.read(12)
        fichier.seek(0)
        mp4 = debut[4:8] == b"ftyp"
        webm = debut[:4] == b"\x1a\x45\xdf\xa3"
        if not (mp4 or webm):
            raise forms.ValidationError("Ce fichier n’est pas une vidéo valide.")
    return fichier


class ConnexionForm(forms.Form):
    username = forms.CharField(max_length=150, label="Identifiant")
    password = forms.CharField(max_length=256, label="Mot de passe", widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        user = authenticate(self.request, username=data["username"], password=data["password"])
        # Même message dans tous les cas : on ne révèle pas si le compte existe.
        if user is None or not (user.is_active and user.is_staff):
            raise forms.ValidationError("Identifiant ou mot de passe incorrect.")
        self.user = user
        return data


class CodeForm(forms.Form):
    code = forms.CharField(max_length=20, strip=True)


class CoursForm(forms.ModelForm):
    class Meta:
        model = Cours
        fields = ["titre", "categorie", "professeur", "avec_modules", "image", "video_bienvenue", "badge", "niveau", "duree", "sous_titre",
                  "description", "prix", "prix_barre", "reduction", "sur_accueil", "en_vedette", "ordre", "publie"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    avec_modules = forms.TypedChoiceField(
        label="Organisation du cours", required=True, initial="False", widget=forms.RadioSelect,
        choices=[("False", "Sans module — une simple liste de leçons"), ("True", "Avec modules — leçons regroupées par modules")],
        coerce=lambda v: v == "True",
    )

    gratuit = forms.BooleanField(label="Gratuit", required=False, help_text="Coché : le cours est offert, les champs de prix sont ignorés.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["avec_modules"] = "True" if self.instance.avec_modules else "False"
            self.initial["gratuit"] = self.instance.est_gratuit
        fin = ["gratuit", "prix", "prix_barre", "reduction", "sur_accueil", "en_vedette", "ordre", "publie"]
        self.order_fields([f for f in self.fields if f not in fin] + fin)
        self.fields["prix"].required = False  # vérifié dans clean() : inutile si le cours est gratuit
        self.fields["professeur"].queryset = Professeur.objects.filter(actif=True)
        self.fields["professeur"].required = True
        self.fields["professeur"].empty_label = "— Choisir un professeur —"

    def clean_image(self):
        return _verifier_image(self.cleaned_data.get("image"))

    def clean_video_bienvenue(self):
        return _verifier_video(self.cleaned_data.get("video_bienvenue"))

    def clean_prix(self):
        prix = self.cleaned_data["prix"]
        if prix is not None and prix < 0:
            raise forms.ValidationError("Le prix ne peut pas être négatif.")
        return prix

    def clean(self):
        data = super().clean()
        if data.get("gratuit"):
            data.update(prix=Decimal("0"), prix_barre=None, reduction="")
            self.errors.pop("prix", None)
            self.errors.pop("prix_barre", None)
        elif data.get("prix") is None and "prix" not in self.errors:
            self.add_error("prix", "Indiquez un prix, ou cochez « Gratuit ».")
        return data

    def save(self, commit=True):
        cours = super().save(commit=False)
        cours.auteur = cours.professeur.nom
        if not cours.slug:
            base = slugify(cours.titre)[:180] or "cours"
            slug, n = base, 2
            while Cours.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            cours.slug = slug
        if commit:
            cours.save()
        return cours


class LeconForm(forms.ModelForm):
    class Meta:
        model = Lecon
        fields = ["titre", "ordre", "video_url", "contenu", "apercu"]
        widgets = {"contenu": forms.Textarea(attrs={"rows": 3})}

    def clean_video_url(self):
        url = self.cleaned_data.get("video_url", "")
        if url:
            URLValidator(schemes=["https"])(url)  # https uniquement : pas de javascript:, data:, http:
        return url


LeconFormSet = inlineformset_factory(Module, Lecon, form=LeconForm, extra=0, can_delete=True)


class BaseModuleFormSet(BaseInlineFormSet):
    """Modules d'un cours ; chaque module porte son propre formulaire de leçons (form.lecons)."""

    def add_fields(self, form, index):
        super().add_fields(form, index)
        # Le modèle vide (index None) reçoit un préfixe-repère que le JavaScript remplace à l'ajout d'un module.
        form.lecons = LeconFormSet(
            data=form.data if form.is_bound else None,
            files=form.files if form.is_bound else None,
            instance=form.instance,
            prefix=f"lecons-{'__m__' if index is None else index}",
        )

    def _a_traiter(self):
        return [f for f in self.forms if not self._should_delete_form(f)]

    def is_valid(self):
        valide = super().is_valid()
        # Toutes les leçons sont contrôlées (pas d'arrêt au premier module en erreur)
        return all([f.lecons.is_valid() for f in self._a_traiter()]) and valide

    def save(self, commit=True):
        modules = super().save(commit)
        for form in self._a_traiter():
            if form.instance.pk:  # module enregistré (les lignes vides ajoutées par erreur sont ignorées)
                form.lecons.instance = form.instance
                form.lecons.save()
        return modules


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["titre", "ordre"]


ModuleFormSet = inlineformset_factory(
    Cours, Module, form=ModuleForm, formset=BaseModuleFormSet, extra=0, can_delete=True
)
class ModuleFormNouveau(ModuleForm):
    def has_changed(self):
        return True  # le module prérempli doit être créé même si l'utilisateur n'y touche pas


# Nouveau cours : un premier module (invisible si le cours est « sans module ») est prêt à recevoir les leçons
ModuleFormSetNouveau = inlineformset_factory(
    Cours, Module, form=ModuleFormNouveau, formset=BaseModuleFormSet, extra=1, can_delete=True
)
MODULE_PAR_DEFAUT = "Contenu du cours"


def aplatir_cours(cours):
    """Cours « sans module » : toutes les leçons passent dans un seul module, dans l'ordre où elles étaient affichées."""
    lecons = list(cours.lecons.all())
    modules = list(cours.modules.all())
    if not modules:
        return
    premier = modules[0]
    for n, lecon in enumerate(lecons):
        Lecon.objects.filter(pk=lecon.pk).update(module=premier, ordre=n)
    cours.modules.exclude(pk=premier.pk).delete()
    Module.objects.filter(pk=premier.pk).update(titre=MODULE_PAR_DEFAUT, ordre=0)


class ProfesseurForm(forms.ModelForm):
    class Meta:
        model = Professeur
        fields = ["nom", "email", "bio", "photo", "actif"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def clean_photo(self):
        return _verifier_image(self.cleaned_data.get("photo"))


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ["nom", "ordre"]
        help_texts = {"ordre": "Position dans les menus : 0 s’affiche en premier."}

    def clean_nom(self):
        nom = self.cleaned_data["nom"].strip()
        if not slugify(nom):
            raise forms.ValidationError("Le nom doit contenir des lettres ou des chiffres.")
        if Categorie.objects.filter(nom__iexact=nom).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Une catégorie porte déjà ce nom.")
        return nom

    def save(self, commit=True):
        categorie = super().save(commit=False)
        if not categorie.slug:  # l'adresse est créée une fois, puis reste stable
            base = slugify(categorie.nom)[:45]
            slug, n = base, 2
            while Categorie.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            categorie.slug = slug
        if commit:
            categorie.save()
        return categorie


class EtudiantForm(forms.ModelForm):
    photo = forms.ImageField(label="Photo", required=False, help_text="JPEG, PNG, WebP ou GIF — 5 Mo maximum.")

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "username", "email", "is_active"]
        labels = {"first_name": "Prénom", "last_name": "Nom", "username": "Identifiant", "email": "E-mail", "is_active": "Compte actif"}
        help_texts = {"username": "", "is_active": "Décoché : l’étudiant ne peut plus se connecter."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profil = ProfilEleve.objects.filter(eleve=self.instance).first() if self.instance.pk else None
        self.fields["photo"].initial = profil.photo if profil else None

    def clean_photo(self):
        return _verifier_image(self.cleaned_data.get("photo"))

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if email and get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profil, _ = ProfilEleve.objects.get_or_create(eleve=user)
            photo = self.cleaned_data.get("photo")
            if photo is False:  # case « effacer » cochée
                profil.photo = ""
                profil.save()
            elif photo and photo != profil.photo:
                profil.photo = photo
                profil.save()
        return user
