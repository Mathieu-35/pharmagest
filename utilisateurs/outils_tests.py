"""Aides communes aux tests (création d'utilisateurs par rôle)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

HASH_RAPIDE = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MDP = "Mot-de-passe-solide-42"


def creer_utilisateur(nom, *roles, **extra):
    utilisateur = get_user_model().objects.create(username=nom, **extra)
    for role in roles:
        utilisateur.groups.add(Group.objects.get(name=role))
    return utilisateur
