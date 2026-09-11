#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test GPIO brut (sans bibliothèque rgbmatrix)
================================================

But : vérifier électriquement, indépendamment de tout réglage logiciel
(multiplexing, row_address_type, etc.), si les lignes R1/G1/B1 conduisent
bien jusqu'au panneau branché sur TOP-P4.

Ce script pilote directement les broches GPIO en "bit-banging" manuel du
protocole HUB75, sans passer par rgbmatrix. Il n'affiche qu'UNE seule ligne
(ligne 0) en une couleur unie, statique (pas de rafraîchissement continu,
donc pas de scintillement à gérer — plus simple pour ce test).

Mapping utilisé (mode "regular", chaîne 0 — celle de TOP-P4) :
    OE=18, CLK=17, STROBE=4, A=22, B=23, C=24, D=25, E=15
    R1=11, G1=27, B1=7  (R2=8, G2=9, B2=10 non utilisées ici)

Installation si besoin (sur le Pi) :
    sudo /home/admin/venv/bin/pip install RPi.GPIO

Utilisation :
    sudo /home/admin/venv/bin/python3 test_raw_gpio_led.py rouge
    sudo /home/admin/venv/bin/python3 test_raw_gpio_led.py vert
    sudo /home/admin/venv/bin/python3 test_raw_gpio_led.py bleu
    sudo /home/admin/venv/bin/python3 test_raw_gpio_led.py blanc

Interprétation :
    - Si 'rouge' allume la première ligne mais 'vert' et 'bleu' n'allument
      RIEN DU TOUT (pas même du bruit) -> confirme un problème électrique
      sur G1 (GPIO27) et/ou B1 (GPIO7) : câble, connecteur, ou puce buffer
      74HCT245 de la carte rouge côté TOP-P4.
    - Si 'vert' ou 'bleu' allument bien la ligne (même faiblement) -> le
      souci est probablement revenu côté réglages rgbmatrix, pas matériel.
"""

import sys
import time

import RPi.GPIO as GPIO

OE, CLK, STROBE = 18, 17, 4
A, B, C, D, E = 22, 23, 24, 25, 15
R1, G1, B1 = 11, 27, 7
R2, G2, B2 = 8, 9, 10

TOUTES_LES_BROCHES = [OE, CLK, STROBE, A, B, C, D, E, R1, G1, B1, R2, G2, B2]

COULEURS = {
    "rouge": (1, 0, 0),
    "vert":  (0, 1, 0),
    "bleu":  (0, 0, 1),
    "blanc": (1, 1, 1),
}

LARGEUR_CANVAS = 64  # 2 panneaux 32x32 chaînés


def pulse(pin):
    GPIO.output(pin, 1)
    time.sleep(0.000001)
    GPIO.output(pin, 0)


def afficher_ligne_unie(r1, g1, b1):
    GPIO.output(OE, 1)  # coupe la sortie pendant qu'on décale les données (actif bas)
    GPIO.output(R2, 0)
    GPIO.output(G2, 0)
    GPIO.output(B2, 0)
    for _ in range(LARGEUR_CANVAS):
        GPIO.output(R1, r1)
        GPIO.output(G1, g1)
        GPIO.output(B1, b1)
        pulse(CLK)
    for pin_adresse in (A, B, C, D, E):
        GPIO.output(pin_adresse, 0)  # ligne 0
    pulse(STROBE)
    GPIO.output(OE, 0)  # active la sortie (actif bas)


def main():
    couleur = sys.argv[1] if len(sys.argv) > 1 else "rouge"
    if couleur not in COULEURS:
        print(f"Couleur inconnue : {couleur}. Choix possibles : {list(COULEURS)}")
        return
    r, g, b = COULEURS[couleur]

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in TOUTES_LES_BROCHES:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)
    GPIO.output(OE, 1)  # sortie coupée au départ

    print(f"Test GPIO brut : première ligne en {couleur} (R1={r} G1={g} B1={b})")
    afficher_ligne_unie(r, g, b)

    try:
        input("Observe la première ligne du panneau, puis Entrée pour éteindre... ")
    finally:
        GPIO.output(OE, 1)
        GPIO.cleanup()


if __name__ == "__main__":
    main()