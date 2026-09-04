#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borne interactive - Reconnaissance vocale (français, hors-ligne)
==================================================================

Version refactorée : toute la logique commune (destinations, matching,
voix, callbacks) vit maintenant dans core.py. Ce fichier ne contient
plus que ce qui est spécifique au micro/Vosk.

Deux façons de lancer :
    python3 voix.py            -> écoute réelle (micro + Vosk)
    python3 voix.py test       -> mode clavier, sans micro ni modèle Vosk

Pour lancer la voix EN MÊME TEMPS que l'écran tactile, voir main.py :
c'est lui qui orchestre les deux (la voix tourne alors dans un thread,
voix.py n'est plus lancé directement).
"""

import queue
import sys

import core

audio_queue = queue.Queue()


def callback_audio(indata, frames, time_info, status):
    if status:
        print(f"[audio] {status}", file=sys.stderr)
    audio_queue.put(bytes(indata))


def mode_test():
    """Mode clavier : valide le CSV / le matching / la voix sans matériel."""
    destinations = core.charger_destinations()
    print(f"{len(destinations)} destination(s) chargée(s) depuis "
          f"'{core.DESTINATIONS_CSV_PATH}'.")
    print("Mode test (clavier) — tape une phrase et Entrée. Ctrl+C pour quitter.\n")
    try:
        while True:
            texte = input("> ").strip()
            if not texte:
                continue
            destination_id = core.trouver_destination(destinations, texte)
            if destination_id:
                core.on_destination_reconnue(destinations, destination_id, texte,
                                              source="voix")
            else:
                core.on_non_compris(texte, source="voix")
    except (KeyboardInterrupt, EOFError):
        print("\nFin du mode test.")


def ecouter(destinations=None, arret_event=None):
    """
    Boucle d'écoute micro + Vosk. Peut être lancée directement (mode
    autonome) ou dans un thread par main.py (dans ce cas, passer un
    `threading.Event` dans `arret_event` pour pouvoir l'arrêter proprement
    depuis le thread principal, ex. à la fermeture de l'écran tactile).
    """
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer, SetLogLevel

    SetLogLevel(-1)

    if destinations is None:
        destinations = core.charger_destinations()
        print(f"{len(destinations)} destination(s) chargée(s) depuis "
              f"'{core.DESTINATIONS_CSV_PATH}'.")

    print("Chargement du modèle Vosk (peut prendre quelques secondes)...")
    try:
        model = Model(core.MODEL_PATH)
    except Exception as e:
        print(f"Impossible de charger le modèle depuis '{core.MODEL_PATH}'.\n"
              f"Vérifie qu'il est bien téléchargé et décompressé.\nErreur : {e}")
        sys.exit(1)

    grammaire = core.construire_grammaire(destinations)
    recognizer = KaldiRecognizer(model, core.SAMPLE_RATE, grammaire)

    print("Prêt. En écoute... (Ctrl+C pour arrêter)\n")

    with sd.RawInputStream(
        samplerate=core.SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=callback_audio,
    ):
        try:
            while arret_event is None or not arret_event.is_set():
                try:
                    data = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data):
                    import json
                    resultat = json.loads(recognizer.Result())
                    texte = resultat.get("text", "").strip()
                    if not texte:
                        continue

                    destination_id = core.trouver_destination(destinations, texte)
                    if destination_id:
                        core.on_destination_reconnue(destinations, destination_id,
                                                      texte, source="voix")
                    else:
                        core.on_non_compris(texte, source="voix")
        except KeyboardInterrupt:
            print("\nArrêt de l'écoute.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        mode_test()
    else:
        ecouter()