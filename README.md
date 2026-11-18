# PharmaGest

Application web de gestion d'une pharmacie, développée avec **Django**, **SQLite** (PostgreSQL en production), **Bootstrap 5** et **ReportLab**.

Elle couvre : médicaments et photos, catégories, fournisseurs, clients, achats et réceptions, lots et péremptions (méthode FEFO), stock et inventaire, caisse, paiements, retours, tableau de bord, reçus, factures et rapports PDF, utilisateurs, rôles et permissions, journal d'audit, sauvegarde et restauration.

## Documentation

| Document | Contenu |
|---|---|
| [`docs/cahier-des-charges.docx`](docs/cahier-des-charges.docx) | Cahier des charges |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Installation, configuration, production, sauvegarde et restauration |
| [`docs/GUIDE_UTILISATION.md`](docs/GUIDE_UTILISATION.md) | Guide d'utilisation pour le personnel |
| [`docs/conception.md`](docs/conception.md) | Dossier de conception : MCD, MLD, UML |
| [`docs/RECETTE.md`](docs/RECETTE.md) | Recette des scénarios du cahier des charges, revue de sécurité |
| [`docs/SCRUM.md`](docs/SCRUM.md) | Plan des 8 sprints |

## Démarrage rapide

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Linux / macOS : source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Puis http://127.0.0.1:8000/. Jeu de données fictives : `python manage.py charger_donnees`. Tests : `python manage.py test`.

## Méthode

Projet mené en 8 sprints d'une semaine ; un sprint ne démarrait qu'après la fin du précédent.

| Sprint | Thème |
|---|---|
| 1 | Analyse, installation et architecture |
| 2 | Modèles, base de données et administration |
| 3 | CRUD médicaments, catégories et photos |
| 4 | Authentification, utilisateurs et permissions |
| 5 | Fournisseurs, achats, lots et stocks |
| 6 | Ventes, caisse, paiements et retours |
| 7 | Tableau de bord, PDF et rapports |
| 8 | Tests, sécurité, documentation et déploiement |

## Avertissement

Le logiciel ne remplace pas les obligations réglementaires d'une pharmacie réelle (délivrance, prescriptions, traçabilité, facturation, données personnelles). Voir la section 12 du cahier des charges et `docs/RECETTE.md`.
