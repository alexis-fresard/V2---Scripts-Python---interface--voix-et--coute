#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test des lignes d'adressage de rangée (A, B, C, D)
======================================================

Le test précédent (test_raw_gpio_led.py) a confirmé que R1/G1/B1 sont bien
câblées : c'était fait avec adresse de ligne = 0 (A=B=C=D=E=0). Mais on n'a
JAMAIS testé si les lignes A/B/C/D elles-mêmes sont bien câblées. Un panneau
32x32 en scan 1:16 a normalement 16 adresses (0 à 15), chacune affichant
simultanément la ligne physique N (via R1/G1/B1) et la ligne N+16 (via
R2/G2/B2).

Ce script allume UNE SEULE ligne, en rouge, à l'adresse demandée, pour que tu
voies à l'œil quelle ligne PHYSIQUE s'allume réellement.

Utilisation :
    sudo /home/admin/venv/bin/python3 test_adressage_led.py 0
    sudo /home/admin/venv/bin/python3 test_adressage_led.py 1
    sudo /home/admin/venv/bin/python3 test_adressage_led.py 5
    sudo /home/admin/venv/bin/python3 test_adressage_led.py 15

Interprétation :
    - Si l'adresse 0 allume la ligne tout en haut, l'adresse 1 la ligne juste
      en dessous, etc. (dans l'ordre, une par une, en descendant) -> les
      lignes A/B/C/D sont bien câblées, ce n'est pas le problème.
    - Si les lignes s'allument dans le désordre (ex: adresse 1 allume une
      ligne loin de l'adresse 0), ou si plusieurs lignes s'allument à la
      fois, ou si rien ne bouge d'une adresse à l'autre -> confirmé, les
      lignes d'adressage sont mal câblées ou mal mappées (--led-row-addr-type
      ou --led-multiplexing à revoir, ou souci physique sur ces lignes).
"""

import sys
import time

import RPi.GPIO as GPIO

OE, CLK, STROBE = 18, 17, 4
A, B, C, D, E = 22, 23, 24, 25, 15
R1, G1, B1 = 11, 27, 7
R2, G2, B2 = 8, 9, 10

TOUTES_LES_BROCHES = [OE, CLK, STROBE, A, B, C, D, E, R1, G1, B1, R2, G2, B2]
LARGEUR_CANVAS = 64


def pulse(pin):
    GPIO.output(pin, 1)
    time.sleep(0.000001)
    GPIO.output(pin, 0)


def afficher_ligne_rouge(adresse):
    GPIO.output(OE, 1)
    GPIO.output(R2, 0)
    GPIO.output(G2, 0)
    GPIO.output(B2, 0)
    for _ in range(LARGEUR_CANVAS):
        GPIO.output(R1, 1)
        GPIO.output(G1, 0)
        GPIO.output(B1, 0)
        pulse(CLK)
    # Décompose l'adresse (0-15) en bits A,B,C,D
    GPIO.output(A, (adresse >> 0) & 1)
    GPIO.output(B, (adresse >> 1) & 1)
    GPIO.output(C, (adresse >> 2) & 1)
    GPIO.output(D, (adresse >> 3) & 1)
    GPIO.output(E, 0)
    pulse(STROBE)
    GPIO.output(OE, 0)


def main():
    if len(sys.argv) < 2:
        print("Utilisation : test_adressage_led.py <adresse 0-15>")
        return
    adresse = int(sys.argv[1])

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in TOUTES_LES_BROCHES:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)
    GPIO.output(OE, 1)

    print(f"Adresse testée : {adresse} (A={adresse & 1} B={(adresse>>1)&1} "
          f"C={(adresse>>2)&1} D={(adresse>>3)&1})")
    afficher_ligne_rouge(adresse)

    try:
        input("Note QUELLE ligne physique s'allume, puis Entrée pour éteindre... ")
    finally:
        GPIO.output(OE, 1)
        GPIO.cleanup()


if __name__ == "__main__":
    main()