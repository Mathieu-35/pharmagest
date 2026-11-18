"""Relance d'une opération entrée en conflit avec une autre transaction.

Quand deux validations arrivent en même temps, la base peut refuser la seconde (SQLite :
« base verrouillée » ; PostgreSQL : interblocage). Rien n'est modifié dans ce cas : on
attend un court instant puis on recommence. La seconde tentative voit alors le résultat
de la première (stock déjà diminué, vente déjà enregistrée...) et applique les règles normales.
"""

import time

from django.db import OperationalError

TENTATIVES = 5
PAUSE = 0.05  # secondes, multipliée par le numéro de la tentative


def reessayer_si_conflit(operation, tentatives=TENTATIVES, pause=PAUSE):
    for essai in range(1, tentatives + 1):
        try:
            return operation()
        except OperationalError:
            if essai == tentatives:
                raise
            time.sleep(pause * essai)
