from django.db import migrations


def creer_professeurs(apps, schema_editor):
    Professeur = apps.get_model("academie", "Professeur")
    Cours = apps.get_model("academie", "Cours")
    for nom in Cours.objects.filter(professeur__isnull=True).values_list("auteur", flat=True).distinct():
        prof, _ = Professeur.objects.get_or_create(nom=nom)
        Cours.objects.filter(auteur=nom, professeur__isnull=True).update(professeur=prof)


class Migration(migrations.Migration):
    dependencies = [("academie", "0002_professeur_suivi")]
    operations = [migrations.RunPython(creer_professeurs, migrations.RunPython.noop)]
