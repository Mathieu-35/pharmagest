# PharmaGest — Dossier de conception

Basé sur les sections 3, 4, 5 et 6 du cahier des charges. Les schémas utilisent Mermaid (affichés directement par GitHub). Les clés étrangères et contraintes définitives seront fixées au Sprint 2.

## 1. Cas d'utilisation (acteurs et fonctions)

```mermaid
flowchart LR
    Admin([Administrateur])
    Pharm([Pharmacien responsable])
    Stock([Gestionnaire de stock])
    Caisse([Caissier])
    Gest([Responsable de gestion])

    Admin --- U1[Gérer utilisateurs et rôles]
    Admin --- U2[Gérer médicaments et catégories]
    Pharm --- U2
    Pharm --- U3[Contrôler lots et péremptions]
    Stock --- U4[Gérer fournisseurs et achats]
    Stock --- U5[Réceptionner et inventorier]
    Caisse --- U6[Enregistrer ventes et paiements]
    Caisse --- U7[Imprimer reçus]
    Caisse --- U8[Enregistrer retours autorisés]
    Gest --- U9[Consulter statistiques et rapports]
```

## 2. MCD — Modèle conceptuel de données

```mermaid
erDiagram
    CATEGORIE ||--o{ MEDICAMENT : regroupe
    MEDICAMENT ||--o{ LOT_STOCK : possede
    FOURNISSEUR ||--o{ COMMANDE_ACHAT : recoit
    COMMANDE_ACHAT ||--|{ LIGNE_ACHAT : contient
    MEDICAMENT ||--o{ LIGNE_ACHAT : concerne
    COMMANDE_ACHAT ||--o{ RECEPTION_ACHAT : "est receptionnee par"
    RECEPTION_ACHAT ||--o{ LOT_STOCK : cree
    LOT_STOCK ||--o{ MOUVEMENT_STOCK : trace
    CLIENT |o--o{ VENTE : effectue
    VENTE ||--|{ LIGNE_VENTE : contient
    MEDICAMENT ||--o{ LIGNE_VENTE : concerne
    LOT_STOCK ||--o{ LIGNE_VENTE : "delivre depuis"
    VENTE ||--o{ PAIEMENT : "est reglee par"
    VENTE ||--o{ RETOUR_VENTE : "peut etre retournee"
    UTILISATEUR ||--o{ COMMANDE_ACHAT : cree
    UTILISATEUR ||--o{ VENTE : realise
    UTILISATEUR ||--o{ JOURNAL_AUDIT : genere

    CATEGORIE {
        int id PK
        string nom
        text description
    }
    MEDICAMENT {
        int id PK
        string nom_commercial
        string denomination_generique
        string forme
        string dosage
        string laboratoire
        string code_barres UK
        image photo
        decimal prix_achat
        decimal prix_vente
        int seuil_alerte
        string statut
        datetime date_creation
    }
    LOT_STOCK {
        int id PK
        string numero_lot
        date date_peremption
        int quantite_recue
        int quantite_restante
        bool bloque
    }
    FOURNISSEUR {
        int id PK
        string nom
        string adresse
        string telephone
        string email
        string numero_fiscal
        string contact_principal
        bool actif
    }
    COMMANDE_ACHAT {
        int id PK
        string statut
        datetime date_commande
    }
    LIGNE_ACHAT {
        int id PK
        int quantite
        decimal prix_achat
    }
    RECEPTION_ACHAT {
        int id PK
        datetime date_reception
    }
    MOUVEMENT_STOCK {
        int id PK
        string type
        int quantite
        datetime date
        string motif
    }
    CLIENT {
        int id PK
        string nom
        string telephone
        bool actif
    }
    VENTE {
        int id PK
        datetime date
        uuid jeton UK
        string statut
    }
    LIGNE_VENTE {
        int id PK
        int quantite
        decimal prix_applique
    }
    PAIEMENT {
        int id PK
        string mode
        decimal montant
        string statut
    }
    RETOUR_VENTE {
        int id PK
        int quantite
        string motif
        bool remis_en_stock
        datetime date
    }
    UTILISATEUR {
        int id PK
        string identifiant
        string role
        bool actif
    }
    JOURNAL_AUDIT {
        int id PK
        string action
        datetime date
        text detail
    }
```

## 3. MLD — Modèle logique (tables relationnelles)

Clés primaires soulignées par `PK`, clés étrangères par `FK`.

| Table | Colonnes |
|---|---|
| `categorie` | id PK, nom, description |
| `medicament` | id PK, nom_commercial, denomination_generique, categorie_id FK, forme, dosage, laboratoire, code_barres (unique, nullable), photo, prix_achat, prix_vente, seuil_alerte, statut, date_creation |
| `fournisseur` | id PK, nom, adresse, telephone, email, numero_fiscal, contact_principal, actif |
| `client` | id PK, nom, telephone, actif |
| `commande_achat` | id PK, fournisseur_id FK, utilisateur_id FK, statut, date_commande ; le montant total est calculé depuis les lignes |
| `ligne_achat` | id PK, commande_id FK, medicament_id FK, quantite, prix_achat |
| `reception_achat` | id PK, commande_id FK, utilisateur_id FK, date_reception |
| `ligne_reception` | id PK, reception_id FK, ligne_achat_id FK, lot_id FK, quantite |
| `lot_stock` | id PK, medicament_id FK, numero_lot, date_peremption, quantite_recue, quantite_restante, bloque (unique : medicament + numero_lot) |
| `mouvement_stock` | id PK, lot_id FK, utilisateur_id FK, type (entrée, sortie, retour, correction), quantite, date, motif |
| `vente` | id PK, client_id FK (nullable), utilisateur_id FK, jeton (unique, anti double validation), date, statut ; le total est calculé depuis les lignes |
| `ligne_vente` | id PK, vente_id FK, medicament_id FK, lot_id FK, quantite, prix_applique |
| `paiement` | id PK, vente_id FK, mode, montant, statut |
| `retour_vente` | id PK, ligne_vente_id FK, utilisateur_id FK, quantite, motif, remis_en_stock, date |
| `utilisateur` | table `auth_user` de Django + groupes (rôles) et permissions |
| `journal_audit` | id PK, utilisateur_id FK, action, detail, date |

### Contraintes issues des règles de gestion

| Règle | Traduction |
|---|---|
| RG01 | Clé primaire automatique sur `medicament` |
| RG02 | `code_barres` unique lorsqu'il est renseigné |
| RG03 | Prix ≥ 0, quantités > 0, validés côté serveur |
| RG04, RG05 | Le stock n'augmente que par une `reception_achat` validée, une seule fois |
| RG06, RG07 | Vente validée = sorties dans une transaction atomique, `quantite_restante` ≥ 0 |
| RG08 | Lots périmés ou `bloque` exclus de la vente (FEFO sur `date_peremption`) |
| RG09, RG10 | `journal_audit` et `mouvement_stock` ; pas de suppression des ventes ni achats validés |
| RG11 | Permissions Django vérifiées sur chaque vue |
| RG12 | `ligne_vente.prix_applique` conserve le prix au moment de la vente |

## 4. Architecture applicative (MVT Django)

| Application | Contenu prévu |
|---|---|
| `utilisateurs` | Authentification, rôles, permissions, journal d'audit |
| `medicaments` | Catégories, médicaments, photos |
| `fournisseurs` | Fournisseurs |
| `clients` | Clients |
| `achats` | Commandes, lignes, réceptions |
| `stock` | Lots, mouvements, inventaire, alertes |
| `ventes` | Caisse, ventes, paiements, retours |
| `rapports` | Tableau de bord, PDF ReportLab |

## 5. Cycle de vie d'une vente (diagramme de séquence)

```mermaid
sequenceDiagram
    actor C as Caissier
    participant V as Vue vente
    participant S as Stock (lots FEFO)
    participant B as Base de données
    C->>V: Ajoute médicament et quantité
    V->>S: Cherche lots valides (non périmés, non bloqués)
    S-->>V: Lot le plus proche de la péremption
    C->>V: Confirme et choisit le paiement
    V->>B: Transaction atomique
    B->>B: Vérifie stock suffisant
    B->>B: Crée vente, lignes (prix figé), paiement
    B->>B: Sortie de stock + mouvement + audit
    B-->>V: Succès
    V-->>C: Reçu
```

## 6. Rôles et permissions (Sprint 4)

Les rôles de la section 3 du cahier des charges sont des groupes Django, créés automatiquement à la migration. Un utilisateur peut cumuler plusieurs rôles si l'administrateur les lui accorde. Les permissions détaillées ci-dessous sont un point de départ que l'administrateur peut ajuster dans l'administration Django.

| Rôle | Permissions initiales |
|---|---|
| Administrateur | Toutes les permissions de l'application, gestion des comptes et rôles, accès à l'administration Django ; journal d'audit en lecture seule |
| Pharmacien responsable | Médicaments et catégories (tout) ; lots (lecture, ajout, modification) ; consultation des achats, ventes, fournisseurs, clients ; enregistrement des retours |
| Gestionnaire de stock | Fournisseurs, commandes, réceptions, lots (lecture, ajout, modification) ; mouvements de stock (lecture, ajout) ; consultation des médicaments |
| Caissier | Ventes et lignes de vente (lecture, ajout) ; paiements et clients (lecture, ajout, modification) ; consultation des médicaments et lots |
| Responsable de gestion | Consultation seule des médicaments, stocks, achats, ventes, fournisseurs et clients |

Chaque vue vérifie la permission correspondante (RG11) : visiteur non connecté → page de connexion ; utilisateur connecté sans permission → page « Accès interdit » (403).

Le journal d'audit (RG09) enregistre : connexions et déconnexions, création / modification / activation / désactivation des comptes, changements de mot de passe, ajout / modification / archivage / suppression des médicaments et des catégories.
