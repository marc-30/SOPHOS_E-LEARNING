import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from academie.models import Activite, Cours, SuiviCours


class Command(BaseCommand):
    help = "Crée des élèves et de l'activité fictifs (90 jours) pour voir le tableau de bord rempli. À ne pas lancer en production."

    def handle(self, *args, **options):
        random.seed(7)
        cours = list(Cours.objects.all())
        if not cours:
            self.stderr.write("Aucun cours : lance d'abord importer_demo.")
            return
        auj = timezone.localdate()
        eleves = [User.objects.get_or_create(username=f"demo{i}", defaults={"email": f"demo{i}@example.com"})[0] for i in range(1, 31)]
        for e in eleves:
            e.date_joined = timezone.now() - timedelta(days=random.randint(0, 89))
            e.save(update_fields=["date_joined"])
        poids = [random.randint(1, 10) for _ in cours]
        for jour in (auj - timedelta(days=i) for i in range(90)):
            for e in random.sample(eleves, random.randint(2, 18)):
                if e.date_joined.date() <= jour:
                    Activite.objects.get_or_create(eleve=e, jour=jour)
                    c = random.choices(cours, poids)[0]
                    SuiviCours.objects.get_or_create(eleve=e, cours=c, jour=jour)
        self.stdout.write(self.style.SUCCESS("Activité fictive créée (comptes demo1 à demo30)."))
