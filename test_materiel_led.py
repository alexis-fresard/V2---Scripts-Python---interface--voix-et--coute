#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic matériel — panneaux LED
=====================================

But : isoler un problème de branchement/config AVANT de retester la logique
de chemin. Chaque test est indépendant et minimal (une seule fonction de la
bibliothèque à la fois), comme dans "Fonction bibliothèque github Python.docx".

Lancement (obligatoirement root pour l'accès GPIO) :
    sudo ~/venv/bin/python3 test_materiel_led.py

Avant de lancer ce script, vérifie d'abord la démo C fournie par la
bibliothèque — c'est la référence qui a déjà fonctionné :
    cd ~/rpi-rgb-led-matrix/examples-api-use
    sudo ./demo -D -m 0 --led-no-hardware-pulse --led-gpio-mapping=regular --led-slowdown-gpio=4

Si CETTE démo n'affiche rien non plus, le problème est 100% câblage/alim
(pas la peine de chercher plus loin côté Python) : revérifier
- l'alimentation 5V des panneaux (branchement + et -, ~3.5A par panneau 32x32)
- le sens du chaînage (sortie panneau 1 -> entrée panneau 2, flèche TOP-P0)
- que la carte de lecteur est bien orientée sur le GPIO (voir doc branchement)

Si la démo C fonctionne mais pas ce script Python, le souci est côté config
Python (options ci-dessous) ou côté environnement (venv / droits root).
"""

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# ---------------------------------------------------------------------------
# Configuration — identique à la commande de démo C qui a déjà fonctionné :
#   --led-no-hardware-pulse --led-gpio-mapping=regular --led-slowdown-gpio=4
# ---------------------------------------------------------------------------
options = RGBMatrixOptions()
options.rows = 32
options.cols = 32
options.chain_length = 2          # 2 panneaux chaînés -> adapter si autre montage
options.parallel = 1
options.hardware_mapping = "regular"
options.gpio_slowdown = 4
options.disable_hardware_pulsing = True

print("Configuration utilisée :")
print(f"  rows={options.rows} cols={options.cols} chain_length={options.chain_length} "
      f"parallel={options.parallel}")
print(f"  hardware_mapping={options.hardware_mapping} gpio_slowdown={options.gpio_slowdown} "
      f"disable_hardware_pulsing={options.disable_hardware_pulsing}")
print(f"  -> canvas total : {options.cols * options.chain_length}x{options.rows * options.parallel}\n")

matrix = RGBMatrix(options=options)
LARGEUR = options.cols * options.chain_length
HAUTEUR = options.rows * options.parallel


def attendre():
    input("   (Entrée pour continuer) ")


def test_remplissage_uni():
    """Étape la plus basique possible : tout allumer d'une seule couleur."""
    print("Test 1 : remplissage rouge uni sur tout le canvas...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Fill(255, 0, 0)
    matrix.SwapOnVSync(canvas)
    print("  -> Si rien n'est allumé du tout : problème alim/câblage/mapping.")
    attendre()

    print("Test 1bis : vert puis bleu (pour vérifier l'ordre des couleurs)...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Fill(0, 255, 0)
    matrix.SwapOnVSync(canvas)
    attendre()
    canvas = matrix.CreateFrameCanvas()
    canvas.Fill(0, 0, 255)
    matrix.SwapOnVSync(canvas)
    print("  -> Si les couleurs sont inversées/fausses : problème de mapping RVB.")
    attendre()


def test_un_seul_pixel():
    """Si le remplissage marche mais pas ça : problème d'adressage/pathfinding, pas de matériel."""
    print(f"Test 2 : un seul pixel blanc en (0,0) [coin du 1er panneau]...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    canvas.SetPixel(0, 0, 255, 255, 255)
    matrix.SwapOnVSync(canvas)
    attendre()

    x_dernier = LARGEUR - 1
    print(f"Test 2bis : un seul pixel blanc en ({x_dernier},0) [coin du 2e panneau]...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    canvas.SetPixel(x_dernier, 0, 255, 255, 255)
    matrix.SwapOnVSync(canvas)
    print("  -> Si le 1er pixel marche mais pas celui-ci : problème de chaînage entre panneaux.")
    attendre()


def test_quadrants():
    """Confirme l'orientation exacte de chaque panneau (utile pour caler les coordonnées du graphe)."""
    print("Test 3 : un coin de chaque panneau dans une couleur différente...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    canvas.SetPixel(0, 0, 255, 0, 0)                    # coin haut-gauche panneau 1 : rouge
    canvas.SetPixel(31, 0, 0, 255, 0)                   # coin haut-droit panneau 1 : vert
    canvas.SetPixel(32, 0, 0, 0, 255)                   # coin haut-gauche panneau 2 : bleu
    canvas.SetPixel(LARGEUR - 1, 0, 255, 255, 0)        # coin haut-droit panneau 2 : jaune
    canvas.SetPixel(0, HAUTEUR - 1, 255, 0, 255)        # coin bas-gauche panneau 1 : magenta
    matrix.SwapOnVSync(canvas)
    print("  -> Note quelle couleur apparaît où : ça donne l'orientation réelle du canvas.")
    attendre()


def test_ligne_et_cercle():
    print("Test 4 : une ligne diagonale sur tout le canvas...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    couleur = graphics.Color(0, 255, 255)
    graphics.DrawLine(canvas, 0, 0, LARGEUR - 1, HAUTEUR - 1, couleur)
    matrix.SwapOnVSync(canvas)
    attendre()

    print("Test 5 : un cercle au centre...")
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    graphics.DrawCircle(canvas, LARGEUR // 2, HAUTEUR // 2, 10, couleur)
    matrix.SwapOnVSync(canvas)
    attendre()


def test_texte():
    print("Test 6 : affichage d'un texte (nécessite une police .bdf, ex. celle des démos)...")
    try:
        font = graphics.Font()
        font.LoadFont("../rpi-rgb-led-matrix/fonts/7x13.bdf")  # adapter le chemin si besoin
        canvas = matrix.CreateFrameCanvas()
        canvas.Clear()
        couleur = graphics.Color(255, 255, 255)
        graphics.DrawText(canvas, font, 1, 15, couleur, "Test")
        matrix.SwapOnVSync(canvas)
    except Exception as e:
        print(f"  [Ignoré] Police introuvable ou erreur : {e}")
    attendre()


def main():
    tests = [
        ("Remplissage couleur uni (rouge/vert/bleu)", test_remplissage_uni),
        ("Un seul pixel (coin panneau 1 puis panneau 2)", test_un_seul_pixel),
        ("Coins des 2 panneaux en couleurs différentes", test_quadrants),
        ("Ligne diagonale + cercle", test_ligne_et_cercle),
        ("Texte", test_texte),
    ]
    print("=== Diagnostic matériel LED ===")
    print("Chaque test attend une touche Entrée avant de passer au suivant.\n")
    for nom, fonction in tests:
        print(f"--- {nom} ---")
        fonction()

    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    matrix.SwapOnVSync(canvas)
    print("Diagnostic terminé, écran éteint.")


if __name__ == "__main__":
    main()