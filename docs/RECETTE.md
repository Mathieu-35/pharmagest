# PharmaGest — Recette (version 1.0)

Ce document rend compte de la validation du projet par rapport au cahier des charges.

## 1. Les 11 scénarios du cahier des charges (section 9)

Chaque scénario est un test automatisé dans [`config/test_recette.py`](../config/test_recette.py). Il passe par les pages de l'application (requêtes HTTP), avec le rôle qui effectue réellement l'opération, et vérifie le résultat attendu.

| N° | Test du cahier des charges | Résultat attendu | Test automatisé | Résultat |
|---|---|---|---|---|
| 1 | Ajouter un médicament avec photo | Médicament enregistré et photo affichée | `test_01_ajouter_un_medicament_avec_photo` | ✅ Réussi |
| 2 | Modifier un médicament | Informations mises à jour | `test_02_modifier_un_medicament` | ✅ Réussi |
| 3 | Supprimer ou archiver un médicament | Historique protégé | `test_03_supprimer_ou_archiver_un_medicament` | ✅ Réussi |
| 4 | Réceptionner un achat de 20 unités | Stock augmenté de 20 une seule fois | `test_04_receptionner_un_achat_de_20_unites` | ✅ Réussi |
| 5 | Vendre 3 unités | Stock diminué de 3 une seule fois | `test_05_vendre_3_unites` | ✅ Réussi |
| 6 | Vendre plus que le stock disponible | Vente refusée | `test_06_vendre_plus_que_le_stock_disponible` | ✅ Réussi |
| 7 | Vendre un lot périmé | Vente refusée | `test_07_vendre_un_lot_perime` | ✅ Réussi |
| 8 | Tenter un accès sans permission | Accès interdit | `test_08_tenter_un_acces_sans_permission` | ✅ Réussi |
| 9 | Générer un reçu PDF | Document lisible avec les bons totaux | `test_09_generer_un_recu_pdf` | ✅ Réussi |
| 10 | Enregistrer deux validations simultanées | Aucune sortie de stock en double ni stock négatif | `test_10_deux_validations_simultanees` | ✅ Réussi |
| 11 | Restaurer une sauvegarde | Données récupérées correctement | `test_11_restaurer_une_sauvegarde` | ✅ Réussi |

Précisions :
- **Scénario 10** : deux fils d'exécution lancent leur validation au même instant sur le même stock (deux ventes différentes de 6 unités sur un stock de 10, puis deux envois du même formulaire). Résultat : une seule vente enregistrée, jamais de stock négatif ni de double sortie. Ce scénario a été répété 8 fois de suite sans échec. Sur SQLite, la validation perdante est relancée automatiquement après un court délai ; sur PostgreSQL, le verrouillage des lignes joue ce rôle.
- **Scénario 11** a aussi été vérifié sur une copie de la base réelle de développement : comptes, mots de passe, rôles, prix et stocks identiques après restauration.
- **Scénario 9** : le texte du PDF est relu par le test (numéro, lignes, prix et totaux exacts). Le rendu visuel (mise en page) doit être contrôlé à l'œil lors de la mise en service.

## 2. Tests automatisés

| Application | Tests | Couverture principale |
|---|---|---|
| `medicaments` | 41 | Modèles, contraintes (code-barres, prix), formulaires, photos (type, taille), liste (recherche, filtre, tri, pagination), suppression ou archivage |
| `fournisseurs` | 16 | CRUD, recherche, désactivation, historique, permissions |
| `achats` | 40 | Commandes, statuts, réception (une seule fois, partielle, lots), atomicité, permissions |
| `stock` | 41 | Lots, FEFO, stock disponible, ruptures, péremptions, blocage, mouvements, inventaire |
| `ventes` | 93 | Caisse, règles de vente, FEFO, double validation, paiements, retours, annulation, concurrence |
| `clients` | 6 | CRUD, historique, permissions |
| `utilisateurs` | 46 | Connexion, rôles et permissions, comptes, mots de passe, réinitialisation, journal d'audit |
| `rapports` | 63 | Chiffre d'affaires, encaissements, marge, alertes, tableau de bord par rôle, documents et rapports PDF |
| `config` | 66 | Sécurité de toutes les routes, CSRF, configuration de production, sauvegarde et restauration, recette |
| **Total** | **412** | Tous réussis |

Le cahier des charges demande que les tests couvrent les modèles, les formulaires, les permissions, les calculs et les opérations de stock : c'est le cas (voir le tableau).

Relancer tous les tests :

```bash
python manage.py test
```

Relancer seulement la recette :

```bash
python manage.py test config.test_recette
```

## 3. Revue de sécurité (cahier des charges, section 8.1)

| Point | Contrôle | État |
|---|---|---|
| Protection CSRF | Middleware actif ; test qui parcourt tous les gabarits et vérifie le jeton de chaque formulaire POST | ✅ |
| Validation serveur des données | Formulaires et services refusent quantités et prix invalides ; testé hors interface | ✅ |
| Permission sur chaque vue | Test qui parcourt **toutes les routes** : visiteur anonyme → redirigé vers la connexion ; utilisateur sans rôle → 403 ; administrateur → aucune erreur serveur | ✅ |
| Images : type et taille | JPEG, PNG, WEBP, 2 Mo maximum ; fichier non image refusé | ✅ |
| Accès directs interdits | Les actions modifiant des données n'acceptent que POST ; redirection de connexion limitée au site | ✅ |
| HTTPS en production | Redirection, cookies sécurisés, HSTS ; `check --deploy` : 2 avertissements facultatifs (HSTS sous-domaines et préchargement) | ✅ |
| Secrets en variables d'environnement | `.env` non versionné ; refus de démarrer en production sans clé secrète ni hôtes | ✅ |
| Sauvegardes protégées et testées | Archive vérifiée par empreintes, accès restreint au propriétaire, `--essai`, restauration atomique | ✅ |
| Journalisation des opérations sensibles | Journal d'audit non modifiable, échecs de connexion inclus (sans mot de passe) | ✅ |
| Doubles ventes et doubles réceptions | Jetons uniques, décrément conditionnel du stock, relance après conflit | ✅ |
| Injections et code dangereux | Test qui cherche SQL brut, `csrf_exempt`, `mark_safe`, `eval`, `exec`, `|safe` : aucun | ✅ |
| Pages d'erreur compréhensibles | Pages 403, 404 et 500 en français, sans détail technique | ✅ |

## 4. Règles de gestion (section 5)

| Règle | Vérifiée par |
|---|---|
| RG01 Identifiant unique | Tests des modèles |
| RG02 Code-barres unique | Tests des modèles et formulaires |
| RG03 Prix et quantités validés côté serveur | Tests des formulaires et des services |
| RG04 Une commande ne modifie pas le stock | Tests des achats, scénario 4 |
| RG05 Une réception augmente le stock une seule fois | Scénario 4, tests de jeton |
| RG06 Une vente diminue le stock une seule fois | Scénarios 5 et 10 |
| RG07 Le stock ne peut pas devenir négatif | Scénarios 6 et 10, contraintes de base |
| RG08 Lots périmés ou bloqués exclus de la vente | Scénario 7, tests des lots |
| RG09 Auteur, date et historique | Tests du journal et des mouvements |
| RG10 Ventes et achats validés non supprimés sans traçabilité | Protection des clés étrangères, retours et annulations |
| RG11 Accès selon les droits | Scénario 8, test de toutes les routes |
| RG12 Prix conservés dans les documents historiques | Tests des lignes de vente et du chiffre d'affaires |

## 5. Livrables (section 11)

| Livrable | Emplacement |
|---|---|
| Code source complet | Dépôt GitHub |
| Base de données et migrations | Dossiers `*/migrations/` |
| Modèles et relations | `*/models.py`, `docs/conception.md` |
| Pages HTML, CSS et Bootstrap | `templates/`, `*/templates/`, `static/` |
| Formulaires CRUD avec photos | Application « Médicaments » |
| Modules d'achats, de ventes et de stock | Applications `achats`, `ventes`, `stock` |
| Utilisateurs et permissions | Application `utilisateurs` |
| Rapports PDF et tableau de bord | Application `rapports` |
| Jeu de données fictives | `python manage.py charger_donnees` |
| Tests automatisés | `*/tests.py`, `*/test_*.py` |
| Manuel d'installation et de configuration | [`INSTALLATION.md`](INSTALLATION.md) |
| Guide d'utilisation | [`GUIDE_UTILISATION.md`](GUIDE_UTILISATION.md) |
| Dossier de conception (MCD, MLD, UML) | [`conception.md`](conception.md) |

## 6. Limites connues et points à valider avant l'exploitation réelle

- **Réglementation** : le logiciel ne remplace pas les obligations réglementaires. Les mentions légales et fiscales, les règles de délivrance, la conservation des documents et la protection des données personnelles doivent être vérifiées pour Madagascar (cahier des charges, section 12). Les mentions légales se saisissent dans `.env` (`PHARMACIE_MENTIONS_LEGALES`).
- **PostgreSQL, gunicorn et nginx** : configuration prévue et documentée, mais **non testée de bout en bout** dans l'environnement de développement (SQLite). À essayer sur un serveur de test avant la mise en service.
- **Mise en page des PDF** : vérifiée par calcul (aucun tableau ne dépasse la page) et par relecture du texte, mais pas visuellement. À contrôler à l'œil sur un exemplaire imprimé.
- **Affichage hors connexion** : Bootstrap est chargé depuis un CDN ; sans Internet, la mise en forme disparaît.
- **Paiements électroniques** : le logiciel n'est connecté à aucun opérateur ; la vérification d'une transaction mobile money est manuelle (référence saisie par l'utilisateur).
- **Droits des rôles** : les permissions détaillées de chaque rôle sont une interprétation de la section 3 du cahier des charges ; elles sont ajustables dans l'administration Django.
- **Monnaie** : « Ar » par défaut, modifiable avec `DEVISE`.
- **Hors périmètre** (section 2) : diagnostic, prescription, application mobile native, comptabilité générale.
