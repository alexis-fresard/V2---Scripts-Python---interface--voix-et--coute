#!/usr/bin/env python3
"""
Test de faisabilité : chemin LED en fonction de la recherche utilisateur
==========================================================================

Objectif de ce script :
    Valider la chaîne complète, de bout en bout, sur le vrai matériel :
        1) L'utilisateur "cherche" une destination (ici saisie texte, pour
           simuler le résultat que donnerait la reconnaissance vocale Vosk)
        2) On retrouve la destination correspondante (matching par alias,
           logique Counter comme dans le projet principal)
        3) On calcule le chemin le plus court depuis l'entrée (BFS)
        4) On allume ce chemin sur les panneaux LED

IMPORTANT — à adapter avant tout test réel :
    - GRAPHE_EXEMPLE ci-dessous est un PLACEHOLDER. Les coordonnées ne
      correspondent à aucun vrai couloir du bâtiment B. Il sert uniquement
      à prouver que la mécanique (BFS + dessin LED) fonctionne.
    - CHAIN_LENGTH / PARALLEL / HARDWARE_MAPPING doivent correspondre à ton
      branchement réel (voir "Installation et branchement.docx" : ordre des
      panneaux via TOP-P0, sens du chaînage).
    - Ce script tourne en root sur le Raspberry Pi (comme les démos du doc) :
          sudo python3 test_chemin_led.py
      Sur un PC sans la lib rgbmatrix installée, il bascule automatiquement
      en mode SIMULATION (aperçu texte + image) pour que tu puisses quand
      même vérifier la logique de matching et de pathfinding.
"""

import re
import unicodedata
from collections import Counter, deque

# ---------------------------------------------------------------------------
# 1) Tentative d'import de la bibliothèque matérielle (rpi-rgb-led-matrix)
# ---------------------------------------------------------------------------
try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    MATRICE_DISPONIBLE = True
except ImportError:
    MATRICE_DISPONIBLE = False
    print("[Info] Bibliothèque 'rgbmatrix' non trouvée -> mode SIMULATION activé.\n")

# ---------------------------------------------------------------------------
# 2) Configuration matérielle (2 panneaux 32x32 chaînés horizontalement)
# ---------------------------------------------------------------------------
PANEL_ROWS = 32
PANEL_COLS = 32
CHAIN_LENGTH = 2          # 2 panneaux chaînés -> canvas de 64x32
PARALLEL = 1
HARDWARE_MAPPING = "regular"        # correspond à la démo C qui fonctionne (voir doc install)
SLOWDOWN_GPIO = 4                   # valeur utilisée dans les démos du doc (Pi 4)
DESACTIVER_PULSE_MATERIEL = True    # équivaut au flag --led-no-hardware-pulse de la démo

LARGEUR_CANVAS = PANEL_COLS * CHAIN_LENGTH   # 64
HAUTEUR_CANVAS = PANEL_ROWS * PARALLEL       # 32

# ---------------------------------------------------------------------------
# 3) GRAPHE D'EXEMPLE — À REMPLACER PAR LA VRAIE CARTE DU BÂTIMENT
#    Chaque nœud = un point-clé du chemin, avec sa position en pixel (x, y)
#    sur le canvas LED (0..63, 0..31).
# ---------------------------------------------------------------------------
NOEUDS = {
    "ENTREE":      (1, 16),
    "COULOIR_1":   (16, 16),
    "COULOIR_2":   (32, 16),
    "COULOIR_3":   (48, 16),
    "C2-07":       (48, 4),
    "C2-08":       (48, 28),
    "SANITAIRES":  (60, 16),
}

ARETES = {
    "ENTREE":     ["COULOIR_1"],
    "COULOIR_1":  ["ENTREE", "COULOIR_2"],
    "COULOIR_2":  ["COULOIR_1", "COULOIR_3"],
    "COULOIR_3":  ["COULOIR_2", "C2-07", "C2-08", "SANITAIRES"],
    "C2-07":      ["COULOIR_3"],
    "C2-08":      ["COULOIR_3"],
    "SANITAIRES": ["COULOIR_3"],
}

DEPART = "ENTREE"

# Destinations "cherchables" par la voix/texte -> nœud du graphe
# (même esprit que Destinations.csv : id + alias)
DESTINATIONS = {
    "C2-07":      {"noeud": "C2-07",      "alias": ["salle c2 07", "c2 07", "c deux zero sept"]},
    "C2-08":      {"noeud": "C2-08",      "alias": ["salle c2 08", "c2 08", "c deux zero huit"]},
    "SANITAIRES": {"noeud": "SANITAIRES", "alias": ["toilettes", "sanitaires", "wc"]},
}

# Mots à ignorer lors du matching (on garde "un"/"une" comme le préconisent
# les retours d'expérience du projet, sinon les salles finissant par "1" cassent)
MOTS_IGNORES = {"salle", "le", "la", "les", "de", "du"}


def normaliser(texte: str):
    """Minuscule, sans accents, découpé en mots -> liste de mots utiles."""
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    mots = re.findall(r"\w+", texte.lower())
    return [m for m in mots if m not in MOTS_IGNORES]


def trouver_destination(recherche: str):
    """Retourne l'id de destination dont les alias correspondent le mieux
    à la recherche utilisateur, via un score de multiset (Counter)."""
    mots_recherche = Counter(normaliser(recherche))
    meilleur_id, meilleur_score = None, 0
    for dest_id, infos in DESTINATIONS.items():
        for alias in infos["alias"]:
            mots_alias = Counter(normaliser(alias))
            # score = nb de mots communs (en tenant compte des répétitions)
            score = sum((mots_recherche & mots_alias).values())
            if score > meilleur_score:
                meilleur_score, meilleur_id = score, dest_id
    return meilleur_id if meilleur_score > 0 else None


def bfs_chemin(depart: str, arrivee: str):
    """Plus court chemin (en nombre de segments) entre deux nœuds du graphe."""
    if depart == arrivee:
        return [depart]
    visites = {depart}
    file_attente = deque([[depart]])
    while file_attente:
        chemin = file_attente.popleft()
        dernier = chemin[-1]
        for voisin in ARETES.get(dernier, []):
            if voisin in visites:
                continue
            nouveau_chemin = chemin + [voisin]
            if voisin == arrivee:
                return nouveau_chemin
            visites.add(voisin)
            file_attente.append(nouveau_chemin)
    return None  # pas de chemin trouvé


def dessiner_chemin_matrice(matrix, chemin_noeuds, couleur=(0, 255, 0)):
    """Dessine le chemin sur les vrais panneaux LED, segment par segment,
    pour un petit effet d'animation."""
    canvas = matrix.CreateFrameCanvas()
    couleur_led = graphics.Color(*couleur)
    canvas.Clear()
    for i in range(len(chemin_noeuds) - 1):
        x1, y1 = NOEUDS[chemin_noeuds[i]]
        x2, y2 = NOEUDS[chemin_noeuds[i + 1]]
        graphics.DrawLine(canvas, x1, y1, x2, y2, couleur_led)
        canvas = matrix.SwapOnVSync(canvas)
    # Met en évidence la destination finale (petit carré plus lumineux)
    xf, yf = NOEUDS[chemin_noeuds[-1]]
    couleur_dest = graphics.Color(255, 0, 0)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            canvas.SetPixel(xf + dx, yf + dy, *[c for c in (255, 0, 0)])
    canvas = matrix.SwapOnVSync(canvas)


def dessiner_chemin_simulation(chemin_noeuds):
    """Mode sans matériel : aperçu texte + image (si Pillow dispo)."""
    print("Aperçu du canvas (X = chemin, D = destination) :")
    grille = [["." for _ in range(LARGEUR_CANVAS)] for _ in range(HAUTEUR_CANVAS)]
    for i in range(len(chemin_noeuds) - 1):
        x1, y1 = NOEUDS[chemin_noeuds[i]]
        x2, y2 = NOEUDS[chemin_noeuds[i + 1]]
        # tracé simple (horizontal puis vertical) pour l'aperçu texte
        for x in range(min(x1, x2), max(x1, x2) + 1):
            grille[y1][x] = "X"
        for y in range(min(y1, y2), max(y1, y2) + 1):
            grille[y2][x2] = "X"
    xf, yf = NOEUDS[chemin_noeuds[-1]]
    grille[yf][xf] = "D"
    for ligne in grille:
        print("".join(ligne))

    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (LARGEUR_CANVAS, HAUTEUR_CANVAS), "black")
        draw = ImageDraw.Draw(img)
        for i in range(len(chemin_noeuds) - 1):
            draw.line([NOEUDS[chemin_noeuds[i]], NOEUDS[chemin_noeuds[i + 1]]], fill=(0, 255, 0))
        draw.ellipse([xf - 1, yf - 1, xf + 1, yf + 1], fill=(255, 0, 0))
        img = img.resize((LARGEUR_CANVAS * 10, HAUTEUR_CANVAS * 10), Image.NEAREST)
        img.save("apercu_chemin_led.png")
        print("\n[Info] Aperçu image sauvegardé : apercu_chemin_led.png")
    except ImportError:
        pass


def initialiser_matrice():
    options = RGBMatrixOptions()
    options.rows = PANEL_ROWS
    options.cols = PANEL_COLS
    options.chain_length = CHAIN_LENGTH
    options.parallel = PARALLEL
    options.hardware_mapping = HARDWARE_MAPPING
    options.gpio_slowdown = SLOWDOWN_GPIO
    options.disable_hardware_pulsing = DESACTIVER_PULSE_MATERIEL
    return RGBMatrix(options=options)


def main():
    print("=== Test de faisabilité : recherche -> chemin -> LED ===")
    print(f"Canvas LED : {LARGEUR_CANVAS}x{HAUTEUR_CANVAS} px ({CHAIN_LENGTH} panneau(x) {PANEL_COLS}x{PANEL_ROWS})")
    print("Destinations d'exemple : C2-07, C2-08, sanitaires\n")

    recherche = input("Destination recherchée (simule la reco vocale) : ")
    dest_id = trouver_destination(recherche)

    if dest_id is None:
        print("Aucune destination correspondante trouvée.")
        return

    noeud_arrivee = DESTINATIONS[dest_id]["noeud"]
    chemin = bfs_chemin(DEPART, noeud_arrivee)

    if chemin is None:
        print(f"Destination '{dest_id}' trouvée mais aucun chemin dans le graphe.")
        return

    print(f"Destination trouvée : {dest_id}")
    print(f"Chemin (BFS) : {' -> '.join(chemin)}")

    if MATRICE_DISPONIBLE:
        matrix = initialiser_matrice()
        dessiner_chemin_matrice(matrix, chemin)
        input("Chemin affiché sur les panneaux. Appuyer sur Entrée pour quitter...")
    else:
        dessiner_chemin_simulation(chemin)


if __name__ == "__main__":
    main()