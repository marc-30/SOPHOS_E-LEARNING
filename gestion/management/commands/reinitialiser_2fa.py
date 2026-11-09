"""Réinitialise la double authentification d'un compte de l'équipe (téléphone perdu, codes de secours perdus).

Utilisation :  python manage.py reinitialiser_2fa NOM_UTILISATEUR
À la prochaine connexion, le compte devra relier à nouveau un téléphone (nouveau QR code).
Réservé à qui a accès au serveur : c'est le dernier recours.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from gestion.models import Appareil2FA


class Command(BaseCommand):
    help = "Supprime l'appareil de double authentification d'un compte de l'équipe."

    def add_arguments(self, parser):
        parser.add_argument("utilisateur", help="Identifiant du compte (ex. sophosstudy)")

    def handle(self, *args, **options):
        nom = options["utilisateur"]
        try:
            user = get_user_model().objects.get(username=nom, is_staff=True)
        except get_user_model().DoesNotExist:
            raise CommandError(f"Aucun compte de l'équipe nommé « {nom} ».")
        supprimes, _ = Appareil2FA.objects.filter(user=user).delete()
        if supprimes:
            self.stdout.write(self.style.SUCCESS(
                f"Double authentification réinitialisée pour « {nom} ». "
                "À la prochaine connexion, un nouveau QR code sera proposé."))
        else:
            self.stdout.write(f"« {nom} » n'avait pas de double authentification configurée.")
