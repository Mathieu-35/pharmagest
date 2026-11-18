# PharmaGest — Guide d'utilisation

Ce guide s'adresse au personnel de la pharmacie. Chaque personne voit uniquement les menus correspondant à son ou ses rôles.

## 1. Se connecter

1. Ouvrez l'adresse de l'application dans votre navigateur.
2. Saisissez votre nom d'utilisateur et votre mot de passe, puis **Se connecter**.
3. En haut à droite : votre nom, **Mot de passe** (changer votre mot de passe) et **Déconnexion**.

**Mot de passe oublié ?** Sur la page de connexion, cliquez sur « Mot de passe oublié ? », saisissez l'adresse e-mail de votre compte et suivez le lien reçu par e-mail. Si votre compte n'a pas d'adresse e-mail, demandez à un administrateur de vous donner un nouveau mot de passe (menu *Utilisateurs → Modifier*).

Un compte désactivé ne peut plus se connecter. Après une période d'inactivité ou une restauration de sauvegarde, il faut se reconnecter.

## 2. Qui peut faire quoi

| Rôle | Ce que la personne peut faire |
|---|---|
| **Administrateur** | Tout, y compris la gestion des comptes, des rôles et la consultation du journal |
| **Pharmacien responsable** | Gérer les médicaments et catégories ; contrôler les lots (bloquer / débloquer) ; consulter achats, ventes, fournisseurs, clients ; enregistrer les retours et annulations de vente ; statistiques et rapports |
| **Gestionnaire de stock** | Gérer fournisseurs, commandes d'achat, réceptions et inventaires ; consulter le catalogue ; rapports de stock, d'achats et de péremptions |
| **Caissier** | Encaisser les ventes, enregistrer et confirmer les paiements, gérer les clients, imprimer reçus et factures ; consulter le catalogue et les lots |
| **Responsable de gestion** | Consulter (sans modifier) le catalogue, le stock, les achats et les ventes ; statistiques, recettes et rapports |

Un utilisateur peut cumuler plusieurs rôles si l'administrateur les lui accorde. Si vous voyez « Accès interdit », votre rôle ne permet pas cette action : adressez-vous à l'administrateur.

## 3. Le tableau de bord (page d'accueil)

Il se met à jour tout seul à partir des données réelles. Selon votre rôle, vous voyez :

- **Stock et alertes** : médicaments actifs, **stocks faibles** (en dessous du seuil d'alerte), **ruptures**, **péremptions proches** (30 jours par défaut), lots périmés encore en stock, avec la liste des produits concernés.
- **Ventes** : nombre et montant des ventes du jour, produits les plus vendus.
- **Chiffres de la période** (rôles financiers) : chiffre d'affaires, encaissements, marge commerciale brute, achats, ventes par jour. Choisissez la période avec « Du » et « Au » puis **Appliquer la période**.

À ne pas confondre :
- le **chiffre d'affaires** = ventes validées, nettes des retours ;
- les **encaissements** = paiements réellement confirmés (un paiement mobile money « en attente » n'est pas encaissé) ;
- la **marge commerciale brute** = chiffre d'affaires − coût d'achat des produits vendus. Ce **n'est pas un bénéfice net** : salaires, loyer et taxes ne sont pas déduits.

## 4. Le catalogue : catégories et médicaments

### Catégories (menu *Catégories*)
Ajoutez, modifiez et recherchez les catégories (antalgiques, vitamines…). Une catégorie utilisée par des médicaments ne peut pas être supprimée.

### Médicaments (menu *Médicaments*)
- **Rechercher** par nom ou code-barres, **filtrer** par catégorie, **trier** (nom, prix, stock), parcourir par pages.
- **Ajouter un médicament** : nom commercial, catégorie, forme, dosage, laboratoire, code-barres (unique), prix d'achat, prix de vente, seuil d'alerte, et une **photo** facultative (JPEG, PNG ou WEBP, 2 Mo maximum).
- **Modifier** : mêmes champs.
- **Supprimer** : une page de confirmation s'affiche. Si le médicament n'a **aucun historique**, il est supprimé. S'il a déjà des lots, des achats ou des ventes, il est **archivé** (il n'est plus vendu ni commandé, mais l'historique est conservé). Pour le réactiver, modifiez-le et remettez le statut « Actif » (filtre *Statut → Archivé* pour le retrouver).
- La liste montre le **stock disponible** : seuls les lots ni périmés ni bloqués comptent. Un badge « Rupture » ou orange signale un stock bas.

## 5. Approvisionner la pharmacie

### Fournisseurs (menu *Fournisseurs*)
Ajoutez et modifiez les fiches (adresse, téléphone, e-mail, numéro fiscal, contact). **Désactivez** un fournisseur plutôt que de le supprimer : son historique d'achats et les montants commandés et réceptionnés restent consultables sur sa fiche.

### Commande d'achat (menu *Achats*)
1. **Nouvelle commande** : choisissez le fournisseur, ajoutez les médicaments, quantités et prix d'achat. Le total se calcule automatiquement. La commande est enregistrée en **brouillon**.
2. **Modifier** tant qu'elle est en brouillon, puis **Valider la commande** (confirmation demandée). Elle passe à « Commandée ».
3. **Annuler** est possible tant qu'aucune marchandise n'a été reçue.

> Une commande **n'augmente pas le stock**. Le stock n'augmente qu'à la réception.

### Réception (bouton *Réceptionner*)
1. Pour chaque ligne, saisissez la **quantité réellement reçue** (0 si rien n'est arrivé), le **numéro de lot** et la **date de péremption**.
2. **Valider la réception** : le lot est créé, le stock augmente, et un mouvement d'entrée est enregistré.
3. Une réception **partielle** est possible : la commande passe à « Partiellement réceptionnée » ; réceptionnez le reste plus tard.
4. Si vous cliquez deux fois par erreur, le stock n'augmente **qu'une seule fois**.

On ne peut pas recevoir plus que la quantité commandée, ni un lot déjà périmé. Les **bons** (bon de commande, bon de réception) s'impriment en PDF depuis la page de la commande.

## 6. Le stock

Menu **Stock** :

- **Stock disponible** : par médicament, avec filtres *Ruptures de stock* et *Sous le seuil d'alerte*.
- **Lots et péremptions** : filtres *En stock*, *Péremption proche*, *Périmés*, *Bloqués*, *Épuisés*. Un lot **périmé ou bloqué n'est jamais proposé à la vente**. Le pharmacien peut **Bloquer** (par exemple en cas de rappel) ou **Débloquer** un lot.
- **Mouvements** : l'historique de toutes les entrées, sorties, retours et corrections, avec l'auteur et la date.
- **Inventaire physique** (gestionnaire de stock) : comptez les lots en rayon, saisissez les quantités trouvées, indiquez le motif, puis **Enregistrer l'inventaire**. Seuls les écarts sont corrigés, chacun avec un mouvement « correction » dans l'historique.

## 7. Vendre (menu *Ventes → Caisse*)

1. **Rechercher** un médicament par son nom, ou **scanner son code-barres** : un code exact ajoute directement 1 unité au panier.
2. Dans les résultats, indiquez la **quantité** et, si besoin, un **lot précis**. Par défaut, le lot qui expire en premier est utilisé automatiquement (méthode FEFO), sur plusieurs lots si nécessaire. Le panier affiche les lots qui seront délivrés.
3. Ajustez les quantités (bouton **OK**) ou retirez une ligne (**×**). Le prix est celui du médicament : il n'est pas modifiable.
4. Choisissez un **client** (facultatif : « Vente comptoir » par défaut) et le **mode de paiement**.
5. **Confirmer la vente**. Le stock diminue, le reçu s'affiche.

Ce qui est refusé automatiquement : quantité nulle ou négative, quantité supérieure au stock disponible, lot périmé ou bloqué, validation en double.

### Paiements
- **Espèces** : encaissé tout de suite.
- **Mobile money** ou autre moyen : le paiement reste **« en attente »** tant que vous n'avez pas vérifié la transaction. Sur la page de la vente, saisissez la **référence de la transaction** puis **Confirmer**. S'il n'a pas abouti, cliquez sur **Échoué**.
- Pour un paiement partiel ou un solde, utilisez **Ajouter un paiement** sur la page de la vente.

### Reçu et facture
Sur la page de la vente : **Reçu PDF** et **Facture PDF** (les informations de la pharmacie, le numéro, les lignes, les quantités, les prix et le total y figurent).

### Historique (menu *Ventes → Historique des ventes*)
Recherche par numéro ou client, filtre par statut et par dates.

## 8. Retours et annulations

Une vente validée n'est **jamais supprimée** : on la corrige par une opération tracée.

- **Enregistrer un retour** (pharmacien ou administrateur) : sur la page de la vente, indiquez pour chaque ligne la quantité retournée, cochez *Remettre en stock* si le produit y est éligible, et saisissez le **motif**. Le montant à rembourser est calculé au prix de la vente. La remise en stock est refusée si le lot est périmé ou bloqué.
- **Annuler la vente** : tout ce qui n'a pas encore été retourné est retourné ; la vente passe à « Annulée » et reste consultable.

## 9. Clients (menu *Clients*)

Ajoutez et modifiez les clients (nom, téléphone, adresse), activez ou désactivez leur compte, et consultez l'**historique de leurs ventes** sur leur fiche. N'enregistrez que les informations strictement nécessaires. Une vente au comptoir n'exige aucun client.

## 10. Rapports et documents PDF

Menu **Rapports** (selon le rôle) :

| Rapport | Contenu |
|---|---|
| Stock | Disponible, seuil, quantité bloquée ou périmée et état de chaque médicament |
| Produits proches de la péremption | Lots périmés encore en stock et lots qui expirent bientôt |
| Ventes (période) | Liste des ventes, chiffre d'affaires, encaissements, marge brute |
| Achats (période) | Commandes passées et marchandises réceptionnées |

Les PDF s'ouvrent dans un nouvel onglet ; utilisez l'impression ou l'enregistrement de votre navigateur.

## 11. Administration (administrateur)

### Utilisateurs (menu *Utilisateurs*)
- **Ajouter un utilisateur** : identifiant, nom, e-mail, mot de passe et **rôles** (cochez un ou plusieurs rôles).
- **Modifier** les informations et les rôles ; laissez le mot de passe vide pour ne pas le changer.
- **Désactiver / Activer** un compte au lieu de le supprimer.
- Vous ne pouvez pas désactiver votre propre compte ni vous retirer le rôle d'administrateur.

### Journal (menu *Journal*)
Il enregistre, avec l'auteur et la date : connexions et échecs de connexion, comptes créés ou modifiés, changements de mot de passe, opérations sur le catalogue, commandes, réceptions, ventes, retours, paiements, blocages de lots et inventaires. Il ne peut pas être modifié.

### Sauvegardes
Voir `docs/INSTALLATION.md`, section 5 : `python manage.py sauvegarder`, `python manage.py restaurer … --essai` puis `--confirmer`. **Faites des sauvegardes régulièrement** et testez-les.

## 12. Questions fréquentes

**Pourquoi un médicament n'apparaît-il pas à la caisse ?** Il est archivé, ou son stock disponible est nul (lots périmés, bloqués ou épuisés). Regardez *Stock → Lots et péremptions*.

**Pourquoi le stock n'a-t-il pas augmenté après ma commande ?** Une commande n'ajoute rien : il faut la **réceptionner**.

**Pourquoi mon paiement mobile money n'est-il pas dans les encaissements ?** Il est « en attente » : confirmez-le avec la référence de la transaction.

**J'ai fait une erreur sur une vente.** Demandez à un pharmacien ou à un administrateur d'enregistrer un retour ou d'annuler la vente.

**« Une autre opération est en cours : réessayez ».** Deux personnes ont validé au même instant. Rien n'a été modifié : recommencez simplement.

**Ce logiciel remplace-t-il les contrôles professionnels ?** Non. La présence d'un médicament dans la base ne signifie pas qu'il peut être délivré : les règles de délivrance, les prescriptions nécessaires et les contrôles du pharmacien restent obligatoires.
