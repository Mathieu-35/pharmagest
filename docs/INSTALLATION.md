# PharmaGest — Manuel d'installation et de configuration

Ce manuel explique comment installer PharmaGest sur un poste de développement ou de test, puis le mettre en production, le configurer, le sauvegarder et le restaurer.

## 1. Prérequis

| Élément | Version |
|---|---|
| Python | 3.12 ou plus récent |
| Git | pour récupérer le projet |
| Navigateur moderne | Chrome, Edge ou Firefox |
| Accès à Internet | **nécessaire à l'affichage** : la mise en page (Bootstrap 5) est chargée depuis un réseau de diffusion (CDN). Hors connexion, l'application fonctionne mais sans mise en forme. |
| PostgreSQL | recommandé en production (SQLite suffit pour tester) |

## 2. Installation (poste de développement ou de test)

```bash
git clone https://github.com/Mathieu-35/pharmagest.git
cd pharmagest
python -m venv .venv
```

Activer l'environnement virtuel :

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate
```

Installer les dépendances, créer la base et le compte administrateur :

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

Au moment de `createsuperuser`, l'adresse e-mail est facultative ; si vous en saisissez une, elle doit être valide (`nom@exemple.com`). Le mot de passe ne s'affiche pas pendant la saisie.

Jeu de données fictives (facultatif, pour essayer l'application) :

```bash
python manage.py charger_donnees
```

Lancer l'application :

```bash
python manage.py runserver
```

Ouvrez ensuite http://127.0.0.1:8000/ et connectez-vous avec le compte créé. Les cinq rôles (Administrateur, Pharmacien responsable, Gestionnaire de stock, Caissier, Responsable de gestion) sont créés automatiquement par `migrate`. Créez les comptes du personnel depuis le menu **Utilisateurs**.

Lancer les tests automatisés :

```bash
python manage.py test
```

## 3. Configuration

La configuration se fait par des **variables d'environnement**, lues dans un fichier `.env` à la racine du projet. Copiez le modèle puis adaptez-le :

```bash
# Windows (PowerShell)
Copy-Item .env.example .env
# Linux / macOS
cp .env.example .env
```

Le fichier `.env` contient des secrets : il n'est **jamais** publié sur GitHub (déjà ignoré par git).

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_DEBUG` | `True` en développement, **`False` en production** | `True` |
| `DJANGO_SECRET_KEY` | Clé secrète (obligatoire en production, 32 caractères minimum) | clé de développement |
| `DJANGO_ALLOWED_HOSTS` | Noms de domaine autorisés, séparés par des virgules (obligatoire en production) | vide |
| `DJANGO_PROXY_HTTPS` | `True` si nginx (ou autre) gère le HTTPS et transmet `X-Forwarded-Proto` | `False` |
| `DJANGO_SSL_REDIRECT` | Redirige tout vers HTTPS en production | `True` |
| `DJANGO_HSTS_SECONDS` | Durée HSTS en secondes en production | `31536000` |
| `DJANGO_HSTS_SOUS_DOMAINES` | Étend HSTS aux sous-domaines (seulement si tous sont en HTTPS) | `False` |
| `DB_ENGINE` | `sqlite` ou `postgresql` | `sqlite` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Connexion PostgreSQL | `localhost`, `5432` |
| `SAUVEGARDES_DIR` | Dossier des sauvegardes | `sauvegardes/` du projet |
| `JOURS_ALERTE_PEREMPTION` | Jours avant péremption pour signaler un lot « proche » | `30` |
| `PHARMACIE_NOM`, `PHARMACIE_ADRESSE`, `PHARMACIE_TELEPHONE`, `PHARMACIE_EMAIL`, `PHARMACIE_NUMERO_FISCAL` | Informations imprimées sur les documents PDF | `PharmaGest`, vide |
| `PHARMACIE_MENTIONS_LEGALES` | Mentions légales et fiscales imprimées en pied de page | vide |
| `DEVISE` | Devise affichée sur les documents | `Ar` |
| `DJANGO_EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DJANGO_DEFAULT_FROM_EMAIL` | Envoi des e-mails de réinitialisation de mot de passe | affichage dans le terminal |

**À faire avant l'exploitation réelle** : renseigner les informations de la pharmacie et surtout les **mentions légales et fiscales applicables à Madagascar** (ou au territoire d'exploitation). Elles ne sont pas fournies par le logiciel. Faites aussi vérifier par un professionnel les exigences locales sur la délivrance des médicaments, la traçabilité des lots, les factures, les données personnelles et la conservation des documents (cahier des charges, section 12).

Générer une clé secrète :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 4. Mise en production

Exemple pour un serveur Linux avec PostgreSQL, gunicorn et nginx. Adaptez les chemins et les noms.

### 4.1 Base de données PostgreSQL

```sql
CREATE USER pharmagest WITH PASSWORD 'un-mot-de-passe-solide';
CREATE DATABASE pharmagest OWNER pharmagest ENCODING 'UTF8';
```

### 4.2 Application

```bash
git clone https://github.com/Mathieu-35/pharmagest.git /srv/pharmagest
cd /srv/pharmagest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-production.txt
```

Fichier `.env` de production (exemple) :

```ini
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<clé générée, 50 caractères>
DJANGO_ALLOWED_HOSTS=pharmacie.exemple.mg
DJANGO_PROXY_HTTPS=True
DB_ENGINE=postgresql
DB_NAME=pharmagest
DB_USER=pharmagest
DB_PASSWORD=un-mot-de-passe-solide
SAUVEGARDES_DIR=/var/backups/pharmagest
PHARMACIE_NOM=Pharmacie Exemple
```

Si `DJANGO_DEBUG=False` mais que la clé secrète ou les hôtes manquent, l'application **refuse de démarrer** : c'est voulu.

Préparer la base et les fichiers statiques :

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

Vérification de sécurité de Django :

```bash
python manage.py check --deploy
```

Il ne reste que deux avertissements facultatifs : `security.W005` (HSTS sur les sous-domaines) et `security.W021` (préchargement HSTS). Activez-les seulement si vous maîtrisez tous les sous-domaines de votre nom de domaine.

### 4.3 Serveur d'application (gunicorn)

```bash
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

À lancer comme service (par exemple avec systemd) pour qu'il redémarre automatiquement.

### 4.4 Serveur web (nginx) et HTTPS

En production, Django ne sert ni les fichiers statiques ni les photos : c'est le serveur web qui s'en charge. Exemple de configuration :

```nginx
server {
    listen 443 ssl;
    server_name pharmacie.exemple.mg;
    # ssl_certificate et ssl_certificate_key : certificat HTTPS (par exemple Let's Encrypt)

    client_max_body_size 3m;            # photos de 2 Mo maximum

    location /static/ { alias /srv/pharmagest/staticfiles/; }
    location /media/  { alias /srv/pharmagest/media/; }   # photos des médicaments

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}

server {
    listen 80;
    server_name pharmacie.exemple.mg;
    return 301 https://$host$request_uri;
}
```

Le dossier `media/` ne doit contenir que des images : ne lui donnez jamais le droit d'exécuter des scripts.

> **Important** : la configuration PostgreSQL, gunicorn et nginx décrite ici suit les pratiques courantes de Django mais **n'a pas pu être testée de bout en bout** dans l'environnement de développement (pas de serveur PostgreSQL ni Linux). Faites un essai complet sur un serveur de test avant la mise en service, en suivant la recette (`docs/RECETTE.md`).

### 4.5 Passer de SQLite à PostgreSQL en conservant les données

1. Sur l'ancienne installation (SQLite) : `python manage.py sauvegarder`.
2. Sur le nouveau serveur : configurer `.env` pour PostgreSQL, puis `python manage.py migrate`.
3. Copier l'archive et tester : `python manage.py restaurer archive.zip --essai`.
4. Restaurer pour de bon : `python manage.py restaurer archive.zip --confirmer`.

## 5. Sauvegarde et restauration

### 5.1 Faire une sauvegarde

```bash
python manage.py sauvegarder
```

Crée dans `SAUVEGARDES_DIR` une archive `pharmagest-AAAAMMJJ-HHMMSS.zip` qui contient **toutes les données** (utilisateurs, rôles, médicaments, lots, achats, ventes, journal) et **les photos**. L'archive est vérifiée aussitôt (empreintes SHA-256). L'accès au fichier est limité à son propriétaire.

L'archive contient les comptes et les mots de passe (hachés) : **conservez-la dans un endroit protégé**, sur un autre disque ou un autre site que le serveur, et ne la publiez jamais (le dossier `sauvegardes/` est exclu de git).

Planification quotidienne (exemples) :

```bash
# Linux : tous les jours à 20 h (crontab -e)
0 20 * * * cd /srv/pharmagest && .venv/bin/python manage.py sauvegarder
```

```powershell
# Windows : tâche planifiée quotidienne à 20 h
schtasks /create /tn "PharmaGest sauvegarde" /sc daily /st 20:00 /tr "E:\Projet pharmacie\.venv\Scripts\python.exe E:\Projet pharmacie\manage.py sauvegarder"
```

### 5.2 Tester une sauvegarde (à faire régulièrement)

```bash
python manage.py restaurer pharmagest-20261118-200000.zip --essai
```

L'essai vérifie l'archive, mène la restauration jusqu'au bout puis l'**annule** : aucune donnée n'est modifiée. Une sauvegarde qu'on n'a jamais testée ne garantit rien : faites cet essai au moins une fois par mois.

### 5.3 Restaurer

```bash
python manage.py restaurer pharmagest-20261118-200000.zip --confirmer
```

- Toutes les données actuelles sont **remplacées** par celles de l'archive : la commande exige `--confirmer`.
- Avant de remplacer quoi que ce soit, l'état actuel est sauvegardé dans `avant-restauration-….zip`.
- L'archive est contrôlée avant toute modification ; la restauration se fait en une seule transaction : en cas d'erreur, rien n'est modifié.
- Le nombre d'enregistrements restaurés est comparé à celui de l'archive.
- Après une restauration, **tous les utilisateurs doivent se reconnecter** (les sessions ne sont pas sauvegardées).

## 6. Mise à jour de l'application

```bash
python manage.py sauvegarder          # toujours sauvegarder avant
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput   # en production
```

Puis redémarrer le service (gunicorn).

## 7. Dépannage

| Problème | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'django'` | L'environnement virtuel n'est pas activé : `.venv\Scripts\Activate.ps1` |
| « l'exécution de scripts est désactivée » (PowerShell) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `That port is already in use` | `python manage.py runserver 8001` |
| `ImproperlyConfigured : DJANGO_SECRET_KEY…` | Définir la clé secrète dans `.env` (obligatoire hors développement) |
| `ImproperlyConfigured : DJANGO_ALLOWED_HOSTS…` | Définir les noms de domaine dans `.env` |
| Pages sans mise en forme | Pas d'accès à Internet (Bootstrap chargé depuis un CDN) |
| Les photos ne s'affichent pas en production | nginx doit servir `/media/` (voir 4.4) |
| L'e-mail « mot de passe oublié » n'arrive pas | Configurer `EMAIL_*` ; en développement, le message s'affiche dans le terminal du serveur |
| « Une autre opération est en cours : réessayez » | Deux validations simultanées : l'opération a été refusée sans rien modifier ; recommencer |
