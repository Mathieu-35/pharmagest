"""Sauvegarde et restauration de PharmaGest.

Une sauvegarde est une archive ZIP contenant :
- donnees.json : toutes les données de la base (utilisateurs, rôles, médicaments, lots, ventes...) ;
- media/ : les photos des médicaments ;
- manifest.json : date, nombre d'objets par table, empreinte SHA-256 de chaque fichier.

Le format JSON de Django est indépendant du moteur : une sauvegarde faite sur SQLite peut être
restaurée sur PostgreSQL et inversement. À la restauration, l'archive est d'abord vérifiée
(empreintes), puis les données sont remplacées dans une transaction : en cas d'erreur, rien
n'est modifié. Les comptes, rôles et mots de passe (hachés) sont inclus : l'archive est donc
sensible et doit être conservée dans un endroit protégé.
"""

import hashlib
import io
import json
import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.serializers.base import DeserializationError
from django.db import DEFAULT_DB_ALIAS, DatabaseError, transaction
from django.utils import timezone

VERSION_FORMAT = 1
# Recréés par les migrations, sans table (rapports.rapport), ou sans intérêt à sauvegarder
EXCLUS = ["contenttypes", "auth.permission", "sessions", "rapports.rapport"]
MODELES_CONSERVES = (ContentType, Permission)


class ErreurSauvegarde(Exception):
    """Sauvegarde ou restauration refusée ; le message est affichable à l'utilisateur."""


class _Annulation(Exception):
    """Sert à annuler la transaction d'un essai de restauration."""


def _empreinte(donnees):
    return hashlib.sha256(donnees).hexdigest()


def _chemin_sur(relatif):
    """Refuse les chemins absolus ou remontant dans l'arborescence (../)."""
    chemin = Path(relatif)
    return not chemin.is_absolute() and ".." not in chemin.parts and relatif.strip() != ""


def _fichiers_media():
    racine = Path(settings.MEDIA_ROOT)
    if not racine.exists():
        return []
    return sorted(p for p in racine.rglob("*") if p.is_file())


# ---------------------------------------------------------------------- Sauvegarde

def creer_sauvegarde(dossier=None, prefixe="pharmagest"):
    """Crée l'archive, la vérifie, et retourne (chemin, manifest)."""
    dossier = Path(dossier or settings.SAUVEGARDES_DIR)
    dossier.mkdir(parents=True, exist_ok=True)

    sortie = io.StringIO()
    call_command("dumpdata", exclude=EXCLUS, use_natural_foreign_keys=True, indent=1, stdout=sortie)
    donnees = sortie.getvalue().encode("utf-8")
    comptes = Counter(objet["model"] for objet in json.loads(donnees))

    horodatage = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    chemin = dossier / f"{prefixe}-{horodatage}.zip"
    numero = 1
    while chemin.exists():
        numero += 1
        chemin = dossier / f"{prefixe}-{horodatage}-{numero}.zip"

    media, contenus = [], {}
    for fichier in _fichiers_media():
        relatif = fichier.relative_to(settings.MEDIA_ROOT).as_posix()
        contenu = fichier.read_bytes()
        contenus[relatif] = contenu
        media.append({"chemin": relatif, "sha256": _empreinte(contenu), "taille": len(contenu)})

    manifest = {
        "format": VERSION_FORMAT,
        "date": timezone.localtime().isoformat(timespec="seconds"),
        "moteur": settings.DATABASES[DEFAULT_DB_ALIAS]["ENGINE"].rsplit(".", 1)[-1],
        "donnees_sha256": _empreinte(donnees),
        "objets": sum(comptes.values()),
        "comptes": dict(sorted(comptes.items())),
        "media": media,
    }

    temporaire = chemin.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
        archive.writestr("donnees.json", donnees)
        for relatif, contenu in contenus.items():
            archive.writestr(f"media/{relatif}", contenu)
    os.replace(temporaire, chemin)
    try:
        os.chmod(chemin, 0o600)  # lecture réservée au propriétaire (sans effet sous Windows)
    except OSError:
        pass

    verifier_archive(chemin)  # une sauvegarde non vérifiée ne vaut rien
    return chemin, manifest


# -------------------------------------------------------------------- Vérification

def verifier_archive(chemin):
    """Contrôle l'intégrité de l'archive et retourne (manifest, données JSON en octets)."""
    chemin = Path(chemin)
    if not chemin.is_file():
        raise ErreurSauvegarde(f"Fichier introuvable : {chemin}")
    try:
        with zipfile.ZipFile(chemin) as archive:
            if archive.testzip() is not None:
                raise ErreurSauvegarde("Archive corrompue (échec du contrôle ZIP).")
            noms = set(archive.namelist())
            if not {"manifest.json", "donnees.json"} <= noms:
                raise ErreurSauvegarde("Archive invalide : manifest.json ou donnees.json manquant.")
            manifest = json.loads(archive.read("manifest.json"))
            donnees = archive.read("donnees.json")
            if manifest.get("format") != VERSION_FORMAT:
                raise ErreurSauvegarde("Format de sauvegarde non reconnu.")
            if _empreinte(donnees) != manifest.get("donnees_sha256"):
                raise ErreurSauvegarde("Les données de l'archive ont été altérées (empreinte différente).")
            for fichier in manifest.get("media", []):
                if not _chemin_sur(fichier["chemin"]):
                    raise ErreurSauvegarde(f"Chemin de photo refusé : {fichier['chemin']}")
                nom = f"media/{fichier['chemin']}"
                if nom not in noms:
                    raise ErreurSauvegarde(f"Photo manquante dans l'archive : {fichier['chemin']}")
                if _empreinte(archive.read(nom)) != fichier["sha256"]:
                    raise ErreurSauvegarde(f"Photo altérée dans l'archive : {fichier['chemin']}")
            json.loads(donnees)
    except zipfile.BadZipFile:
        raise ErreurSauvegarde("Ce fichier n'est pas une archive de sauvegarde valide.")
    except (json.JSONDecodeError, KeyError):
        raise ErreurSauvegarde("Contenu de l'archive illisible.")
    return manifest, donnees


# ------------------------------------------------------------------- Restauration

def _modeles_a_vider():
    return [
        m for m in apps.get_models(include_auto_created=True)
        if m._meta.managed and not m._meta.proxy and m not in MODELES_CONSERVES
    ]


def _vider_les_donnees(base=DEFAULT_DB_ALIAS):
    """Supprime toutes les lignes, en commençant par les tables qui dépendent des autres."""
    restants = set(_modeles_a_vider())

    def dependants(modele):
        """Modèles restants qui pointent vers `modele` par une clé étrangère."""
        return {
            autre for autre in restants
            if autre is not modele and any(
                champ.is_relation and champ.concrete and champ.related_model is modele
                for champ in autre._meta.get_fields()
            )
        }

    while restants:
        libres = [m for m in restants if not dependants(m)]
        if not libres:
            raise ErreurSauvegarde("Dépendances circulaires entre les tables : restauration impossible.")
        for modele in libres:
            modele._base_manager.using(base).all()._raw_delete(base)
            restants.discard(modele)


def _compter(base=DEFAULT_DB_ALIAS):
    return Counter({
        modele._meta.label_lower: modele._base_manager.using(base).count()
        for modele in apps.get_models(include_auto_created=True)
        if modele._meta.managed and not modele._meta.proxy
    })


def restaurer(chemin, essai=False, base=DEFAULT_DB_ALIAS):
    """Remplace toutes les données par celles de l'archive.

    - L'archive est vérifiée avant toute modification.
    - Tout se passe dans une transaction : en cas d'erreur, la base reste inchangée.
    - Avec essai=True, la restauration est menée jusqu'au bout puis annulée (aucun effet).
    - Hors essai, une sauvegarde de sécurité de l'état actuel est faite d'abord.
    Retourne un résumé.
    """
    manifest, donnees = verifier_archive(chemin)

    sauvegarde_securite = None
    if not essai:
        sauvegarde_securite, _ = creer_sauvegarde(prefixe="avant-restauration")

    attendus = Counter(manifest["comptes"])
    with tempfile.TemporaryDirectory() as temporaire:
        fixture = Path(temporaire) / "donnees.json"
        fixture.write_bytes(donnees)
        try:
            with transaction.atomic(using=base):
                _vider_les_donnees(base)
                call_command("loaddata", str(fixture), verbosity=0, database=base)
                obtenus = _compter(base)
                ecarts = {
                    modele: (attendu, obtenus.get(modele, 0))
                    for modele, attendu in attendus.items() if obtenus.get(modele, 0) != attendu
                }
                if ecarts:
                    raise ErreurSauvegarde(
                        "Restauration annulée : le nombre d'enregistrements ne correspond pas "
                        + ", ".join(f"{m} ({a} attendus, {o} obtenus)" for m, (a, o) in sorted(ecarts.items()))
                    )
                if essai:
                    raise _Annulation
        except _Annulation:
            pass
        except (DatabaseError, DeserializationError, ValueError) as erreur:
            raise ErreurSauvegarde(
                f"Restauration annulée, aucune donnée n'a été modifiée : {erreur}"
            )

    fichiers = 0
    if not essai:
        fichiers = _restaurer_photos(chemin, manifest)

    return {
        "objets": manifest["objets"], "photos": fichiers, "essai": essai,
        "date_sauvegarde": manifest["date"], "sauvegarde_securite": sauvegarde_securite,
    }


def _restaurer_photos(chemin, manifest):
    racine = Path(settings.MEDIA_ROOT).resolve()
    ecrits = 0
    with zipfile.ZipFile(chemin) as archive:
        for fichier in manifest.get("media", []):
            cible = (racine / fichier["chemin"]).resolve()
            if racine not in cible.parents:   # protection contre les chemins du type ../../
                raise ErreurSauvegarde(f"Chemin de photo refusé : {fichier['chemin']}")
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(archive.read(f"media/{fichier['chemin']}"))
            ecrits += 1
    return ecrits
