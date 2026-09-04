#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borne interactive - Point d'entrée principal
===============================================

Lance ensemble :
    - l'écoute micro/Vosk (voix.py)   -> dans un thread en arrière-plan
    - l'écran tactile (interface_tactile.py) -> dans le thread principal
      (obligatoire : Kivy doit tourner dans le thread principal)

Les deux partagent la même liste de destinations et déclenchent tous les
deux core.on_destination_reconnue(...), donc peu importe si l'utilisateur
parle ou touche l'écran, la réponse (voix + futur LED) est identique.

Lancement :
    python3 main.py
"""

import threading

import core
import voix
from interface_tactile import BorneApp


def main():
    destinations = core.charger_destinations()
    print(f"{len(destinations)} destination(s) chargée(s) depuis "
          f"'{core.DESTINATIONS_CSV_PATH}'.")

    arret_event = threading.Event()

    def lancer_ecoute():
        try:
            voix.ecouter(destinations=destinations, arret_event=arret_event)
        except Exception as e:
            # Si le micro/modèle Vosk n'est pas dispo (ex. test sur PC sans
            # matériel), on ne bloque pas l'écran tactile pour autant.
            print(f"[voix] Écoute micro indisponible, écran tactile seul "
                  f"reste actif. Détail : {e}")

    thread_voix = threading.Thread(target=lancer_ecoute, daemon=True)
    thread_voix.start()

    try:
        BorneApp().run()
    finally:
        arret_event.set()


if __name__ == "__main__":
    main()