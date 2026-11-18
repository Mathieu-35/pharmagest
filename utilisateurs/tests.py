from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from medicaments.models import Categorie, Medicament
from utilisateurs import roles
from utilisateurs.models import JournalAudit

User = get_user_model()
HASH_RAPIDE = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MDP = "Mot-de-passe-solide-42"


def utilisateur(nom, *roles_, **extra):
    u = User.objects.create(username=nom, **extra)
    u.set_password(MDP)
    u.save()
    for role in roles_:
        u.groups.add(Group.objects.get(name=role))
    return u


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class RolesTests(TestCase):
    def test_cinq_roles_crees(self):
        noms = set(Group.objects.values_list("name", flat=True))
        self.assertEqual(noms, {
            roles.ADMINISTRATEUR, roles.PHARMACIEN, roles.GESTIONNAIRE_STOCK,
            roles.CAISSIER, roles.RESPONSABLE_GESTION,
        })

    def groupe(self, nom):
        return Group.objects.get(name=nom)

    def a_perm(self, nom_groupe, perm):
        app, code = perm.split(".")
        return self.groupe(nom_groupe).permissions.filter(
            content_type__app_label=app, codename=code).exists()

    def test_caissier(self):
        self.assertTrue(self.a_perm(roles.CAISSIER, "ventes.add_vente"))
        self.assertTrue(self.a_perm(roles.CAISSIER, "medicaments.view_medicament"))
        self.assertFalse(self.a_perm(roles.CAISSIER, "medicaments.add_medicament"))
        self.assertFalse(self.a_perm(roles.CAISSIER, "achats.add_commandeachat"))
        self.assertFalse(self.a_perm(roles.CAISSIER, "auth.view_user"))

    def test_gestionnaire_de_stock(self):
        self.assertTrue(self.a_perm(roles.GESTIONNAIRE_STOCK, "achats.add_commandeachat"))
        self.assertTrue(self.a_perm(roles.GESTIONNAIRE_STOCK, "fournisseurs.change_fournisseur"))
        self.assertFalse(self.a_perm(roles.GESTIONNAIRE_STOCK, "ventes.add_vente"))
        self.assertFalse(self.a_perm(roles.GESTIONNAIRE_STOCK, "medicaments.change_medicament"))

    def test_pharmacien(self):
        self.assertTrue(self.a_perm(roles.PHARMACIEN, "medicaments.add_medicament"))
        self.assertTrue(self.a_perm(roles.PHARMACIEN, "ventes.view_vente"))
        self.assertFalse(self.a_perm(roles.PHARMACIEN, "ventes.add_vente"))

    def test_responsable_gestion_en_lecture_seule(self):
        permissions = self.groupe(roles.RESPONSABLE_GESTION).permissions
        self.assertTrue(permissions.exists())
        # Aucune permission d'ajout, de modification ou de suppression de données...
        self.assertFalse(permissions.exclude(codename__startswith="view_").exclude(
            content_type__app_label="rapports").exists())
        # ... seulement la consultation des statistiques et la génération des rapports
        self.assertEqual(
            set(permissions.filter(content_type__app_label="rapports").values_list("codename", flat=True)),
            {roles.TABLEAU, roles.FINANCES, roles.RAPPORTS})

    def test_administrateur_gere_les_comptes_mais_pas_le_journal(self):
        self.assertTrue(self.a_perm(roles.ADMINISTRATEUR, "auth.add_user"))
        self.assertTrue(self.a_perm(roles.ADMINISTRATEUR, "utilisateurs.view_journalaudit"))
        self.assertFalse(self.a_perm(roles.ADMINISTRATEUR, "utilisateurs.change_journalaudit"))
        self.assertFalse(self.a_perm(roles.ADMINISTRATEUR, "utilisateurs.delete_journalaudit"))

    def test_creation_des_roles_sans_ecraser_les_ajustements(self):
        groupe = self.groupe(roles.CAISSIER)
        avant = groupe.permissions.count()
        groupe.permissions.clear()
        roles.creer_roles()
        self.assertEqual(self.groupe(roles.CAISSIER).permissions.count(), 0)
        self.assertGreater(avant, 0)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class ProtectionDesVuesTests(TestCase):
    """RG11 : chaque vue refuse les utilisateurs non autorisés."""

    def setUp(self):
        categorie = Categorie.objects.create(nom="Antalgiques")
        self.med = Medicament.objects.create(
            nom_commercial="Para", categorie=categorie, prix_achat=1, prix_vente=2)
        self.categorie = categorie
        self.urls = [
            reverse("accueil"),
            reverse("medicaments:liste"),
            reverse("medicaments:creer"),
            reverse("medicaments:detail", args=[self.med.pk]),
            reverse("medicaments:modifier", args=[self.med.pk]),
            reverse("medicaments:supprimer", args=[self.med.pk]),
            reverse("medicaments:categories"),
            reverse("medicaments:categorie_creer"),
            reverse("medicaments:categorie_modifier", args=[categorie.pk]),
            reverse("medicaments:categorie_supprimer", args=[categorie.pk]),
            reverse("utilisateurs:liste"),
            reverse("utilisateurs:creer"),
            reverse("utilisateurs:modifier", args=[1]),
            reverse("utilisateurs:journal"),
            reverse("utilisateurs:mot_de_passe_changer"),
        ]

    def test_visiteur_anonyme_renvoye_vers_la_connexion(self):
        for url in self.urls:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r.url.startswith(reverse("utilisateurs:connexion")), r.url)

    def test_post_anonyme_refuse(self):
        r = self.client.post(reverse("medicaments:supprimer", args=[self.med.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Medicament.objects.filter(pk=self.med.pk).exists())

    def test_utilisateur_sans_role_interdit_partout(self):
        self.client.force_login(utilisateur("sans_role"))
        interdits = [u for u in self.urls
                     if u not in (reverse("accueil"), reverse("utilisateurs:mot_de_passe_changer"))]
        for url in interdits:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_acces_interdit_affiche_une_page_lisible(self):
        self.client.force_login(utilisateur("sans_role"))
        r = self.client.get(reverse("medicaments:liste"))
        self.assertContains(r, "Accès interdit", status_code=403)

    def test_caissier_consulte_mais_ne_modifie_pas_le_catalogue(self):
        self.client.force_login(utilisateur("caisse", roles.CAISSIER))
        self.assertEqual(self.client.get(reverse("medicaments:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("medicaments:detail", args=[self.med.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("medicaments:creer")).status_code, 403)
        self.assertEqual(self.client.get(reverse("medicaments:modifier", args=[self.med.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("medicaments:supprimer", args=[self.med.pk])).status_code, 403)
        self.assertTrue(Medicament.objects.filter(pk=self.med.pk).exists())
        self.assertEqual(self.client.get(reverse("utilisateurs:liste")).status_code, 403)

    def test_gestionnaire_de_stock_ne_supprime_pas_de_medicament(self):
        self.client.force_login(utilisateur("stock", roles.GESTIONNAIRE_STOCK))
        self.assertEqual(self.client.get(reverse("medicaments:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("medicaments:supprimer", args=[self.med.pk])).status_code, 403)

    def test_responsable_de_gestion_en_lecture_seule(self):
        self.client.force_login(utilisateur("gestion", roles.RESPONSABLE_GESTION))
        self.assertEqual(self.client.get(reverse("medicaments:liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("medicaments:creer")).status_code, 403)

    def test_pharmacien_gere_le_catalogue_mais_pas_les_comptes(self):
        self.client.force_login(utilisateur("pharma", roles.PHARMACIEN))
        self.assertEqual(self.client.get(reverse("medicaments:creer")).status_code, 200)
        self.assertEqual(self.client.get(reverse("medicaments:categorie_creer")).status_code, 200)
        self.assertEqual(self.client.get(reverse("utilisateurs:liste")).status_code, 403)

    def test_roles_cumules(self):
        self.client.force_login(utilisateur("double", roles.CAISSIER, roles.GESTIONNAIRE_STOCK))
        self.assertEqual(self.client.get(reverse("medicaments:liste")).status_code, 200)

    def test_menu_masque_les_liens_non_autorises(self):
        self.client.force_login(utilisateur("caisse", roles.CAISSIER))
        r = self.client.get(reverse("accueil"))
        self.assertContains(r, "Médicaments")
        self.assertNotContains(r, f'href="{reverse("utilisateurs:liste")}"')
        self.assertNotContains(r, f'href="{reverse("utilisateurs:journal")}"')


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class ConnexionTests(TestCase):
    def test_connexion_reussie(self):
        utilisateur("alice")
        r = self.client.post(reverse("utilisateurs:connexion"), {"username": "alice", "password": MDP})
        self.assertRedirects(r, reverse("accueil"))
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)

    def test_mauvais_mot_de_passe(self):
        utilisateur("alice")
        r = self.client.post(reverse("utilisateurs:connexion"), {"username": "alice", "password": "faux"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 302)

    def test_compte_desactive_refuse(self):
        utilisateur("inactif", is_active=False)
        r = self.client.post(reverse("utilisateurs:connexion"), {"username": "inactif", "password": MDP})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 302)

    def test_deconnexion(self):
        self.client.force_login(utilisateur("alice"))
        self.client.post(reverse("utilisateurs:deconnexion"))
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 302)

    def test_retour_vers_la_page_demandee(self):
        utilisateur("alice", roles.CAISSIER)
        url = reverse("medicaments:liste")
        r = self.client.post(f"{reverse('utilisateurs:connexion')}?next={url}",
                             {"username": "alice", "password": MDP})
        self.assertRedirects(r, url)

    def test_mot_de_passe_jamais_stocke_en_clair(self):
        u = utilisateur("alice")
        self.assertNotEqual(u.password, MDP)
        self.assertNotIn(MDP, u.password)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class GestionDesComptesTests(TestCase):
    def setUp(self):
        self.admin = utilisateur("chef", roles.ADMINISTRATEUR, is_staff=True)
        self.client.force_login(self.admin)

    def donnees(self, **extra):
        d = {"username": "nouveau", "first_name": "Nou", "last_name": "Veau",
             "email": "n@example.com", "is_active": "on",
             "password1": MDP, "password2": MDP,
             "groups": [Group.objects.get(name=roles.CAISSIER).pk]}
        d.update(extra)
        return d

    def test_creation_de_compte_avec_role(self):
        r = self.client.post(reverse("utilisateurs:creer"), self.donnees())
        self.assertRedirects(r, reverse("utilisateurs:liste"))
        u = User.objects.get(username="nouveau")
        self.assertTrue(u.check_password(MDP))
        self.assertEqual([g.name for g in u.groups.all()], [roles.CAISSIER])
        self.assertFalse(u.is_staff)

    def test_connexion_avec_le_nouveau_compte(self):
        self.client.post(reverse("utilisateurs:creer"), self.donnees())
        self.client.logout()
        r = self.client.post(reverse("utilisateurs:connexion"), {"username": "nouveau", "password": MDP})
        self.assertRedirects(r, reverse("accueil"))

    def test_role_administrateur_donne_acces_a_ladministration(self):
        groupe = Group.objects.get(name=roles.ADMINISTRATEUR).pk
        self.client.post(reverse("utilisateurs:creer"), self.donnees(groups=[groupe]))
        self.assertTrue(User.objects.get(username="nouveau").is_staff)

    def test_mots_de_passe_differents_refuses(self):
        r = self.client.post(reverse("utilisateurs:creer"), self.donnees(password2="autre"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="nouveau").exists())

    def test_mot_de_passe_trop_simple_refuse(self):
        r = self.client.post(reverse("utilisateurs:creer"), self.donnees(password1="123", password2="123"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="nouveau").exists())

    def test_mot_de_passe_obligatoire_a_la_creation(self):
        r = self.client.post(reverse("utilisateurs:creer"), self.donnees(password1="", password2=""))
        self.assertEqual(r.status_code, 200)

    def test_modification_des_roles(self):
        u = utilisateur("bob", roles.CAISSIER)
        d = self.donnees(username="bob", password1="", password2="",
                         groups=[Group.objects.get(name=roles.PHARMACIEN).pk])
        self.client.post(reverse("utilisateurs:modifier", args=[u.pk]), d)
        self.assertEqual([g.name for g in u.groups.all()], [roles.PHARMACIEN])
        self.assertTrue(User.objects.get(pk=u.pk).check_password(MDP))  # mot de passe inchangé

    def test_activation_et_desactivation(self):
        u = utilisateur("bob")
        self.client.post(reverse("utilisateurs:activation", args=[u.pk]))
        u.refresh_from_db()
        self.assertFalse(u.is_active)
        self.client.post(reverse("utilisateurs:activation", args=[u.pk]))
        u.refresh_from_db()
        self.assertTrue(u.is_active)

    def test_activation_exige_post(self):
        u = utilisateur("bob")
        self.assertEqual(self.client.get(reverse("utilisateurs:activation", args=[u.pk])).status_code, 405)

    def test_on_ne_peut_pas_desactiver_son_propre_compte(self):
        self.client.post(reverse("utilisateurs:activation", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_on_ne_peut_pas_se_retirer_le_role_administrateur(self):
        d = self.donnees(username="chef", password1="", password2="",
                         groups=[Group.objects.get(name=roles.CAISSIER).pk])
        r = self.client.post(reverse("utilisateurs:modifier", args=[self.admin.pk]), d)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.admin.groups.filter(name=roles.ADMINISTRATEUR).exists())

    def test_un_administrateur_ne_touche_pas_a_un_super_utilisateur(self):
        root = User.objects.create(username="root", is_superuser=True, is_staff=True)
        self.assertEqual(self.client.get(reverse("utilisateurs:modifier", args=[root.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("utilisateurs:activation", args=[root.pk])).status_code, 403)

    def test_recherche_de_comptes(self):
        utilisateur("zoe")
        r = self.client.get(reverse("utilisateurs:liste"), {"q": "zoe"})
        self.assertEqual([u.username for u in r.context["page"]], ["zoe"])

    def test_un_non_administrateur_ne_peut_pas_creer_de_compte(self):
        self.client.force_login(utilisateur("pharma", roles.PHARMACIEN))
        r = self.client.post(reverse("utilisateurs:creer"), self.donnees())
        self.assertEqual(r.status_code, 403)
        self.assertFalse(User.objects.filter(username="nouveau").exists())


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class MotDePasseTests(TestCase):
    NOUVEAU = "Autre-mot-de-passe-91"

    def test_changement_du_mot_de_passe(self):
        u = utilisateur("alice")
        self.client.force_login(u)
        r = self.client.post(reverse("utilisateurs:mot_de_passe_changer"), {
            "old_password": MDP, "new_password1": self.NOUVEAU, "new_password2": self.NOUVEAU})
        self.assertRedirects(r, reverse("accueil"))
        u.refresh_from_db()
        self.assertTrue(u.check_password(self.NOUVEAU))

    def test_changement_refuse_si_ancien_mot_de_passe_faux(self):
        u = utilisateur("alice")
        self.client.force_login(u)
        r = self.client.post(reverse("utilisateurs:mot_de_passe_changer"), {
            "old_password": "faux", "new_password1": self.NOUVEAU, "new_password2": self.NOUVEAU})
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password(MDP))

    def test_reinitialisation_par_e_mail(self):
        u = utilisateur("alice", email="alice@example.com")
        self.client.post(reverse("utilisateurs:reinitialisation"), {"email": "alice@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        lien = next(l for l in mail.outbox[0].body.splitlines() if "/mot-de-passe/reinitialiser/" in l)
        chemin = lien.split("testserver", 1)[1]
        r = self.client.get(chemin, follow=True)  # Django redirige vers l'URL de saisie
        self.assertContains(r, "Nouveau mot de passe")
        r = self.client.post(r.request["PATH_INFO"], {
            "new_password1": self.NOUVEAU, "new_password2": self.NOUVEAU})
        self.assertRedirects(r, reverse("utilisateurs:reinitialisation_terminee"))
        u.refresh_from_db()
        self.assertTrue(u.check_password(self.NOUVEAU))

    def test_lien_de_reinitialisation_invalide(self):
        r = self.client.get(reverse("utilisateurs:reinitialisation_confirmer", args=["abc", "faux-jeton"]))
        self.assertContains(r, "invalide ou a expiré")

    def test_email_inconnu_ne_revele_rien(self):
        r = self.client.post(reverse("utilisateurs:reinitialisation"), {"email": "inconnu@example.com"})
        self.assertRedirects(r, reverse("utilisateurs:reinitialisation_envoyee"))
        self.assertEqual(len(mail.outbox), 0)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
class JournalAuditTests(TestCase):
    def test_connexion_et_deconnexion_journalisees(self):
        utilisateur("alice")
        self.client.post(reverse("utilisateurs:connexion"), {"username": "alice", "password": MDP})
        self.client.post(reverse("utilisateurs:deconnexion"))
        actions = list(JournalAudit.objects.values_list("action", flat=True))
        self.assertIn("Connexion", actions)
        self.assertIn("Déconnexion", actions)
        self.assertEqual(JournalAudit.objects.get(action="Connexion").utilisateur.username, "alice")

    def test_operations_sur_les_medicaments_journalisees(self):
        pharma = utilisateur("pharma", roles.PHARMACIEN)
        self.client.force_login(pharma)
        categorie = Categorie.objects.create(nom="Antalgiques")
        r = self.client.post(reverse("medicaments:creer"), {
            "nom_commercial": "Para", "categorie": categorie.pk, "forme": "comprime",
            "prix_achat": "1", "prix_vente": "2", "seuil_alerte": "5", "statut": "actif"})
        self.assertEqual(r.status_code, 302)
        entree = JournalAudit.objects.get(action="Médicament ajouté")
        self.assertEqual(entree.utilisateur, pharma)
        self.assertIsNotNone(entree.date)

    def test_creation_de_compte_journalisee(self):
        admin = utilisateur("chef", roles.ADMINISTRATEUR)
        self.client.force_login(admin)
        self.client.post(reverse("utilisateurs:creer"), {
            "username": "nouveau", "is_active": "on", "password1": MDP, "password2": MDP})
        self.assertTrue(JournalAudit.objects.filter(action="Compte créé", objet="nouveau", utilisateur=admin).exists())

    def test_consultation_reservee_aux_autorises(self):
        self.client.force_login(utilisateur("caisse", roles.CAISSIER))
        self.assertEqual(self.client.get(reverse("utilisateurs:journal")).status_code, 403)
        self.client.force_login(utilisateur("chef", roles.ADMINISTRATEUR))
        self.assertEqual(self.client.get(reverse("utilisateurs:journal")).status_code, 200)
