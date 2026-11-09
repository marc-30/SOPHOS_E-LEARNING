import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academie", "0005_donnees_modules_inscriptions")]
    operations = [
        migrations.AlterField(
            model_name="lecon", name="module",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lecons", to="academie.module"),
        ),
    ]
