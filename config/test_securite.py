"""Tests de sécurité transversaux (cahier des charges, section 8.1)."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from config import environnement
from utilisateurs.models import JournalAudit
from utilisateurs.outils_tests import HASH_RAPIDE, MDP, creer_utilisateur

RACINE = Path(settings.BASE_DIR)
DOSSIERS_IGNORES = {".venv", "node_modules", "staticfiles", "media", "sauvegardes", "__pycache__", ".git"}

# Routes volontairement accessibles sans connexion
PUBLIQUES = {
    "utilisateurs/connexion/",
    "utilisateurs/deconnexion/",
    "utilisateurs/mot-de-passe/oublie/",
    "utilisateurs/mot-de-passe/oublie/envoye/",
    "utilisateurs/mot-de-passe/reinitialiser/<uidb64>/<token>/",
    "utilisateurs/mot-de-passe/reinitialiser/termine/",
}
# Accessibles à tout utilisateur connecté, sans permission particulière
CONNECTES = {"", "utilisateurs/mot-de-passe/changer/"}


def routes(patterns=None, prefixe=""):
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for motif in patterns:
        if isinstance(motif, URLResolver):
            yield from routes(motif.url_patterns, prefixe + str(motif.pattern))
        elif isinstance(motif, URLPattern):
            yield prefixe + str(motif.pattern)


def routes_de_l_application():
    return sorted(r for r in routes() if not r.startswith("admin/") and "<path:" not in r)


def url_reelle(route):
    return "/" + re.sub(r"<(?:\w+:)?\w+>", "1", route)


def fichiers(extension):
    for chemin in RACINE.rglob(f"*{extension}"):
        if not (set(chemin.relative_to(RACINE).parts) & DOSSIERS_IGNORES):
            yield chemin


class ProtectionDeToutesLesVuesTests(TestCase):
    """RG11 : aucune vue de l'application n'est accessible sans autorisation."""

    def test_le_parcours_des_routes_est_complet(self):
        liste = routes_de_l_application()
        self.assertGreater(len(liste), 60)
        for attendue in ("ventes/caisse/valider/", "stock/inventaire/", "rapports/pdf/ventes/"):
            self.assertIn(attendue, liste)

    def test_visiteur_anonyme_ne_voit_aucune_page_protegee(self):
        for route in routes_de_l_application():
            if route in PUBLIQUES:
                continue
            for methode in ("get", "post"):
                with self.subTest(route=route, methode=methode):
                    reponse = getattr(self.client, methode)(url_reelle(route))
                    if methode == "get" and reponse.status_code == 405:
                        continue   # vue réservée aux requêtes POST : rien n'est affiché
                    self.assertEqual(reponse.status_code, 302, f"{route} accessible sans connexion")
                    self.assertTrue(reponse["Location"].startswith(reverse("utilisateurs:connexion")), route)

    def test_utilisateur_sans_role_interdit_partout(self):
        self.client.force_login(creer_utilisateur("sans_role"))
        for route in routes_de_l_application():
            if route in PUBLIQUES or route in CONNECTES:
                continue
            for methode in ("get", "post"):
                with self.subTest(route=route, methode=methode):
                    reponse = getattr(self.client, methode)(url_reelle(route))
                    self.assertIn(reponse.status_code, (403, 405),
                                  f"{route} ({methode}) accessible sans permission")

    @override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
    def test_aucune_route_ne_plante(self):
        """Parcours en administrateur : jamais d'erreur serveur (500)."""
        admin = get_user_model().objects.create(username="root", is_superuser=True, is_staff=True)
        self.client.force_login(admin)
        for route in routes_de_l_application():
            if "deconnexion" in route:
                continue
            with self.subTest(route=route):
                reponse = self.client.get(url_reelle(route))
                self.assertLess(reponse.status_code, 500, route)

    def test_pas_de_page_publique_inattendue(self):
        """La liste des routes publiques est exactement celle prévue."""
        self.assertEqual(
            {r for r in PUBLIQUES if r in routes_de_l_application()}, PUBLIQUES)


class CsrfEtCodeSurTests(SimpleTestCase):
    def test_tous_les_formulaires_post_ont_un_jeton_csrf(self):
        trouves = 0
        for chemin in fichiers(".html"):
            texte = chemin.read_text(encoding="utf-8")
            for formulaire in re.finditer(r'<form[^>]*method="post"[^>]*>(.*?)</form>', texte, re.S | re.I):
                trouves += 1
                self.assertIn("{% csrf_token %}", formulaire.group(1),
                              f"Formulaire POST sans csrf_token dans {chemin.relative_to(RACINE)}")
        self.assertGreater(trouves, 30)

    def test_aucun_formulaire_get_ne_modifie_des_donnees(self):
        for chemin in fichiers(".html"):
            texte = chemin.read_text(encoding="utf-8")
            for balise in re.findall(r"<form[^>]*>", texte, re.I):
                if "method" not in balise.lower():
                    self.fail(f"Formulaire sans méthode explicite dans {chemin.relative_to(RACINE)}")

    def test_middleware_csrf_actif(self):
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.clickjacking.XFrameOptionsMiddleware", settings.MIDDLEWARE)

    def test_constructions_dangereuses_absentes_du_code(self):
        interdits = {
            "csrf_exempt": r"csrf_exempt",
            "mark_safe": r"mark_safe",
            "SQL brut (.raw)": r"\.raw\(",
            "SQL brut (.extra)": r"\.extra\(",
            "curseur SQL": r"connection\.cursor\(",
            "eval": r"\beval\(",
            "exec": r"\bexec\(",
            "os.system": r"os\.system\(",
            "pickle": r"\bpickle\b",
        }
        for chemin in fichiers(".py"):
            relatif = chemin.relative_to(RACINE)
            if "migrations" in relatif.parts or chemin.name.startswith("test") or chemin.name == "outils_tests.py":
                continue
            code = chemin.read_text(encoding="utf-8")
            for nom, motif in interdits.items():
                self.assertIsNone(re.search(motif, code), f"{nom} trouvé dans {relatif}")

    def test_aucun_filtre_safe_dans_les_gabarits(self):
        for chemin in fichiers(".html"):
            texte = chemin.read_text(encoding="utf-8")
            self.assertNotIn("|safe", texte, chemin.name)
            self.assertNotIn("autoescape off", texte, chemin.name)

    def test_le_fichier_secret_et_les_sauvegardes_ne_sont_pas_versionnes(self):
        ignore = (RACINE / ".gitignore").read_text(encoding="utf-8")
        for attendu in (".env", "db.sqlite3", "sauvegardes/", ".venv/", "media/"):
            self.assertIn(attendu, ignore)
        self.assertTrue((RACINE / ".env.example").is_file())
        exemple = (RACINE / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(exemple, r"DB_PASSWORD=\S+")   # aucun mot de passe réel dans l'exemple

    def test_secrets_non_codes_en_dur(self):
        code = (RACINE / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("os.environ", code)
        self.assertNotRegex(code, r"SECRET_KEY\s*=\s*[\"']")


class EnvironnementTests(SimpleTestCase):
    CLE = "une-cle-secrete-de-test-tres-longue-1234567890abcdef"

    def test_mode_debug_par_defaut_en_developpement(self):
        self.assertTrue(environnement.mode_debug({}))
        self.assertFalse(environnement.mode_debug({"DJANGO_DEBUG": "False"}))
        self.assertFalse(environnement.mode_debug({"DJANGO_DEBUG": "0"}))
        self.assertTrue(environnement.mode_debug({"DJANGO_DEBUG": "True"}))

    def test_cle_secrete_obligatoire_en_production(self):
        with self.assertRaises(ImproperlyConfigured):
            environnement.cle_secrete({}, debug=False)
        with self.assertRaises(ImproperlyConfigured):
            environnement.cle_secrete({"DJANGO_SECRET_KEY": environnement.CLE_PAR_DEFAUT}, debug=False)
        with self.assertRaises(ImproperlyConfigured):
            environnement.cle_secrete({"DJANGO_SECRET_KEY": "trop-courte"}, debug=False)
        self.assertEqual(environnement.cle_secrete({"DJANGO_SECRET_KEY": self.CLE}, debug=False), self.CLE)

    def test_cle_de_developpement_acceptee_en_debug(self):
        self.assertEqual(environnement.cle_secrete({}, debug=True), environnement.CLE_PAR_DEFAUT)

    def test_hotes_obligatoires_en_production(self):
        with self.assertRaises(ImproperlyConfigured):
            environnement.hotes_autorises({}, debug=False)
        self.assertEqual(
            environnement.hotes_autorises({"DJANGO_ALLOWED_HOSTS": "a.mg, b.mg"}, debug=False), ["a.mg", "b.mg"])
        self.assertEqual(environnement.hotes_autorises({}, debug=True), [])

    def test_base_sqlite_par_defaut(self):
        base = environnement.configuration_base({}, Path("/projet"))
        self.assertEqual(base["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(Path(base["default"]["NAME"]), Path("/projet/db.sqlite3"))

    def test_base_postgresql(self):
        env = {"DB_ENGINE": "postgresql", "DB_NAME": "pharmagest", "DB_USER": "pg", "DB_PASSWORD": "secret",
               "DB_HOST": "db.interne", "DB_PORT": "6543"}
        base = environnement.configuration_base(env, Path("/projet"))["default"]
        self.assertEqual(base["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((base["NAME"], base["USER"], base["HOST"], base["PORT"]),
                         ("pharmagest", "pg", "db.interne", "6543"))
        self.assertEqual(base["PASSWORD"], "secret")
        self.assertGreater(base["CONN_MAX_AGE"], 0)

    def test_postgresql_valeurs_par_defaut_et_variables_manquantes(self):
        env = {"DB_ENGINE": "postgres", "DB_NAME": "p", "DB_USER": "u", "DB_PASSWORD": "x"}
        base = environnement.configuration_base(env, Path("/p"))["default"]
        self.assertEqual((base["HOST"], base["PORT"]), ("localhost", "5432"))
        with self.assertRaisesMessage(ImproperlyConfigured, "DB_PASSWORD"):
            environnement.configuration_base({"DB_ENGINE": "postgresql", "DB_NAME": "p", "DB_USER": "u"}, Path("/p"))

    def test_moteur_inconnu_refuse(self):
        with self.assertRaises(ImproperlyConfigured):
            environnement.configuration_base({"DB_ENGINE": "oracle"}, Path("/p"))

    def test_securite_https_en_production(self):
        reglages = environnement.parametres_securite({}, debug=False)
        self.assertTrue(reglages["SECURE_SSL_REDIRECT"])
        self.assertTrue(reglages["SESSION_COOKIE_SECURE"])
        self.assertTrue(reglages["CSRF_COOKIE_SECURE"])
        self.assertGreaterEqual(reglages["SECURE_HSTS_SECONDS"], 31536000)
        self.assertEqual(reglages["X_FRAME_OPTIONS"], "DENY")
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", reglages)

    def test_securite_derriere_un_proxy(self):
        reglages = environnement.parametres_securite({"DJANGO_PROXY_HTTPS": "True"}, debug=False)
        self.assertEqual(reglages["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_rien_d_impose_en_developpement(self):
        self.assertEqual(environnement.parametres_securite({}, debug=True), {})


class ErreursEtJournalTests(TestCase):
    @override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
    def test_echec_de_connexion_journalise_sans_mot_de_passe(self):
        creer_utilisateur("alice")
        self.client.post(reverse("utilisateurs:connexion"), {"username": "alice", "password": "mot-de-passe-faux-123"})
        entree = JournalAudit.objects.get(action="Échec de connexion")
        self.assertEqual(entree.objet, "alice")
        self.assertIsNone(entree.utilisateur)
        self.assertNotIn("mot-de-passe-faux-123", entree.detail + entree.objet)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_page_404_comprehensible(self):
        reponse = self.client.get("/cette-page-n-existe-pas/")
        self.assertContains(reponse, "Page introuvable", status_code=404)
        self.assertNotContains(reponse, "Traceback", status_code=404)

    def test_page_403_comprehensible(self):
        self.client.force_login(creer_utilisateur("sans_role"))
        self.assertContains(self.client.get(reverse("stock:inventaire")), "Accès interdit", status_code=403)

    def test_page_500_autonome_et_rassurante(self):
        page = render_to_string("500.html")
        self.assertIn("Une erreur est survenue", page)
        self.assertIn("Aucune donnée n'a été perdue", page)

    def test_en_tetes_de_securite(self):
        self.client.force_login(creer_utilisateur("sans_role"))
        reponse = self.client.get(reverse("accueil"))
        self.assertEqual(reponse["X-Frame-Options"], "DENY")
        self.assertEqual(reponse["X-Content-Type-Options"], "nosniff")

    @override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
    def test_deconnexion_exige_post(self):
        self.client.force_login(creer_utilisateur("alice"))
        self.assertEqual(self.client.get(reverse("utilisateurs:deconnexion")).status_code, 405)

    @override_settings(PASSWORD_HASHERS=HASH_RAPIDE)
    def test_redirection_de_connexion_refuse_les_sites_externes(self):
        u = creer_utilisateur("alice")
        u.set_password(MDP)
        u.save()
        reponse = self.client.post(
            reverse("utilisateurs:connexion") + "?next=https://site-pirate.example/",
            {"username": "alice", "password": MDP})
        self.assertRedirects(reponse, reverse("accueil"))
