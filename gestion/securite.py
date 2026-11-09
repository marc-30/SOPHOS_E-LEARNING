"""Protection de la connexion : limite les essais de mot de passe (force brute)."""
import logging

from django.core.cache import cache

logger = logging.getLogger("gestion.securite")

MAX_ECHECS = 5
BLOCAGE_SECONDES = 15 * 60


def ip_client(request):
    # REMOTE_ADDR uniquement : X-Forwarded-For est falsifiable. Derrière un proxy (Render, Nginx…),
    # configurer le serveur pour qu'il fournisse la vraie adresse dans REMOTE_ADDR.
    return request.META.get("REMOTE_ADDR", "inconnue")


def _cles(request, identifiant):
    return [f"gestion:echecs:ip:{ip_client(request)}", f"gestion:echecs:user:{identifiant.strip().lower()[:150]}"]


def est_bloque(request, identifiant):
    return any(cache.get(cle, 0) >= MAX_ECHECS for cle in _cles(request, identifiant))


def enregistrer_echec(request, identifiant):
    for cle in _cles(request, identifiant):
        cache.add(cle, 0, BLOCAGE_SECONDES)
        try:
            cache.incr(cle)
        except ValueError:
            cache.set(cle, 1, BLOCAGE_SECONDES)
    logger.warning("Échec de connexion admin (ip=%s, identifiant=%r)", ip_client(request), identifiant[:60])


def effacer_echecs(request, identifiant):
    cache.delete(_cles(request, identifiant)[1])
