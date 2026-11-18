from django.core.management.base import BaseCommand, CommandError

from config import sauvegarde


class Command(BaseCommand):
    help = (
        "Restaure une sauvegarde : REMPLACE toutes les données actuelles. "
        "Utilisez d'abord --essai pour tester sans rien modifier."
    )

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Archive créée par la commande « sauvegarder ».")
        parser.add_argument(
            "--essai", action="store_true",
            help="Teste la restauration complète puis l'annule : aucune donnée n'est modifiée.")
        parser.add_argument(
            "--confirmer", action="store_true",
            help="Confirme le remplacement des données actuelles (obligatoire hors essai).")

    def handle(self, *args, **options):
        if not options["essai"] and not options["confirmer"]:
            raise CommandError(
                "La restauration remplace toutes les données actuelles. "
                "Relancez avec --confirmer (ou --essai pour seulement tester).")
        try:
            resume = sauvegarde.restaurer(options["fichier"], essai=options["essai"])
        except sauvegarde.ErreurSauvegarde as erreur:
            raise CommandError(str(erreur))

        if resume["essai"]:
            self.stdout.write(self.style.SUCCESS(
                f"Essai réussi : {resume['objets']} enregistrements restaurables "
                f"(sauvegarde du {resume['date_sauvegarde']}). Aucune donnée modifiée."))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Restauration terminée : {resume['objets']} enregistrements et {resume['photos']} photo(s) "
            f"(sauvegarde du {resume['date_sauvegarde']})."))
        self.stdout.write(f"  Ancien état conservé dans : {resume['sauvegarde_securite']}")
