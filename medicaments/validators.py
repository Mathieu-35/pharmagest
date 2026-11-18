from django.core.exceptions import ValidationError
from django.db.models.fields.files import FieldFile
from PIL import Image

FORMATS_AUTORISES = {"JPEG", "PNG", "WEBP"}
TAILLE_MAX = 2 * 1024 * 1024  # 2 Mo


def valider_photo(fichier):
    """Vérifie le type et la taille d'une photo nouvellement envoyée."""
    if isinstance(fichier, FieldFile) and fichier._committed:
        return  # photo déjà enregistrée : rien à revérifier

    if fichier.size > TAILLE_MAX:
        raise ValidationError("La photo est trop lourde (2 Mo maximum).")

    try:
        fichier.seek(0)
        format_image = Image.open(fichier).format
    except Exception:
        raise ValidationError("Le fichier envoyé n'est pas une image valide.")
    finally:
        try:
            fichier.seek(0)
        except Exception:
            pass

    if format_image not in FORMATS_AUTORISES:
        raise ValidationError("Format non accepté : utilisez une image JPEG, PNG ou WEBP.")
