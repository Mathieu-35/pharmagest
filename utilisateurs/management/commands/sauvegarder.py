from django.core.management.base import BaseCommand, CommandError

from config import sauvegarde


class Command(BaseCommand):
    help = "Crée une sauvegarde (archive ZIP) de la base de données et des photos, puis la vérifie."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dossier", help="Dossier de destination (par défaut : SAUVEGARDES_DIR, « sauvegardes/ »).")

    def handle(self, *args, **options):
        try:
            chemin, manifest = sauvegarde.creer_sauvegarde(options["dossier"])
        except sauvegarde.ErreurSauvegarde as erreur:
            raise CommandError(str(erreur))
        taille = chemin.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde créée et vérifiée : {chemin}"))
        self.stdout.write(
            f"  {manifest['objets']} enregistrements, {len(manifest['media'])} photo(s), {taille:.0f} Ko.")
        self.stdout.write(
            "  Conservez ce fichier dans un endroit protégé : il contient les comptes et les données.")
