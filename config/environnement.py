"""Lecture de la configuration depuis les variables d'environnement.

Les fonctions reçoivent le dictionnaire d'environnement en paramètre pour pouvoir être
testées sans toucher à l'environnement réel. Elles refusent de démarrer en production
(DJANGO_DEBUG=False) avec une configuration dangereuse.
"""

from django.core.exceptions import ImproperlyConfigured

CLE_PAR_DEFAUT = "cle-de-developpement-a-remplacer"
LONGUEUR_MINIMALE_CLE = 32


def booleen(valeur, defaut=False):
    if valeur is None or valeur == "":
        return defaut
    return str(valeur).strip().lower() in ("1", "true", "vrai", "oui", "yes", "on")


def mode_debug(env):
    """Le mode debug est actif par défaut (développement) ; la production met DJANGO_DEBUG=False."""
    return booleen(env.get("DJANGO_DEBUG"), defaut=True)


def cle_secrete(env, debug):
    cle = env.get("DJANGO_SECRET_KEY", "")
    if debug:
        return cle or CLE_PAR_DEFAUT
    if not cle or cle == CLE_PAR_DEFAUT:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY doit être définie avec une valeur secrète en production."
        )
    if len(cle) < LONGUEUR_MINIMALE_CLE:
        raise ImproperlyConfigured(
            f"DJANGO_SECRET_KEY est trop courte (au moins {LONGUEUR_MINIMALE_CLE} caractères)."
        )
    return cle


def hotes_autorises(env, debug):
    hotes = [h.strip() for h in env.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not debug and not hotes:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS doit lister les noms de domaine autorisés en production."
        )
    return hotes


def configuration_base(env, base_dir):
    """SQLite en développement ; PostgreSQL (recommandé) en production."""
    moteur = env.get("DB_ENGINE", "sqlite").strip().lower()

    if moteur in ("postgresql", "postgres"):
        manquantes = [nom for nom in ("DB_NAME", "DB_USER", "DB_PASSWORD") if not env.get(nom)]
        if manquantes:
            raise ImproperlyConfigured(
                "Variables manquantes pour PostgreSQL : " + ", ".join(manquantes) + "."
            )
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env["DB_NAME"],
                "USER": env["DB_USER"],
                "PASSWORD": env["DB_PASSWORD"],
                "HOST": env.get("DB_HOST", "localhost"),
                "PORT": env.get("DB_PORT", "5432"),
                "CONN_MAX_AGE": int(env.get("DB_CONN_MAX_AGE", "60")),
            }
        }

    if moteur == "sqlite":
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": env.get("DB_NAME") or base_dir / "db.sqlite3",
            }
        }

    raise ImproperlyConfigured(f"DB_ENGINE inconnu : « {moteur} » (utilisez sqlite ou postgresql).")


def parametres_securite(env, debug):
    """Réglages de sécurité appliqués en production : HTTPS obligatoire, cookies sécurisés,
    HSTS. En développement (HTTP local), rien n'est imposé."""
    if debug:
        return {}
    reglages = {
        "SECURE_SSL_REDIRECT": booleen(env.get("DJANGO_SSL_REDIRECT"), defaut=True),
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_HSTS_SECONDS": int(env.get("DJANGO_HSTS_SECONDS", "31536000")),
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": booleen(env.get("DJANGO_HSTS_SOUS_DOMAINES")),
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "X_FRAME_OPTIONS": "DENY",
    }
    # Derrière un serveur web (nginx...) qui termine le HTTPS et transmet X-Forwarded-Proto
    if booleen(env.get("DJANGO_PROXY_HTTPS")):
        reglages["SECURE_PROXY_SSL_HEADER"] = ("HTTP_X_FORWARDED_PROTO", "https")
    return reglages
