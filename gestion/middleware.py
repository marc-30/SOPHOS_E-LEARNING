from django.conf import settings
from django.http.request import split_domain_port

URLCONF_GESTION = "sophos.urls_gestion"


class RoutageParHoteMiddleware:
    """Sépare le site public et l'administration selon le nom de domaine.

    - ADMIN_HOST (ex. gestion.sophos.com) ne sert QUE l'administration ;
    - tous les autres domaines ne servent QUE le site public : l'admin n'y existe pas (404).
    Doit être le premier middleware de la liste.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        domaine, _ = split_domain_port(request.get_host())
        if domaine == settings.ADMIN_HOST:
            request.urlconf = URLCONF_GESTION
        return self.get_response(request)


class EnTetesSecuriteGestionMiddleware:
    """En-têtes stricts sur l'administration : pas de script ni de style en ligne, pas d'iframe, pas de cache."""

    CSP = (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reponse = self.get_response(request)
        if getattr(request, "urlconf", None) == URLCONF_GESTION and not request.path.startswith("/django-admin/"):
            reponse.headers.setdefault("Content-Security-Policy", self.CSP)
            reponse.headers["Cache-Control"] = "no-store"
            reponse.headers["X-Content-Type-Options"] = "nosniff"
            reponse.headers["X-Frame-Options"] = "DENY"
            reponse.headers["Referrer-Policy"] = "same-origin"
            reponse.headers["X-Robots-Tag"] = "noindex, nofollow"
            reponse.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return reponse
