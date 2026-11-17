# PharmaGest — Plan de sprints (Scrum)

Basé uniquement sur le cahier des charges (`cahier-des-charges.docx`) : un sprint = une semaine du planning prévisionnel (section 10).

## Règle

**On ne passe au sprint suivant qu'après avoir réalisé et validé le précédent.** Un sprint est terminé quand toutes ses tâches sont faites et que ses critères de validation (tests de la section 9 du cahier des charges) passent. Une tâche non finie reste dans le sprint en cours.

## Déroulement d'un sprint

1. **Planning** : on relit les tâches du sprint.
2. **Développement** : on réalise les tâches, avec leurs tests (Django `TestCase`).
3. **Revue** : on vérifie les critères de validation.
4. **Commit + push sur GitHub** (fait par toi) à la fin du sprint, avec le nom du sprint dans le message, par exemple `Sprint 3 : CRUD médicaments, catégories et photos`.

---

## Sprint 1 — Analyse, installation et architecture (semaine 1)

- Analyse du besoin, dossier de conception : MCD, MLD, diagrammes UML utiles
- Installation : environnement virtuel, Django, `requirements.txt`, projet `config`
- Création des applications : `utilisateurs`, `medicaments`, `fournisseurs`, `clients`, `achats`, `stock`, `ventes`, `rapports`
- Dossiers `templates/`, `static/` (css, js, images), `media/`
- Configuration par variables d'environnement (secrets), SQLite en développement, Bootstrap 5, interface en français

**Validation :** le projet démarre (`runserver`), les applications sont déclarées, la conception est relue.

## Sprint 2 — Modèles, base de données et administration (semaine 2)

- Modèles : `Categorie`, `Medicament`, `Fournisseur`, `Client`, `LotStock`, `MouvementStock`, `CommandeAchat`, `LigneAchat`, `ReceptionAchat`, `Vente`, `LigneVente`, `Paiement`, `RetourVente`, `JournalAudit`
- Contraintes : identifiant unique (RG01), code-barres unique (RG02), prix et quantités validés (RG03)
- Enregistrement dans l'administration Django
- Jeu de données fictives
- Tests des modèles

**Validation :** migrations appliquées, code-barres dupliqué refusé, données fictives chargeables.

## Sprint 3 — CRUD médicaments, catégories et photos (semaine 3)

- CRUD catégories, recherche, suppression interdite si utilisée
- CRUD médicaments avec photo (Pillow), vérification du type et de la taille de l'image
- Liste : recherche par nom ou code-barres, filtre par catégorie, tri, pagination
- Suppression uniquement si l'historique n'est pas compromis, sinon archivage
- Tests des formulaires et des vues

**Validation :** ajouter un médicament avec photo · modifier un médicament · supprimer ou archiver (historique protégé).

## Sprint 4 — Authentification, utilisateurs et permissions (semaine 4)

- Connexion / déconnexion, modification et réinitialisation du mot de passe
- Rôles : Administrateur, Pharmacien responsable, Gestionnaire de stock, Caissier, Responsable de gestion
- Création / modification des comptes, activation / désactivation
- Protection de toutes les vues selon les permissions (RG11)
- Enregistrement de l'auteur et de la date des opérations importantes (RG09, journal d'audit)
- Tests des permissions

**Validation :** tenter un accès sans permission → accès interdit.

## Sprint 5 — Fournisseurs, achats, lots et stocks (semaine 5)

- CRUD fournisseurs, recherche nom / téléphone, désactivation, historique des achats
- Commande d'achat multi-lignes, total automatique, statuts (brouillon, commandée, partiellement / entièrement réceptionnée, annulée)
- Réception totale ou partielle : création des lots (numéro, péremption), stock augmenté une seule fois (RG04, RG05)
- Mouvements de stock traçables, historique
- Stock disponible, ruptures, seuil d'alerte, inventaire physique, corrections autorisées
- Détection des produits périmés ou proches de la péremption
- Tests : réception sans doublon, stock jamais négatif

**Validation :** réceptionner un achat de 20 unités → stock +20 une seule fois.

## Sprint 6 — Ventes, caisse, paiements et retours (semaine 6)

- Interface de caisse : recherche ou code-barres, lot, quantité, sous-totaux, total
- Méthode FEFO, exclusion des lots périmés ou bloqués (RG08)
- Validation de la vente et sortie de stock dans une transaction atomique (RG06, RG07)
- Refus des quantités nulles, négatives ou supérieures au stock ; pas de double validation
- Prix appliqué conservé dans la ligne de vente (RG12)
- Paiements (espèces, mobile money confirmé après vérification du statut)
- Clients : gestion, historique des ventes, vente comptoir
- Retours et annulations par opération compensatoire, remise en stock si éligible
- Tests de concurrence et des règles de vente

**Validation :** vendre 3 unités → stock −3 une seule fois · vendre plus que le stock → refusé · vendre un lot périmé → refusé · deux validations simultanées → pas de double sortie ni stock négatif.

## Sprint 7 — Tableau de bord, PDF et rapports (semaine 7)

- Tableau de bord : médicaments actifs, ventes du jour, stocks faibles, péremptions proches (valeurs calculées), ventes et achats par période, produits les plus vendus, alertes
- Statistiques selon le rôle ; chiffre d'affaires distinct des encaissements et des bénéfices
- PDF ReportLab : reçu de vente, facture, bon de commande, bon de réception
- Rapports PDF : stock, ventes, achats, produits proches de la péremption
- Tests des calculs et des PDF

**Validation :** générer un reçu PDF → document lisible avec les bons totaux.

## Sprint 8 — Tests, sécurité, documentation et déploiement (semaine 8)

- Tests automatisés : modèles, formulaires, permissions, calculs, opérations de stock
- Sécurité : CSRF, validation serveur, secrets en variables d'environnement, HTTPS en production
- Sauvegarde et restauration de la base, testées
- Configuration de production (PostgreSQL)
- Manuel d'installation et de configuration, guide d'utilisation
- Dossier de conception final (MCD, MLD, UML)
- Recette de tous les scénarios de la section 9

**Validation :** tous les tests de la section 9 passent, dont « restaurer une sauvegarde → données récupérées ».
