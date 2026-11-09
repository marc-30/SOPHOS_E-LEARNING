from django.db.models import Prefetch

from .models import Categorie, Cours


def menu_categories(request):
    """Catégories et cours publiés affichés dans le menu déroulant « Cours » de l'en-tête."""
    if getattr(request, "urlconf", None):  # administration : pas de menu public
        return {}
    return {
        "menu_categories": Categorie.objects.prefetch_related(
            Prefetch("cours", queryset=Cours.objects.publies(), to_attr="cours_publies")
        )
    }
