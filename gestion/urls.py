from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("", views.tableau_de_bord, name="tableau_de_bord"),
    path("api/stats/", views.api_stats, name="api_stats"),
    path("connexion/", views.connexion, name="connexion"),
    path("verification/", views.verification, name="verification"),
    path("activation/", views.activation, name="activation"),
    path("activation/qr.svg", views.activation_qr, name="activation_qr"),
    path("codes-secours/", views.codes_secours, name="codes_secours"),
    path("codes-secours/regenerer/", views.regenerer_codes, name="regenerer_codes"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("mot-de-passe/", views.mot_de_passe, name="mot_de_passe"),
    path("cours/", views.cours_liste, name="cours_liste"),
    path("cours/nouveau/", views.cours_form, name="cours_nouveau"),
    path("cours/<int:pk>/", views.cours_form, name="cours_modifier"),
    path("cours/<int:pk>/publier/", views.cours_publier, name="cours_publier"),
    path("cours/<int:pk>/supprimer/", views.cours_supprimer, name="cours_supprimer"),
    path("categories/", views.categories_liste, name="categories_liste"),
    path("categories/nouvelle/", views.categorie_form, name="categorie_nouvelle"),
    path("categories/<int:pk>/", views.categorie_form, name="categorie_modifier"),
    path("categories/<int:pk>/supprimer/", views.categorie_supprimer, name="categorie_supprimer"),
    path("etudiants/", views.etudiants_liste, name="etudiants_liste"),
    path("etudiants/<int:pk>/", views.etudiant_detail, name="etudiant_detail"),
    path("etudiants/<int:pk>/modifier/", views.etudiant_modifier, name="etudiant_modifier"),
    path("etudiants/<int:pk>/statut/", views.etudiant_statut, name="etudiant_statut"),
    path("professeurs/", views.professeurs_liste, name="professeurs_liste"),
    path("professeurs/nouveau/", views.professeur_form, name="professeur_nouveau"),
    path("professeurs/<int:pk>/", views.professeur_form, name="professeur_modifier"),
    path("professeurs/<int:pk>/supprimer/", views.professeur_supprimer, name="professeur_supprimer"),
    path("ventes/", views.ventes_liste, name="ventes_liste"),
]
