#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chemin LED — prototype autonome
================================

But : dès qu'une destination est choisie (ici saisie au clavier pour ce
test), dessiner un chemin lumineux depuis le point de départ fixe
(bas-centre des 2 panneaux chaînés) jusqu'à la coordonnée LED de la
salle, avec une animation progressive (le chemin se dessine point par
point, comme demandé).

Ce script est volontairement autonome pour l'instant. La logique de
calcul et de dessin du chemin (`calculer_chemin_bresenham`,
`dessiner_chemin`, `afficher_chemin_vers`) est isolée dans des
fonctions séparées, sans dépendance à Kivy ni à voix.py, pour être
facile à réutiliser telle quelle depuis core.py une fois validée.

Format attendu de Destinations.csv (2 nouvelles colonnes ajoutées à la
fin, séparateur ';', comme le reste du fichier) :

    id;aliases;etage;ligne;colonne

    ligne   : 0-31 (position verticale sur le canvas 64x32)
    colonne : 0-63 (position horizontale sur le canvas 64x32)

    Exemple : C2-07;salle c deux zero sept;2;4;40

Le chemin est pour l'instant une ligne droite (Bresenham) entre le
départ et la salle — c'est volontairement simplifié en attendant le
vrai pathfinding par graphe de corridors prévu plus tard dans le
projet ; remplacer `calculer_chemin_bresenham` par un appel au graphe
suffira à brancher la vraie logique plus tard sans toucher au reste.

Configuration matérielle : identique à test_rgbmatrix.py (carte rouge
en direct sur GPIO, mapping "regular", 2 panneaux chaînés 64x32, Pi 4).

Lancement :
    sudo /home/admin/venv/bin/python3 chemin_led.py
"""

import csv
import os
import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CSV = os.path.join(BASE_DIR, "Destinations.csv")

LARGEUR_CANVAS = 64
HAUTEUR_CANVAS = 32

# Point de départ fixe : bas, au milieu des deux panneaux chaînés
DEPART = (LARGEUR_CANVAS // 2, HAUTEUR_CANVAS - 1)  # (colonne, ligne)

COULEUR_CHEMIN = (255, 140, 0)      # orange, bien visible pour le trajet
COULEUR_DESTINATION = (0, 255, 0)   # vert, pour repérer clairement l'arrivée
DELAI_ENTRE_POINTS = 0.03           # secondes entre chaque point de l'animation


def creer_options():
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 32
    options.chain_length = 2
    options.parallel = 1
    options.hardware_mapping = "regular"
    options.gpio_slowdown = 4
    options.brightness = 60
    options.pwm_bits = 11
    options.disable_hardware_pulsing = True
    return options


def charger_destinations():
    """Charge Destinations.csv et renvoie un dict {id: (colonne, ligne)}.
    Les salles sans coordonnées LED valides sont ignorées avec un
    avertissement (pattern de dégradation gracieuse déjà utilisé ailleurs
    dans le projet)."""
    destinations = {}
    with open(CHEMIN_CSV, encoding="utf-8") as f:
        lecteur = csv.DictReader(f, delimiter=";")
        for rangee in lecteur:
            try:
                ligne = int(rangee["ligne"])
                colonne = int(rangee["colonne"])
            except (KeyError, ValueError):
                print(f"Ligne ignorée (coordonnées LED manquantes ou invalides) : {rangee}")
                continue
            destinations[rangee["id"]] = (colonne, ligne)
    return destinations


def calculer_chemin_bresenham(x0, y0, x1, y1):
    """Renvoie la liste des points (colonne, ligne) formant une ligne droite
    entre le départ et l'arrivée sur la grille de pixels (algorithme de
    Bresenham). Version temporaire avant le vrai pathfinding par graphe de
    corridors."""
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    erreur = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * erreur
        if e2 >= dy:
            erreur += dy
            x += sx
        if e2 <= dx:
            erreur += dx
            y += sy
    return points


def dessiner_chemin(matrix, canvas, points, couleur_chemin, couleur_destination):
    """Anime le chemin point par point : chaque point reste allumé pendant
    qu'on ajoute le suivant, donc le chemin se construit progressivement à
    l'écran. Le dernier point (la salle) est mis en évidence dans une
    couleur différente."""
    canvas.Clear()
    canvas = matrix.SwapOnVSync(canvas)
    for i, (x, y) in enumerate(points):
        est_dernier_point = (i == len(points) - 1)
        r, g, b = couleur_destination if est_dernier_point else couleur_chemin
        canvas.SetPixel(x, y, r, g, b)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(DELAI_ENTRE_POINTS)
    return canvas


def afficher_chemin_vers(matrix, canvas, destinations, id_salle):
    """Point d'entrée principal à appeler dès qu'une destination est
    reconnue (vocalement ou tactilement). C'est cette fonction qu'il
    faudra appeler depuis core.py une fois intégrée."""
    if id_salle not in destinations:
        print(f"Salle inconnue ou sans coordonnées LED : {id_salle}")
        return canvas
    arrivee = destinations[id_salle]
    print(f"Chemin vers {id_salle} : {DEPART} -> {arrivee}")
    points = calculer_chemin_bresenham(DEPART[0], DEPART[1], arrivee[0], arrivee[1])
    return dessiner_chemin(matrix, canvas, points, COULEUR_CHEMIN, COULEUR_DESTINATION)


def menu(matrix, destinations):
    """Boucle de test au clavier — à remplacer par l'appel déclenché par la
    reconnaissance vocale / le tactile une fois intégré à main.py."""
    canvas = matrix.CreateFrameCanvas()
    print(f"\n{len(destinations)} destination(s) chargée(s) depuis Destinations.csv")
    print("Entre un id de salle (ex: C2-07), ou 'q' pour quitter.")
    while True:
        id_salle = input("Salle : ").strip()
        if id_salle.lower() == "q":
            break
        canvas = afficher_chemin_vers(matrix, canvas, destinations, id_salle)


def main():
    destinations = charger_destinations()
    if not destinations:
        print("Aucune destination avec coordonnées LED valides trouvée dans le CSV.")
        print(f"Vérifie que {CHEMIN_CSV} contient bien les colonnes 'ligne' et 'colonne'.")
        return
    options = creer_options()
    matrix = RGBMatrix(options=options)
    try:
        menu(matrix, destinations)
    finally:
        matrix.Clear()


if __name__ == "__main__":
    main()