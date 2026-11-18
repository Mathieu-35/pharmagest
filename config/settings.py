"""Configuration Django de PharmaGest.

Les valeurs sensibles sont lues dans les variables d'environnement
(fichier .env en développement, voir .env.example).
"""

import os
from pathlib import Path

from django.contrib.messages import constants as messages
from dotenv import load_dotenv

from config import environnement

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# DJANGO_DEBUG=False en production : la clé secrète et les hôtes autorisés deviennent alors
# obligatoires et les réglages HTTPS ci-dessous s'appliquent.
DEBUG = environnement.mode_debug(os.environ)

SECRET_KEY = environnement.cle_secrete(os.environ, DEBUG)

ALLOWED_HOSTS = environnement.hotes_autorises(os.environ, DEBUG)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Applications PharmaGest
    "utilisateurs",
    "medicaments",
    "fournisseurs",
    "clients",
    "achats",
    "stock",
    "ventes",
    "rapports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Base de données : SQLite en développement, PostgreSQL recommandé en production
# (DB_ENGINE=postgresql, voir .env.example et docs/INSTALLATION.md)
DATABASES = environnement.configuration_base(os.environ, BASE_DIR)


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Interface en français, fuseau de Madagascar
LANGUAGE_CODE = "fr"
TIME_ZONE = "Indian/Antananarivo"
USE_I18N = True
USE_TZ = True


# Fichiers statiques et médias (photos des médicaments)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Nombre de jours avant la péremption à partir duquel un lot est signalé « proche de la péremption »
JOURS_ALERTE_PEREMPTION = int(os.environ.get("JOURS_ALERTE_PEREMPTION", "30"))

# Informations de la pharmacie imprimées sur les documents PDF (reçus, factures, bons, rapports).
# À renseigner dans le fichier .env ; les mentions légales et fiscales doivent être celles
# applicables à Madagascar (ou au territoire d'exploitation).
PHARMACIE = {
    "nom": os.environ.get("PHARMACIE_NOM", "PharmaGest"),
    "adresse": os.environ.get("PHARMACIE_ADRESSE", ""),
    "telephone": os.environ.get("PHARMACIE_TELEPHONE", ""),
    "email": os.environ.get("PHARMACIE_EMAIL", ""),
    "numero_fiscal": os.environ.get("PHARMACIE_NUMERO_FISCAL", ""),
    "mentions_legales": os.environ.get("PHARMACIE_MENTIONS_LEGALES", ""),
}
DEVISE = os.environ.get("DEVISE", "Ar")

# Sécurité en production : HTTPS obligatoire, cookies sécurisés, HSTS
globals().update(environnement.parametres_securite(os.environ, DEBUG))

# Dossier des sauvegardes (hors du code et hors du dossier servi par le serveur web)
SAUVEGARDES_DIR = Path(os.environ.get("SAUVEGARDES_DIR") or BASE_DIR / "sauvegardes")

# Authentification
LOGIN_URL = "utilisateurs:connexion"
LOGIN_REDIRECT_URL = "accueil"
LOGOUT_REDIRECT_URL = "utilisateurs:connexion"

# E-mails (réinitialisation du mot de passe). En développement, les e-mails
# s'affichent dans le terminal ; en production, définir un vrai serveur SMTP.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "PharmaGest <noreply@pharmagest.local>")
# Serveur SMTP (utilisé seulement avec DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = environnement.booleen(os.environ.get("EMAIL_USE_TLS"), defaut=True)

# Les messages Django prennent les classes d'alerte Bootstrap
MESSAGE_TAGS = {messages.ERROR: "danger"}
