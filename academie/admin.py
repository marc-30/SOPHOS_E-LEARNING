from django.contrib import admin
from django.utils.html import format_html

from .models import Achat, Categorie, Cours, Inscription, Lecon, Module, Projet

admin.site.site_header = "Sophos Académie — Administration"
admin.site.site_title = "Sophos Académie"
admin.site.index_title = "Gestion du site"


def miniature(obj):
    if obj.image:
        return format_html('<img src="{}" style="height:40px;border-radius:4px">', obj.image.url)
    return ""


miniature.short_description = "Image"


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ["nom", "slug", "ordre"]
    list_editable = ["ordre"]
    prepopulated_fields = {"slug": ["nom"]}


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    fields = ["ordre", "titre"]


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = [miniature, "titre", "categorie", "prix", "badge", "sur_accueil", "en_vedette", "publie", "ordre"]
    list_display_links = [miniature, "titre"]
    list_editable = ["prix", "badge", "sur_accueil", "publie", "ordre"]
    list_filter = ["categorie", "publie", "sur_accueil", "badge"]
    search_fields = ["titre", "auteur"]
    prepopulated_fields = {"slug": ["titre"]}
    inlines = [ModuleInline]
    fieldsets = [
        (None, {"fields": ["titre", "slug", "categorie", "image", "video_bienvenue", "description"]}),
        ("Carte du cours", {"fields": ["badge", "niveau", "duree", "auteur", "sous_titre"]}),
        ("Prix", {"fields": ["prix", "prix_barre", "reduction"]}),
        ("Affichage", {"fields": ["publie", "sur_accueil", "en_vedette", "ordre"]}),
    ]


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = [miniature, "titre", "categorie", "publie", "ordre"]
    list_display_links = [miniature, "titre"]
    list_editable = ["publie", "ordre"]


@admin.register(Achat)
class AchatAdmin(admin.ModelAdmin):
    list_display = ["cree_le", "eleve", "cours", "montant", "statut", "paye_le"]
    list_filter = ["statut", "cours"]
    search_fields = ["eleve__username", "eleve__email", "cours__titre", "reference"]
    readonly_fields = ["reference", "cree_le", "paye_le"]
    date_hierarchy = "cree_le"


from .models import Professeur  # noqa: E402


@admin.register(Professeur)
class ProfesseurAdmin(admin.ModelAdmin):
    list_display = ["nom", "email", "actif"]
    search_fields = ["nom", "email"]


@admin.register(Lecon)
class LeconAdmin(admin.ModelAdmin):
    list_display = ["titre", "module", "cours", "ordre", "apercu"]
    list_filter = ["cours"]
    search_fields = ["titre"]


@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ["cree_le", "eleve", "cours", "gratuite"]
    list_filter = ["gratuite", "cours"]
    search_fields = ["eleve__username", "eleve__email", "cours__titre"]
