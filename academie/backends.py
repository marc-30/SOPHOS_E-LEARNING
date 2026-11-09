from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOuIdentifiantBackend(ModelBackend):
    """Connexion avec l'identifiant OU l'adresse e-mail (si l'e-mail n'appartient qu'à un seul compte)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and password and "@" in username:
            User = get_user_model()
            comptes = list(User.objects.filter(email__iexact=username.strip())[:2])
            if len(comptes) == 1:
                username = comptes[0].get_username()
        return super().authenticate(request, username=username, password=password, **kwargs)
