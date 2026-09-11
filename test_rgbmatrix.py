#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test avec la bibliothèque rgbmatrix (rpi-rgb-led-matrix)
==========================================================

Contrairement aux scripts précédents (bit-banging manuel en Python), ici
c'est la bibliothèque C compilée qui gère le rafraîchissement en boucle
via un thread haute priorité — plus de scintillement, PWM réel pour de
vraies couleurs (pas juste 8 couleurs on/off), et le multiplexage des
16 adresses est géré nativement.

Configuration matérielle (d'après ta config actuelle) :
    - Carte "rouge" branchée en direct sur le GPIO (pas de HAT Adafruit)
      -> hardware_mapping = "regular"
    - 2 panneaux 32x32 chaînés en une seule rangée -> 64x32
    - Raspberry Pi 4 -> gpio_slowdown = 4 (recommandé pour le Pi 4,
      comme dans les commandes de démo de ton document)

Pré-requis : la bibliothèque doit déjà être compilée et installée
(tu l'as fait en suivant "Installation et branchement.docx" :
`sudo make install-python PYTHON=$(which python3)` dans
`bindings/python/`).

IMPORTANT : ce script doit être lancé avec sudo (accès direct au GPIO) :
    sudo /home/admin/venv/bin/python3 test_rgbmatrix.py
"""

import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics


# --- Chemin vers une police .bdf fournie avec rpi-rgb-led-matrix ---
# Ajuste si ton dossier du dépôt n'est pas à cet endroit.
CHEMIN_POLICE = "/home/admin/rpi-rgb-led-matrix/fonts/7x13.bdf"


def creer_options():
    options = RGBMatrixOptions()
    options.rows = 32                  # hauteur d'un panneau
    options.cols = 32                  # largeur d'un panneau
    options.chain_length = 2           # 2 panneaux chaînés -> 64x32 au total
    options.parallel = 1               # une seule chaîne (pas de panneaux en parallèle)
    options.hardware_mapping = "regular"   # carte rouge en direct sur GPIO, pas de HAT
    options.gpio_slowdown = 4          # requis sur Pi 4 pour un signal stable
    options.brightness = 60            # 0-100 ; baisse si l'alim peine encore un peu
    options.pwm_bits = 11              # profondeur de couleur (défaut, laisse tel quel pour commencer)
    options.disable_hardware_pulsing = True  # utile si pas de patch audio désactivé sur le Pi
    return options


def test_couleurs_pleines(matrix):
    """Remplit tout le canvas (64x32) en rouge, vert, bleu, blanc — comparable
    au test 1 du script brut, mais sans scintillement cette fois."""
    couleurs = [
        ("ROUGE", (255, 0, 0)),
        ("VERT", (0, 255, 0)),
        ("BLEU", (0, 0, 255)),
        ("BLANC", (255, 255, 255)),
    ]
    for nom, (r, g, b) in couleurs:
        print(f"Couleur affichée : {nom} — observe si c'est stable (pas de scintillement)")
        matrix.Fill(r, g, b)
        input("  -> Entrée pour la couleur suivante... ")


def test_texte(matrix):
    """Affiche un texte statique, puis un texte qui défile — pour vérifier
    la lisibilité et le bon sens de chaînage des panneaux."""
    canvas = matrix.CreateFrameCanvas()
    police = graphics.Font()
    try:
        police.LoadFont(CHEMIN_POLICE)
    except Exception as e:
        print(f"Impossible de charger la police à {CHEMIN_POLICE} : {e}")
        print("Ajuste CHEMIN_POLICE en haut du script vers ton dossier rpi-rgb-led-matrix/fonts/")
        return

    couleur_texte = graphics.Color(255, 255, 0)

    print("Texte statique 'TEST OK'")
    canvas.Clear()
    graphics.DrawText(canvas, police, 4, 20, couleur_texte, "TEST OK")
    canvas = matrix.SwapOnVSync(canvas)
    input("  -> Entrée pour le texte défilant... ")

    print("Texte défilant (Ctrl+C ou Entrée pour arrêter)")
    texte = "BORNE DIVTEC - TEST"
    position = canvas.width
    try:
        while True:
            canvas.Clear()
            longueur = graphics.DrawText(canvas, police, position, 20, couleur_texte, texte)
            position -= 1
            if position + longueur < 0:
                position = canvas.width
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(0.03)
    except KeyboardInterrupt:
        pass


def test_identification_panneaux(matrix):
    """Moitié gauche rouge, moitié droite verte — pour confirmer que le
    chaînage des 2 panneaux est dans le bon sens (même test que sur le
    script brut, mais ici via la bibliothèque)."""
    canvas = matrix.CreateFrameCanvas()
    for y in range(canvas.height):
        for x in range(canvas.width):
            if x < canvas.width // 2:
                canvas.SetPixel(x, y, 255, 0, 0)
            else:
                canvas.SetPixel(x, y, 0, 255, 0)
    matrix.SwapOnVSync(canvas)
    input("  -> Entrée pour continuer... ")


def main():
    options = creer_options()
    matrix = RGBMatrix(options=options)

    try:
        test_couleurs_pleines(matrix)
        test_identification_panneaux(matrix)
        test_texte(matrix)
    finally:
        matrix.Clear()


if __name__ == "__main__":
    main()