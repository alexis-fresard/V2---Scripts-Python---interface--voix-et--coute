# Borne Divtec — Panneau d'orientation interactif

Borne d'orientation interactive pour l'entrée du bâtiment B (Division
technique, Divtec). L'utilisateur demande une destination à la voix ou
au toucher, et la borne y répond (affichage à l'écran, à terme
allumage LED du chemin correspondant).

## Fonctionnalités

- **Reconnaissance vocale hors-ligne** (français) via Vosk + sounddevice
- **Interface tactile** (Kivy) : grille de destinations colorées, barre
  de recherche, filtres par étage, écran de veille avec horloge
- **Matching flou** partagé entre la voix et la recherche tactile
  (mêmes alias, même logique)
- **Fonctionnement autonome et sans supervision** : dégradation
  gracieuse si le micro, le modèle Vosk ou une icône sont absents —
  l'appli ne plante pas
- **Panneaux LED matriciels** (HUB75) pour l'affichage physique du
  chemin (pathfinding à venir)

## Matériel

- Raspberry Pi 4 (8 Go de RAM) — privilégié au Pi 5 (incompatibilités
  GPIO avec `rpi-rgb-led-matrix` sur le RP1)
- Adafruit RGB Matrix Bonnet/HAT
- Panneaux LED matriciels RVB (HUB75)
- Microphone USB (ReSpeaker USB Mic Array recommandé)
- Écran tactile
- Alimentation 5V dédiée pour les panneaux LED

## Structure du projet

```
Borne/
├── main.py                 # Point d'entrée : orchestre écran + voix
├── interface_tactile.py    # Interface Kivy (écran tactile)
├── voix.py                 # Reconnaissance vocale (Vosk + sounddevice)
├── core.py                 # Logique commune : destinations, matching, callbacks
├── Destinations.csv         # Liste des salles/destinations (id;aliases;etage)
└── icones/                 # Icônes PNG des cartes destination + micro
```

## Installation

```bash
pip3 install kivy sounddevice vosk pyttsx3
```

Télécharger le modèle vocal `vosk-model-small-fr-0.22` et le placer
dans le même dossier que les scripts.

## Lancement

```bash
# Interface tactile seule (autonome, sans micro requis)
python3 interface_tactile.py

# Écran + micro orchestrés ensemble (bouton poussoir / détection de présence)
python3 main.py

# Reconnaissance vocale seule, mode clavier (sans micro ni Vosk)
python3 voix.py test

# Reconnaissance vocale seule, mode micro réel
python3 voix.py
```

En production, le lancement se fait via un service **systemd**
(`divtec.service`), avec démarrage/arrêt programmés
(`divtec-start.timer` / `divtec-stop.timer`).

## Points d'attention connus

- **Timing de démarrage systemd** : le service peut apparaître `dead`
  au boot si `graphical.target` est atteint avant que le serveur X ne
  soit prêt (piste : script `wait-for-x.sh` en pre-start)
- **Micro parfois non détecté** (`Error querying device -1`) — l'appli
  se rabat alors sur le mode tactile seul, sans planter
- **Chemins relatifs** : toujours utiliser `BASE_DIR` (basé sur
  `__file__`) pour localiser `Destinations.csv` et le modèle Vosk,
  quel que soit le répertoire de lancement

## À venir

- Pathfinding (BFS/Dijkstra/A*) depuis les deux entrées vers chaque
  destination, avec cache au démarrage
- Allumage effectif des panneaux LED selon le chemin calculé
- Contrôle d'alimentation de l'écran (`xset dpms`) synchronisé avec les
  horaires d'ouverture du bâtiment

  Pour toute informations supplémentaires, contacter Alexis Frésard