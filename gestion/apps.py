from django.apps import AppConfig


class GestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestion"

    def ready(self):
        # L'ancienne admin Django (/django-admin/) ne doit pas contourner la double authentification :
        # elle n'accepte que les sessions où le code du téléphone a été vérifié, et sa page de connexion
        # renvoie vers celle de l'administration Sophos.
        from django.contrib import admin
        from django.shortcuts import redirect

        def a_le_droit(request):
            u = request.user
            return u.is_active and u.is_staff and request.session.get("gestion_2fa") == u.pk

        admin.site.has_permission = a_le_droit
        admin.site.login = lambda request, extra_context=None: redirect("gestion:connexion")
