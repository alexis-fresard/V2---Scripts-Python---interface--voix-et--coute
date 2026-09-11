#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test GPIO brut complet (sans bibliothèque rgbmatrix)
=====================================================

But : aller plus loin que le test "une ligne, une couleur" en pilotant
l'ENSEMBLE du canvas (les deux panneaux chaînés, toutes les lignes) en
bit-banging manuel du protocole HUB75, pour repérer des problèmes qui ne
se voient pas sur une seule ligne statique : lignes d'adresse (A/B/C/D)
défectueuses, mauvais ordre de chaînage entre panneaux, pixels morts,
canal couleur qui lâche uniquement sur certaines lignes, etc.

Contrairement au script précédent, l'affichage complet nécessite un
rafraîchissement en boucle (multiplexage) car chaque adresse (0 à 15)
pilote 2 lignes physiques à la fois (haut via R1/G1/B1, bas via
R2/G2/B2) — il faut donc rebalayer les 16 adresses en continu pour que
l'image tienne à l'œil (persistance rétinienne), sinon on ne voit
qu'une ligne à la fois clignoter très vite.

Mapping utilisé (mode "regular", chaîne 0 — celle de TOP-P4), identique
au script précédent :
    OE=18, CLK=17, STROBE=4, A=22, B=23, C=24, D=25, E=15
    R1=11, G1=27, B1=7  (haut de chaque paire de lignes)
    R2=8,  G2=9,  B2=10 (bas de chaque paire de lignes)

Hypothèse : 2 panneaux 32x32 chaînés horizontalement -> canvas de
64 colonnes x 32 lignes, scan 1:16 (adresses 0-15, E non utilisé).
Si vos panneaux sont en scan 1:8 ou 1:32, dites-le-moi : le nombre
d'adresses et l'usage de E changent.

Installation si besoin (sur le Pi) :
    sudo /home/admin/venv/bin/pip install RPi.GPIO

Utilisation :
    sudo /home/admin/venv/bin/python3 test_raw_gpio_led_complet.py

Un menu s'affiche : chaque test tourne en boucle jusqu'à ce que vous
appuyiez sur Entrée, ce qui passe au test suivant (ou quitte).
"""

import sys
import time
import threading

import RPi.GPIO as GPIO

# --- Mapping des broches (identique au script précédent) ---
OE, CLK, STROBE = 18, 17, 4
A, B, C, D, E = 22, 23, 24, 25, 15
R1, G1, B1 = 11, 27, 7
R2, G2, B2 = 8, 9, 10

TOUTES_LES_BROCHES = [OE, CLK, STROBE, A, B, C, D, E, R1, G1, B1, R2, G2, B2]

LARGEUR_CANVAS = 64   # 2 panneaux 32x32 chaînés horizontalement
HAUTEUR_CANVAS = 32   # hauteur d'un panneau
NB_ADRESSES = 16      # scan 1:16 -> 16 adresses, chacune pilote 2 lignes (n et n+16)

NOIR, ROUGE, VERT, BLEU, BLANC = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1)


# ---------------------------------------------------------------------------
# Primitives bas niveau (identiques dans l'esprit au script précédent)
# ---------------------------------------------------------------------------

def pulse(pin):
    GPIO.output(pin, 1)
    time.sleep(0.000001)
    GPIO.output(pin, 0)


def set_adresse(n):
    """Positionne les lignes d'adresse A/B/C/D pour sélectionner la paire de
    lignes n et n+16. E reste à 0 (non utilisé en scan 1:16)."""
    GPIO.output(A, n & 1)
    GPIO.output(B, (n >> 1) & 1)
    GPIO.output(C, (n >> 2) & 1)
    GPIO.output(D, (n >> 3) & 1)
    GPIO.output(E, 0)


def creer_framebuffer(couleur=NOIR):
    """Crée un buffer image [ligne][colonne] = (r, g, b), toutes les lignes
    initialisées à la couleur donnée."""
    return [[couleur for _ in range(LARGEUR_CANVAS)] for _ in range(HAUTEUR_CANVAS)]


def rafraichir_une_fois(framebuffer):
    """Balaie les 16 adresses une fois (un rafraîchissement complet de
    l'image). À appeler en boucle pour que l'image tienne à l'œil."""
    for adresse in range(NB_ADRESSES):
        GPIO.output(OE, 1)  # coupe la sortie pendant qu'on décale les données
        ligne_haut = framebuffer[adresse]
        ligne_bas = framebuffer[adresse + 16]
        for col in range(LARGEUR_CANVAS):
            r1, g1, b1 = ligne_haut[col]
            r2, g2, b2 = ligne_bas[col]
            GPIO.output(R1, r1)
            GPIO.output(G1, g1)
            GPIO.output(B1, b1)
            GPIO.output(R2, r2)
            GPIO.output(G2, g2)
            GPIO.output(B2, b2)
            pulse(CLK)
        set_adresse(adresse)
        pulse(STROBE)
        GPIO.output(OE, 0)  # active la sortie
        #time.sleep(0.0003)  # temps d'affichage de la paire de lignes


def attendre_entree_en_arriere_plan(message):
    """Lance un thread qui attend la touche Entrée, et renvoie un Event mis
    à True dès que l'utilisateur appuie. Permet de continuer à rafraîchir
    l'écran en boucle pendant qu'on attend l'utilisateur."""
    evt = threading.Event()

    def attendre():
        try:
            input(message)
        except EOFError:
            pass
        evt.set()

    threading.Thread(target=attendre, daemon=True).start()
    return evt


def afficher_jusqua_entree(framebuffer, message="  -> Entrée pour continuer... "):
    """Rafraîchit le framebuffer en boucle jusqu'à ce que l'utilisateur
    appuie sur Entrée (ou Ctrl+C)."""
    evt = attendre_entree_en_arriere_plan(message)
    try:
        while not evt.is_set():
            rafraichir_une_fois(framebuffer)
    except KeyboardInterrupt:
        pass


def animer_jusqua_entree(generateur_frames, delai_entre_frames, message="  -> Entrée pour continuer... "):
    """Pour les tests animés (pixel qui défile) : `generateur_frames` est un
    générateur infini qui produit un nouveau framebuffer à chaque itération.
    On rafraîchit chaque frame pendant `delai_entre_frames` secondes avant
    de passer à la suivante, jusqu'à Entrée ou Ctrl+C."""
    evt = attendre_entree_en_arriere_plan(message)
    try:
        for frame in generateur_frames:
            if evt.is_set():
                break
            t_fin_frame = time.time() + delai_entre_frames
            while time.time() < t_fin_frame and not evt.is_set():
                rafraichir_une_fois(frame)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_couleurs_pleines():
    """Remplit tout le canvas (les 2 panneaux, toutes les lignes) en rouge,
    vert, bleu puis blanc, un après l'autre. Vérifie que chaque canal
    fonctionne sur TOUTE la surface, pas juste sur la ligne 0."""
    print("\n[Test 1] Couleurs pleines sur tout le canvas")
    for nom, couleur in [("ROUGE", ROUGE), ("VERT", VERT), ("BLEU", BLEU), ("BLANC", BLANC)]:
        print(f" Couleur affichée : {nom} (tout le canvas doit être uniforme)")
        fb = creer_framebuffer(couleur)
        afficher_jusqua_entree(fb, f"  {nom} affiché -> Entrée pour la couleur suivante... ")


def test_barres_rgb():
    """Affiche 3 bandes verticales R/G/B côte à côte sur toute la hauteur.
    Utile pour repérer un décalage de colonnes entre les 2 panneaux chaînés,
    ou un canal qui ne s'allume que sur une partie de la largeur."""
    print("\n[Test 2] Barres verticales Rouge / Vert / Bleu")
    fb = creer_framebuffer(NOIR)
    tiers = LARGEUR_CANVAS // 3
    for y in range(HAUTEUR_CANVAS):
        for x in range(LARGEUR_CANVAS):
            if x < tiers:
                fb[y][x] = ROUGE
            elif x < 2 * tiers:
                fb[y][x] = VERT
            else:
                fb[y][x] = BLEU
    afficher_jusqua_entree(fb)


def test_damier():
    """Damier pixel par pixel (1 pixel allumé, 1 éteint, en quinconce).
    Un bon moyen visuel de repérer des pixels morts ou des colonnes qui ne
    répondent pas correctement au clock."""
    print("\n[Test 3] Damier pixel par pixel (blanc / éteint)")
    fb = creer_framebuffer(NOIR)
    for y in range(HAUTEUR_CANVAS):
        for x in range(LARGEUR_CANVAS):
            if (x + y) % 2 == 0:
                fb[y][x] = BLANC
    afficher_jusqua_entree(fb)


def test_identification_panneaux():
    """Moitié gauche (colonnes 0-31, panneau branché sur TOP-P4) en rouge,
    moitié droite (colonnes 32-63, panneau chaîné en aval) en vert.
    Permet de confirmer visuellement l'ordre et l'orientation du
    chaînage : si les couleurs sont inversées ou mélangées, le sens de
    chaînage ou le mapping des colonnes n'est pas celui attendu."""
    print("\n[Test 4] Identification des panneaux (gauche=ROUGE, droite=VERT)")
    fb = creer_framebuffer(NOIR)
    for y in range(HAUTEUR_CANVAS):
        for x in range(LARGEUR_CANVAS):
            fb[y][x] = ROUGE if x < LARGEUR_CANVAS // 2 else VERT
    afficher_jusqua_entree(fb)


def test_balayage_lignes():
    """Allume une seule paire de lignes à la fois (adresse n et n+16) en
    blanc, en cyclant sur les 16 adresses. Contrairement aux autres tests,
    chaque adresse est maintenue statique quelques secondes (pas besoin de
    persistance rétinienne ici) : si une ligne particulière ne s'allume
    jamais, ça pointe vers un souci sur la ligne d'adresse correspondante
    (A/B/C/D) ou son connecteur."""
    print("\n[Test 5] Balayage ligne par ligne (adresses 0 à 15)")
    print(" Chaque paire de lignes reste allumée ~1.5s avant de passer à la suivante.")
    evt = attendre_entree_en_arriere_plan("  Entrée à tout moment pour arrêter et continuer... ")
    try:
        for adresse in range(NB_ADRESSES):
            if evt.is_set():
                break
            print(f"  -> adresse {adresse:2d}  (lignes {adresse} et {adresse + 16})")
            fb = creer_framebuffer(NOIR)
            fb[adresse] = [BLANC] * LARGEUR_CANVAS
            fb[adresse + 16] = [BLANC] * LARGEUR_CANVAS
            t_fin = time.time() + 1.5
            while time.time() < t_fin and not evt.is_set():
                rafraichir_une_fois(fb)
    except KeyboardInterrupt:
        pass


def test_pixel_qui_defile():
    """Un unique pixel blanc se déplace ligne par ligne, colonne par
    colonne, sur tout le canvas. Le test le plus fin pour repérer un pixel
    mort isolé (contrairement au damier, on regarde une position précise
    à la fois)."""
    print("\n[Test 6] Pixel qui défile sur tout le canvas")

    def generateur():
        while True:
            for y in range(HAUTEUR_CANVAS):
                for x in range(LARGEUR_CANVAS):
                    fb = creer_framebuffer(NOIR)
                    fb[y][x] = BLANC
                    yield fb

    animer_jusqua_entree(generateur(), delai_entre_frames=0.03)


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------

TESTS = [
    ("Couleurs pleines (rouge/vert/bleu/blanc sur tout l'écran)", test_couleurs_pleines),
    ("Barres verticales RGB", test_barres_rgb),
    ("Damier pixel par pixel", test_damier),
    ("Identification des panneaux chaînés (gauche/droite)", test_identification_panneaux),
    ("Balayage ligne par ligne (adresses A/B/C/D)", test_balayage_lignes),
    ("Pixel qui défile (recherche de pixel mort)", test_pixel_qui_defile),
]


def initialiser_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in TOUTES_LES_BROCHES:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)
    GPIO.output(OE, 1)  # sortie coupée au départ


def menu():
    while True:
        print("\n=== Test complet de la carte / des panneaux LED ===")
        for i, (nom, _) in enumerate(TESTS, start=1):
            print(f"  {i}. {nom}")
        print("  0. Quitter")
        choix = input("Choix : ").strip()
        if choix == "0":
            break
        try:
            index = int(choix) - 1
            if index < 0 or index >= len(TESTS):
                raise ValueError
        except ValueError:
            print("Choix invalide.")
            continue
        _, fonction_test = TESTS[index]
        fonction_test()


def main():
    initialiser_gpio()
    try:
        menu()
    finally:
        GPIO.output(OE, 1)
        GPIO.cleanup()
        print("GPIO libérés proprement.")


if __name__ == "__main__":
    main()