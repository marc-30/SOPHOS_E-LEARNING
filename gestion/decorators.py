from functools import wraps

from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache


def staff_requis(vue):
    """Réserve la vue aux comptes équipe actifs ; sinon renvoie vers la connexion admin."""

    @wraps(vue)
    @never_cache
    def enveloppe(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), "gestion:connexion")
        if not (user.is_active and user.is_staff):
            raise PermissionDenied
        # Le mot de passe seul ne suffit jamais : le code du téléphone doit avoir été vérifié dans CETTE session.
        if request.session.get("gestion_2fa") != user.pk:
            logout(request)
            return redirect_to_login(request.get_full_path(), "gestion:connexion")
        return vue(request, *args, **kwargs)

    return enveloppe
