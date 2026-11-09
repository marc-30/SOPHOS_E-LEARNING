from django.utils import timezone

from .models import Activite


class ActiviteEleveMiddleware:
    """Note qu'un élève connecté a utilisé le site aujourd'hui (une seule écriture par jour et par session)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_staff:
            aujourdhui = timezone.localdate()
            if request.session.get("activite_jour") != aujourdhui.isoformat():
                Activite.objects.get_or_create(eleve=user, jour=aujourdhui)
                request.session["activite_jour"] = aujourdhui.isoformat()
        return self.get_response(request)
