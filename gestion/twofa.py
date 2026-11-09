"""Double authentification par code TOTP (RFC 6238) : Google Authenticator, Authy, Microsoft Authenticator…"""
import base64
import hashlib
import hmac
import io
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from .models import Appareil2FA

PAS = 30
NB_CODES_SECOURS = 8
ISSUER = "Sophos Académie"


def _fernet():
    # Clé dérivée de SECRET_KEY. Si SECRET_KEY change, les appareils enregistrés doivent être réinitialisés.
    cle = hashlib.sha256(b"gestion-2fa|" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(cle))


def chiffrer(secret):
    return _fernet().encrypt(secret.encode()).decode()


def dechiffrer(valeur):
    try:
        return _fernet().decrypt(valeur.encode()).decode()
    except InvalidToken:
        return None


def appareil_de(user):
    return Appareil2FA.objects.filter(user=user).first()


def preparer_appareil(user):
    """Appareil du compte : celui déjà enregistré (confirmé ou en cours d'activation), sinon un nouveau secret."""
    appareil = appareil_de(user)
    if appareil:
        return appareil
    return Appareil2FA.objects.create(user=user, secret_chiffre=chiffrer(pyotp.random_base32()))


def uri(appareil):
    return pyotp.TOTP(dechiffrer(appareil.secret_chiffre)).provisioning_uri(name=appareil.user.get_username(), issuer_name=ISSUER)


def secret_affichable(appareil):
    secret = dechiffrer(appareil.secret_chiffre) or ""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


def qr_svg(appareil):
    image = qrcode.make(uri(appareil), image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    sortie = io.BytesIO()
    image.save(sortie)
    return sortie.getvalue()


def verifier_code(appareil, code, maintenant=None):
    """Vrai si le code à 6 chiffres est valide (±1 pas de 30 s) et pas déjà utilisé."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    secret = dechiffrer(appareil.secret_chiffre)
    if len(code) != 6 or not secret:
        return False
    totp = pyotp.TOTP(secret, interval=PAS)
    maintenant = time.time() if maintenant is None else maintenant
    for decalage in (-1, 0, 1):
        t = maintenant + decalage * PAS
        pas = int(t // PAS)
        if hmac.compare_digest(totp.at(t), code) and pas > appareil.dernier_pas:
            appareil.dernier_pas = pas
            appareil.save(update_fields=["dernier_pas"])
            return True
    return False


def _empreinte(code):
    code = code.strip().lower().replace(" ", "")
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def generer_codes_secours(appareil):
    """Remplace les codes de secours ; renvoie les codes en clair (affichés une seule fois)."""
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(NB_CODES_SECOURS)]
    appareil.codes_secours = [_empreinte(c) for c in codes]
    appareil.save(update_fields=["codes_secours"])
    return codes


def utiliser_code_secours(appareil, code):
    empreinte = _empreinte(code or "")
    for stocke in appareil.codes_secours:
        if hmac.compare_digest(stocke, empreinte):
            appareil.codes_secours = [c for c in appareil.codes_secours if c != stocke]
            appareil.save(update_fields=["codes_secours"])
            return True
    return False
