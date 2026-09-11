#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borne interactive - Affichage du chemin LED
=============================================

Ce module s'abonne au système de callbacks de core.py
(`core.ajouter_abonne`) pour dessiner automatiquement un chemin lumineux
dès qu'une destination est reconnue, que ce soit par la voix ou par
l'écran tactile. Il n'a aucune connaissance de la source ni de la
logique de matching — exactement le découplage prévu par le système
d'abonnés de core.py.

Intégration dans main.py (à faire une seule fois, au démarrage) :

    import led
    import core

    destinations = core.charger_destinations()
    led.initialiser()
    core.ajouter_abonne(led.on_destination_reconnue)

    ... (lancement de la voix / de l'interface tactile comme avant) ...

    # à la fermeture propre de l'application :
    led.arreter()

Les coordonnées LED de chaque salle viennent des colonnes optionnelles
"ligne" et "colonne" de Destinations.csv (voir la version mise à jour de
core.charger_destinations). Une salle sans coordonnées valides n'aura
simplement pas de chemin LED affiché — dégradation gracieuse, la voix
et le tactile continuent de fonctionner normalement.

Le chemin est pour l'instant une ligne droite (Bresenham) entre le point
de départ fixe et la salle — à remplacer par le vrai pathfinding par
graphe de corridors plus tard : il suffira de changer `calculer_chemin`,
rien d'autre dans ce module n'a besoin de bouger.

IMPORTANT (intégration avec l'écran tactile Kivy) : l'animation dure le
temps de parcourir tous les points du chemin (~0.03s par point). Pour ne
pas geler l'interface tactile si `on_destination_reconnue` est appelée
depuis le thread principal Kivy, l'animation tourne dans un thread
séparé (voir `threading.Thread` plus bas).

Configuration matérielle : carte rouge en direct sur GPIO, mapping
"regular", 2 panneaux chaînés 64x32, Pi 4.
"""

import threading
import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions

LARGEUR_CANVAS = 64
HAUTEUR_CANVAS = 32

# Point de départ fixe : bas, au milieu des deux panneaux chaînés
DEPART = (LARGEUR_CANVAS // 2, HAUTEUR_CANVAS - 1)  # (colonne, ligne)

COULEUR_CHEMIN = (255, 140, 0)      # orange, pour le trajet
COULEUR_DESTINATION = (0, 255, 0)   # vert, pour repérer clairement l'arrivée
DELAI_ENTRE_POINTS = 0.03           # secondes entre chaque point de l'animation

_matrix = None
_canvas = None
_verrou_affichage = threading.Lock()  # évite que 2 chemins s'affichent en même temps


def _creer_options():
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


def initialiser():
    """À appeler UNE SEULE FOIS au démarrage (dans main.py), avant tout
    abonnement. Créer plusieurs fois un RGBMatrix ferait planter ou
    entrerait en conflit avec le GPIO déjà réservé."""
    global _matrix, _canvas
    if _matrix is not None:
        return  # déjà initialisé, on ne recrée pas
    _matrix = RGBMatrix(options=_creer_options())
    _canvas = _matrix.CreateFrameCanvas()


def arreter():
    """À appeler à la fermeture propre de l'application pour éteindre
    proprement les panneaux."""
    if _matrix is not None:
        _matrix.Clear()


def calculer_chemin(x0, y0, x1, y1):
    """Bresenham : liste de points (colonne, ligne) formant une ligne
    droite. Version temporaire avant le vrai pathfinding par graphe de
    corridors — remplacer cette fonction suffira à brancher la vraie
    logique plus tard sans toucher au reste du module."""
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


def _dessiner_chemin(points):
    """Anime le chemin point par point (le tracé se construit
    progressivement). Le dernier point (la salle) est mis en évidence
    dans une couleur différente. Protégé par un verrou pour éviter que
    deux chemins ne se dessinent en même temps sur le même canvas."""
    global _canvas
    with _verrou_affichage:
        _canvas.Clear()
        _canvas = _matrix.SwapOnVSync(_canvas)
        for i, (x, y) in enumerate(points):
            est_dernier_point = (i == len(points) - 1)
            r, g, b = COULEUR_DESTINATION if est_dernier_point else COULEUR_CHEMIN
            _canvas.SetPixel(x, y, r, g, b)
            _canvas = _matrix.SwapOnVSync(_canvas)
            time.sleep(DELAI_ENTRE_POINTS)


def on_destination_reconnue(destination_id, dest, source):
    """Signature attendue par core.ajouter_abonne : appelée automatiquement
    à chaque destination reconnue, voix ou tactile confondus."""
    if _matrix is None:
        print("[led] initialiser() n'a pas été appelé, chemin LED ignoré.")
        return

    if dest is None or dest.get("ligne_led") is None or dest.get("colonne_led") is None:
        print(f"[led] Pas de coordonnées LED pour '{destination_id}', "
              f"chemin non affiché.")
        return

    arrivee = (dest["colonne_led"], dest["ligne_led"])
    print(f"[led] Chemin vers {destination_id} : {DEPART} -> {arrivee}")
    points = calculer_chemin(DEPART[0], DEPART[1], arrivee[0], arrivee[1])
    # Thread séparé pour ne jamais bloquer l'appelant (thread voix ou
    # thread principal Kivy pour le tactile).
    threading.Thread(target=_dessiner_chemin, args=(points,), daemon=True).start()