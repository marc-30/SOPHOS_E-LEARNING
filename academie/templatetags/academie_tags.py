from decimal import Decimal

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def prix(valeur):
    """Affiche un montant à la française : 94.99 -> « 94,99 $ »."""
    if valeur in (None, ""):
        return ""
    texte = f"{Decimal(valeur):,.2f}".replace(",", " ").replace(".", ",")
    return f"{texte} {getattr(settings, 'DEVISE', '$')}"
