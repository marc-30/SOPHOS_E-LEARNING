from django.db import migrations


def migrer(apps, schema_editor):
    Cours = apps.get_model("academie", "Cours")
    Module = apps.get_model("academie", "Module")
    Lecon = apps.get_model("academie", "Lecon")
    Achat = apps.get_model("academie", "Achat")
    Inscription = apps.get_model("academie", "Inscription")
    # Chaque cours qui avait des leçons reçoit un module « Contenu du cours » qui les regroupe
    for cours in Cours.objects.filter(lecons__isnull=False).distinct():
        module = Module.objects.create(cours=cours, titre="Contenu du cours", ordre=0)
        Lecon.objects.filter(cours=cours, module__isnull=True).update(module=module)
    # Chaque achat déjà payé devient une inscription
    for achat in Achat.objects.filter(statut="paye"):
        Inscription.objects.get_or_create(eleve_id=achat.eleve_id, cours_id=achat.cours_id, defaults={"achat_id": achat.pk})


class Migration(migrations.Migration):
    dependencies = [("academie", "0004_modules_inscriptions")]
    operations = [migrations.RunPython(migrer, migrations.RunPython.noop)]
