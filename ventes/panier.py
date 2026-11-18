"""Panier de caisse, conservé dans la session de l'utilisateur."""

import uuid

CLE = "panier_caisse"


class Panier:
    def __init__(self, session):
        self.session = session
        donnees = session.get(CLE)
        if not donnees or "jeton" not in donnees:
            donnees = {"jeton": str(uuid.uuid4()), "lignes": [], "client_id": None}
        self.donnees = donnees

    def _sauver(self):
        self.session[CLE] = self.donnees
        self.session.modified = True

    @property
    def jeton(self):
        return self.donnees["jeton"]

    @property
    def lignes(self):
        return self.donnees["lignes"]

    @property
    def client_id(self):
        return self.donnees.get("client_id")

    def definir_client(self, client_id):
        self.donnees["client_id"] = client_id
        self._sauver()

    def quantite_de(self, medicament_id, lot_id=None, hors_index=None):
        return sum(
            l["quantite"] for i, l in enumerate(self.lignes)
            if l["medicament_id"] == medicament_id and l["lot_id"] == lot_id and i != hors_index
        )

    def ajouter(self, medicament_id, quantite, lot_id=None):
        for ligne in self.lignes:
            if ligne["medicament_id"] == medicament_id and ligne["lot_id"] == lot_id:
                ligne["quantite"] += quantite
                break
        else:
            self.lignes.append({"medicament_id": medicament_id, "quantite": quantite, "lot_id": lot_id})
        self._sauver()

    def modifier(self, index, quantite):
        if 0 <= index < len(self.lignes):
            self.lignes[index]["quantite"] = quantite
            self._sauver()

    def retirer(self, index):
        if 0 <= index < len(self.lignes):
            del self.lignes[index]
            self._sauver()

    def vider(self):
        """Vide le panier et change de jeton : la vente suivante est une nouvelle vente."""
        self.donnees = {"jeton": str(uuid.uuid4()), "lignes": [], "client_id": None}
        self._sauver()
