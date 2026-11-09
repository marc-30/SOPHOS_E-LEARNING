from django.conf import settings
from django.db import models


class Appareil2FA(models.Model):
    """Application d'authentification (code à 6 chiffres) liée à un compte de l'équipe."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appareil_2fa")
    secret_chiffre = models.TextField()  # jamais en clair en base
    confirme = models.BooleanField(default=False)
    dernier_pas = models.BigIntegerField(default=0)  # dernier code accepté : un code ne sert qu'une fois
    codes_secours = models.JSONField(default=list)  # empreintes (SHA-256) des codes de secours non utilisés
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "appareil 2FA"
        verbose_name_plural = "appareils 2FA"

    def __str__(self):
        return f"2FA de {self.user}"
