#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de type d'adressage / multiplexage du panneau
=====================================================

Le port TOP-P4 est confirmé comme étant le bon port (chain 0). Mais le
panneau affiche une moitié allumée / des couleurs fausses -> c'est un
symptôme classique de mauvais réglage de row_address_type ou multiplexing
(le panneau n'utilise pas le schéma d'adressage par défaut).

Utilisation (sur le Pi, avec le venv) :
    sudo /home/admin/venv/bin/python3 test_scan_led.py <row_addr_type> <multiplexing>

Exemples à essayer dans l'ordre (relance la commande en changeant juste
les deux chiffres, pas besoin de rééditer le fichier) :
    sudo ...python3 test_scan_led.py 0 0    # réglage par défaut (déjà testé)
    sudo ...python3 test_scan_led.py 1 0
    sudo ...python3 test_scan_led.py 2 0
    sudo ...python3 test_scan_led.py 3 0
    sudo ...python3 test_scan_led.py 4 0
    sudo ...python3 test_scan_led.py 0 1
    sudo ...python3 test_scan_led.py 0 2
    sudo ...python3 test_scan_led.py 0 3
    ... etc.

À chaque essai : le panneau doit s'allumer TOTALEMENT et UNIFORMÉMENT en
blanc si la combinaison est la bonne. Note le (row_addr_type, multiplexing)
qui donne un résultat propre.

row_address_type : 0=défaut, 1=AB-addressed, 2=direct row select,
                    3=ABC-addressed, 4=ABC Shift + DE direct
multiplexing      : 0=direct (défaut), puis 1 à ~18 selon les fabricants
                    (Stripe, Checkered, Spiral, ZStripe, etc.)
"""

import sys
from rgbmatrix import RGBMatrix, RGBMatrixOptions

row_addr_type = int(sys.argv[1]) if len(sys.argv) > 1 else 0
multiplexing = int(sys.argv[2]) if len(sys.argv) > 2 else 0

options = RGBMatrixOptions()
options.rows = 32
options.cols = 32
options.chain_length = 2
options.parallel = 1
options.hardware_mapping = "regular"
options.gpio_slowdown = 4
options.disable_hardware_pulsing = True
options.row_address_type = row_addr_type
options.multiplexing = multiplexing

print(f"Test avec row_address_type={row_addr_type}, multiplexing={multiplexing}")
print("-> Le panneau devrait s'allumer entièrement en blanc si c'est le bon réglage.")

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()
canvas.Fill(255, 255, 255)
matrix.SwapOnVSync(canvas)

input("Observe le panneau, puis appuie sur Entrée pour éteindre et quitter... ")

canvas = matrix.CreateFrameCanvas()
canvas.Clear()
matrix.SwapOnVSync(canvas)