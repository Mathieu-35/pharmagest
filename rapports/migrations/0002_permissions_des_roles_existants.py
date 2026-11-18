"""Ajoute les permissions du tableau de bord et des rapports aux rôles déjà créés
(Sprints 4 à 6). Sur une base neuve, les groupes sont créés plus tard avec ces
permissions déjà incluses : cette migration ne fait alors rien."""

from django.db import migrations

PERMISSIONS = {
    "voir_tableau_de_bord": "Peut voir le tableau de bord",
    "voir_statistiques_financieres": "Peut voir le chiffre d'affaires, les encaissements et les marges",
    "generer_rapports": "Peut générer les rapports PDF",
}

PAR_ROLE = {
    "Administrateur": ["voir_tableau_de_bord", "voir_statistiques_financieres", "generer_rapports"],
    "Pharmacien responsable": ["voir_tableau_de_bord", "voir_statistiques_financieres", "generer_rapports"],
    "Gestionnaire de stock": ["voir_tableau_de_bord", "generer_rapports"],
    "Caissier": ["voir_tableau_de_bord"],
    "Responsable de gestion": ["voir_tableau_de_bord", "voir_statistiques_financieres", "generer_rapports"],
}


def ajouter_permissions(apps, schema_editor):
    base = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    type_rapport, _ = ContentType.objects.using(base).get_or_create(
        app_label="rapports", model="rapport"
    )
    permissions = {}
    for codename, nom in PERMISSIONS.items():
        permissions[codename], _ = Permission.objects.using(base).get_or_create(
            content_type=type_rapport, codename=codename, defaults={"name": nom}
        )
    for nom_groupe, codenames in PAR_ROLE.items():
        groupe = Group.objects.using(base).filter(name=nom_groupe).first()
        if groupe:
            groupe.permissions.add(*[permissions[c] for c in codenames])


class Migration(migrations.Migration):

    dependencies = [
        ("rapports", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(ajouter_permissions, migrations.RunPython.noop)]
