from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("cours/", views.catalogue, name="catalogue"),
    path("cours/<slug:slug>/", views.cours_detail, name="cours_detail"),
    path("cours/<slug:slug>/acheter/", views.acheter, name="acheter"),
    path("cours/<slug:slug>/lecon/<int:pk>/", views.lecon, name="lecon"),
    path("cours/<slug:slug>/inscription/", views.s_inscrire, name="s_inscrire"),
    path("cours/<slug:slug>/lecon/<int:pk>/terminer/", views.lecon_terminer, name="lecon_terminer"),
    path("paiement/<uuid:reference>/", views.paiement, name="paiement"),
    path("projets/", views.projets, name="projets"),
    path("plus/", views.plus, name="plus"),
    path("mes-cours/", views.mes_cours, name="mes_cours"),
    path("inscription/", views.inscription, name="inscription"),
    path("connexion/", auth_views.LoginView.as_view(), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
]
