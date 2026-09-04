#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borne interactive - Écran tactile (Kivy)
==========================================

Interface tactile "grille de boutons colorés" habillée dans un style
clair/moderne, avec un peu de relief (ombres douces sur les cartes,
boutons et barre de recherche) et un contraste de texte calculé
automatiquement sur chaque carte destination (voir contraste_texte) pour
rester lisible quelle que soit la couleur choisie dans le CSV : une
barre de recherche en haut (réutilise le même
matching flou que la voix, core.trouver_destination), un gros bouton
microphone central pour déclencher l'écoute directement depuis l'écran
(sans avoir besoin du bouton poussoir physique ni de main.py), une
rangée de filtres par étage sous forme de pastilles, et une grille de
cartes représentant les destinations, colorées selon la colonne
"couleur" du CSV (pour se rapprocher du style du panneau physique).

Quand l'utilisateur tape une recherche, touche une destination OU
appuie sur le micro et parle, on appelle
core.on_destination_reconnue(..., source=...) — exactement la même
fonction, peu importe la source. Ça garantit la même réponse vocale et
le même futur allumage LED, peu importe comment la destination a été
demandée.

Micro
-----
Le bouton micro central lance voix.ecouter(...) (voir voix.py) dans un
thread séparé, pour ne jamais geler l'interface tactile :
    - appui -> le bouton devient rouge et pulse plus vite, la borne
      écoute (via Vosk) jusqu'à ce qu'une destination soit reconnue,
      qu'on ré-appuie sur le bouton, ou qu'un délai (DUREE_MAX_ECOUTE)
      soit dépassé sans résultat ;
    - une destination reconnue à la voix arrête automatiquement
      l'écoute (comme un push-to-talk) et surligne la carte
      correspondante si elle est visible à l'écran.

sounddevice/vosk ne sont importés que lorsqu'on appuie réellement sur
le micro (import différé dans voix.ecouter) : l'écran fonctionne donc
toujours en mode autonome même si le micro USB ou le modèle Vosk ne
sont pas encore installés/branchés - on aura juste un message d'erreur
au lieu d'un plantage.

Installation :
    pip3 install kivy
    pip3 install sounddevice vosk pyttsx3   # nécessaires pour le micro

Lancement (autonome) :
    python3 interface_tactile.py

Pour lancer écran + micro orchestrés ensemble (ex. avec bouton poussoir
physique / détection de présence), voir main.py.

Écran de veille & horloge
--------------------------
Une horloge (heure + date, en français, sans dépendre de la locale
système) est affichée en haut de l'écran. Après DUREE_AVANT_VEILLE
secondes sans aucune interaction (tactile, recherche ou micro), un
écran de veille plein cadre s'affiche (gros horloge + invite à toucher
ou parler) plutôt que de laisser la grille complète comme premier
contact. N'importe quel toucher sur cet écran le referme.

Icônes de destination
----------------------
Chaque carte affiche un petit badge dont le type (bureau, cafétéria,
bibliothèque, santé, sanitaires, ou 'salle' par défaut) est déduit par
mots-clés depuis l'id/les alias de la destination (voir
deduire_type_icone) — aucune colonne CSV supplémentaire n'est
nécessaire. L'image affichée vient d'un fichier PNG dans le dossier
DOSSIER_ICONES (voir FICHIERS_ICONES) : mets-y salle.png, bureau.png,
cafeteria.png, bibliotheque.png, sante.png et sanitaires.png. Le gros
bouton micro cherche de la même façon icones/micro.png (voir
FICHIER_ICONE_MICRO). Un fichier manquant n'empêche pas l'appli de
tourner : le badge/bouton concerné reste juste un simple disque en
attendant.
"""

import os
import threading
import time
from datetime import datetime

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import NumericProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle

import core
import voix

# ---------------------------------------------------------------------------
# THÈME (palette sombre / moderne)
# ---------------------------------------------------------------------------

COULEUR_FOND = (0.96, 0.97, 0.98, 1)              # fond clair (quasi blanc)
COULEUR_FOND_CARTE = (1, 1, 1, 1)                 # cartes/panneaux blancs
COULEUR_TEXTE = (0.10, 0.11, 0.14, 1)              # texte sombre
COULEUR_TEXTE_ATTENUE = (0.45, 0.48, 0.55, 1)      # texte sombre atténué

COULEUR_ACCENT = (0.30, 0.62, 0.98, 1)            # bleu accent (recherche, filtre actif)
COULEUR_ALERTE = (0.95, 0.55, 0.20, 1)

COULEUR_FILTRE_ACTIF = COULEUR_ACCENT
COULEUR_FILTRE_INACTIF = (0.90, 0.91, 0.93, 1)

COULEUR_MICRO_IDLE = (0.30, 0.62, 0.98, 1)        # bleu : prêt à écouter
COULEUR_MICRO_ECOUTE = (0.92, 0.35, 0.32, 1)      # rouge : écoute en cours
COULEUR_MICRO_ERREUR = (0.80, 0.20, 0.20, 1)      # rouge foncé : micro indisponible

COULEUR_OMBRE = (0.05, 0.07, 0.11)                # base des ombres portées (mélangée avec de l'alpha)
COULEUR_BORDURE = (0.88, 0.89, 0.92, 1)           # liseré discret (barre de recherche, séparateur d'en-tête)

DUREE_MAX_ECOUTE = 12   # secondes avant abandon automatique si rien n'est compris
DUREE_AVANT_VEILLE = 60  # secondes d'inactivité avant l'écran de veille

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# Icônes de destination : chaque type pointe vers un fichier PNG à mettre
# dans DOSSIER_ICONES (à côté de ce script). Si le fichier n'existe pas
# encore, le badge reste un simple disque (pas de plantage) - pratique tant
# que tu n'as pas fini de télécharger/nommer tous les fichiers.
DOSSIER_ICONES = "icones"
FICHIERS_ICONES = {
    "salle": "classroom.png",
    "bureau": "office.png",
    "cafeteria": "restaurant.png",
    "sport": "sport.png",
    "sante": "heal.png",
    "sanitaires": "wc.png",
    #"conciergerie": "cleaning.png",
}


def hex_vers_rgba(couleur_hex: str):
    """Convertit '#C0407A' en tuple Kivy (r, g, b, 1), valeurs 0-1."""
    couleur_hex = couleur_hex.lstrip("#")
    try:
        r = int(couleur_hex[0:2], 16) / 255
        g = int(couleur_hex[2:4], 16) / 255
        b = int(couleur_hex[4:6], 16) / 255
        return (r, g, b, 1)
    except (ValueError, IndexError):
        return hex_vers_rgba(core.COULEUR_PAR_DEFAUT)


def assombrir_couleur(rgba, facteur=0.8):
    """Assombrit une couleur (retour tactile visuel à l'appui)."""
    r, g, b, a = rgba
    return (r * facteur, g * facteur, b * facteur, a)


def contraste_texte(couleur_rgba):
    """Choisit du texte blanc ou (quasi) noir selon la luminosité perçue de
    couleur_rgba, pour rester lisible même si le CSV définit une couleur
    de destination très claire (ex. jaune pâle) sur laquelle du texte
    blanc fixe deviendrait illisible."""
    r, g, b = couleur_rgba[0], couleur_rgba[1], couleur_rgba[2]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (1, 1, 1, 1) if luminance < 0.6 else (0.10, 0.11, 0.14, 1)


def libelle_etage(etage) -> str:
    if etage is None:
        return "?"
    if etage == 0:
        return "RDC"
    if etage == 1:
        return "1er"
    if etage == 4:
        return "Bât. A"
    return f"{etage}e"


def formater_date(maintenant: datetime) -> str:
    """ex. 'vendredi 28 août' — en dur en français pour ne pas dépendre
    d'une locale système qui pourrait ne pas être installée sur la borne."""
    return f"{JOURS_FR[maintenant.weekday()]} {maintenant.day} {MOIS_FR[maintenant.month - 1]}"


def deduire_type_icone(dest) -> str:
    """Déduit un type d'icône (voir FICHIERS_ICONES) à partir de l'id et des
    alias d'une destination, par mots-clés — aucune colonne CSV
    supplémentaire n'est nécessaire. 'salle' (porte générique) est le
    repli par défaut si aucun mot-clé ne correspond."""
    texte = core.normaliser(dest["id"] + " " + " ".join(dest["aliases"]))
    regles = (
        (("wc", "toilette", "sanitaire"), "sanitaires"),
        (("cafet", "cafeteria", "cantine", "restaurant", "refectoire"), "cafeteria"),
        (("sport","gym"), "sport"),
        (("infirmerie", "sante", "medical", "secours"), "sante"),
        (("secretariat", "direction", "bureau", "administration"), "bureau"),
        #(("concièrge"), "conciergerie"),
    )
    for mots_cles, type_icone in regles:
        if any(mot in texte for mot in mots_cles):
            return type_icone
    return "salle"


# ---------------------------------------------------------------------------
# WIDGETS RÉUTILISABLES (rectangles arrondis dessinés en canvas ; seul le
# badge d'icône des cartes destination charge un fichier PNG, voir
# IconeBadge/DOSSIER_ICONES ci-dessous)
# ---------------------------------------------------------------------------

class _CarteBase(ButtonBehavior, Widget):
    """Base commune : ombre douce (2 couches semi-transparentes décalées
    vers le bas, pour un effet de flou de pauvre sans shader) + rectangle
    arrondi + label centré, avec redessin automatique au changement de
    taille/position (Kivy ne fait pas de layout automatique des enfants
    d'un Widget nu). L'ombre donne du relief aux cartes/pastilles/boutons
    plutôt qu'un aplat qui se fond dans le fond clair de l'écran."""

    def __init__(self, texte="", couleur=None, rayon=16, taille_police="18sp",
                 police_grasse=True, couleur_texte=(1, 1, 1, 1), ombre=True,
                 **kwargs):
        super().__init__(**kwargs)
        couleur = couleur or COULEUR_FOND_CARTE
        self.rayon = rayon
        self.avec_ombre = ombre
        with self.canvas.before:
            if ombre:
                self._c_ombre_loin = Color(*COULEUR_OMBRE, 0.045)
                self._ombre_loin = RoundedRectangle(radius=[rayon + 4])
                self._c_ombre_pres = Color(*COULEUR_OMBRE, 0.09)
                self._ombre_pres = RoundedRectangle(radius=[rayon + 2])
            self._c_fond = Color(*couleur)
            self._fond = RoundedRectangle(radius=[rayon])
        self.label = Label(text=texte, bold=police_grasse, font_size=taille_police,
                            color=couleur_texte)
        self.add_widget(self.label)
        self.bind(pos=self._redessiner, size=self._redessiner)
        self._redessiner()

    def _redessiner(self, *args):
        if self.avec_ombre:
            self._ombre_loin.pos = (self.x, self.y - 6)
            self._ombre_loin.size = self.size
            self._ombre_loin.radius = [min(self.rayon + 4, self.height / 2, self.width / 2)]
            self._ombre_pres.pos = (self.x, self.y - 2)
            self._ombre_pres.size = self.size
            self._ombre_pres.radius = [min(self.rayon + 2, self.height / 2, self.width / 2)]
        self._fond.pos = self.pos
        self._fond.size = self.size
        self._fond.radius = [min(self.rayon, self.height / 2, self.width / 2)]
        self.label.pos = self.pos
        self.label.size = self.size
        self.label.text_size = self.size
        self.label.halign = "center"
        self.label.valign = "middle"

    def definir_couleur(self, couleur):
        self._c_fond.rgba = couleur


class IconeBadge(Widget):
    """Petit badge rond (fond semi-transparent) affiché dans le coin d'une
    carte destination, contenant l'image PNG correspondant au type de
    destination (voir FICHIERS_ICONES / deduire_type_icone). Si le fichier
    n'existe pas encore dans DOSSIER_ICONES, le badge reste un simple
    disque - pas de plantage tant que les icônes ne sont pas toutes en
    place."""

    def __init__(self, type_icone="salle", **kwargs):
        super().__init__(**kwargs)
        self.type_icone = type_icone if type_icone in FICHIERS_ICONES else "salle"
        with self.canvas.before:
            self._c_fond = Color(0, 0, 0, 0.28)
            self._fond = Ellipse()
            self._c_anneau = Color(1, 1, 1, 0.55)
            self._anneau = Line(width=1.1)

        self.image = None
        chemin = os.path.join(DOSSIER_ICONES, FICHIERS_ICONES[self.type_icone])
        if os.path.isfile(chemin):
            self.image = Image(source=chemin, allow_stretch=True, keep_ratio=True)
            self.add_widget(self.image)
        else:
            print(f"[icônes] Fichier introuvable : '{chemin}' (badge laissé vide).")

        self.bind(pos=self._redessiner, size=self._redessiner)
        self._redessiner()

    def _redessiner(self, *args):
        self._fond.pos = self.pos
        self._fond.size = self.size
        self._anneau.circle = (self.center_x, self.center_y, self.width / 2 - 0.6)
        if self.image is not None:
            marge = self.width * 0.18
            self.image.pos = (self.x + marge, self.y + marge)
            self.image.size = (self.width - 2 * marge, self.height - 2 * marge)


class EtiquetteEtage(_CarteBase):
    """Petite étiquette posée dans le coin bas-droit d'une carte
    destination, rappelant l'étage en texte. Utile pour rester lisible
    même sans distinguer les couleurs (daltonisme, luminosité du hall...)
    plutôt que de se fier uniquement à la pastille de filtre en haut de
    l'écran."""

    def __init__(self, texte, **kwargs):
        super().__init__(texte=texte, couleur=(0, 0, 0, 0.30), rayon=8,
                          taille_police="12sp", couleur_texte=(1, 1, 1, 1),
                          ombre=False, **kwargs)


class CarteDestination(_CarteBase):
    """Carte tactile représentant une destination : rectangle arrondi
    coloré (couleur reprise du CSV, comme sur le panneau physique) avec
    un léger assombrissement au toucher pour un retour tactile clair, un
    badge d'icône (voir IconeBadge/deduire_type_icone) et une étiquette
    d'étage pour rester lisible aussi sans se fier uniquement à la
    couleur. Le texte principal bascule automatiquement en noir ou blanc
    (voir contraste_texte) selon la couleur reçue du CSV."""

    def __init__(self, texte, couleur, type_icone="salle", etage_texte=None, **kwargs):
        super().__init__(texte=texte, couleur=couleur, rayon=20,
                          taille_police="21sp",
                          couleur_texte=contraste_texte(couleur), **kwargs)
        self.couleur_normale = couleur
        self.couleur_appui = assombrir_couleur(couleur, 0.78)
        self.badge = IconeBadge(type_icone=type_icone, size_hint=(None, None),
                                 size=(34, 34))
        self.add_widget(self.badge)
        self.etiquette_etage = None
        if etage_texte:
            self.etiquette_etage = EtiquetteEtage(etage_texte, size_hint=(None, None),
                                                   size=(42, 22))
            self.add_widget(self.etiquette_etage)
        self._redessiner()  # repositionne tout, badge + étiquette inclus

    def _redessiner(self, *args):
        super()._redessiner(*args)
        if hasattr(self, "badge"):
            marge = 9
            self.badge.pos = (self.x + marge, self.top - marge - self.badge.height)
        if getattr(self, "etiquette_etage", None) is not None:
            marge = 8
            self.etiquette_etage.pos = (self.right - marge - self.etiquette_etage.width,
                                         self.y + marge)

    def on_state(self, instance, valeur):
        self.definir_couleur(self.couleur_appui if valeur == "down" else self.couleur_normale)

    def surligner(self):
        """Flash blanc bref utilisé pour confirmer une reconnaissance
        (vocale ou tactile)."""
        self.definir_couleur((1, 1, 1, 1))
        Clock.schedule_once(lambda dt: self.definir_couleur(self.couleur_normale), 1.2)


class PastilleEtage(_CarteBase):
    """Filtre par étage sous forme de pastille (pill), façon chip
    d'interface tactile moderne, plutôt qu'un bouton rectangulaire."""

    def __init__(self, texte, **kwargs):
        super().__init__(texte=texte, couleur=COULEUR_FILTRE_INACTIF, rayon=999,
                          taille_police="17sp", couleur_texte=COULEUR_TEXTE_ATTENUE,
                          **kwargs)
        self.actif = False

    def definir_actif(self, actif):
        self.actif = actif
        self.definir_couleur(COULEUR_FILTRE_ACTIF if actif else COULEUR_FILTRE_INACTIF)
        self.label.color = (1, 1, 1, 1) if actif else COULEUR_TEXTE_ATTENUE


class BoutonAction(_CarteBase):
    """Bouton d'action générique, style accent (ex. « Rechercher »)."""

    def __init__(self, texte, **kwargs):
        super().__init__(texte=texte, couleur=COULEUR_ACCENT, rayon=14,
                          taille_police="18sp", **kwargs)
        self.couleur_normale = COULEUR_ACCENT
        self.couleur_appui = assombrir_couleur(COULEUR_ACCENT, 0.8)

    def on_state(self, instance, valeur):
        self.definir_couleur(self.couleur_appui if valeur == "down" else self.couleur_normale)


class Diviseur(Widget):
    """Fine ligne horizontale utilisée comme séparateur visuel discret
    (ex. sous l'en-tête), pour structurer l'écran plutôt que de laisser
    un simple espace vide entre les zones."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", 1)
        super().__init__(**kwargs)
        with self.canvas:
            Color(*COULEUR_BORDURE)
            self._trait = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redessiner, size=self._redessiner)

    def _redessiner(self, *args):
        self._trait.pos = self.pos
        self._trait.size = self.size


class ConteneurArrondi(BoxLayout):
    """BoxLayout classique mais avec un fond arrondi, une ombre douce et un
    fin liseré dessinés en canvas, pour un rendu plus « élevé » que les
    rectangles Kivy par défaut (utilisé pour la barre de recherche)."""

    def __init__(self, couleur_fond=None, rayon=16, ombre=True, **kwargs):
        super().__init__(**kwargs)
        self.rayon = rayon
        self.avec_ombre = ombre
        with self.canvas.before:
            if ombre:
                Color(*COULEUR_OMBRE, 0.045)
                self._ombre_loin = RoundedRectangle(radius=[rayon + 4])
                Color(*COULEUR_OMBRE, 0.08)
                self._ombre_pres = RoundedRectangle(radius=[rayon + 2])
            self._c = Color(*(couleur_fond or COULEUR_FOND_CARTE))
            self._rect = RoundedRectangle(radius=[rayon])
            Color(*COULEUR_BORDURE)
            self._bordure = Line(width=1.1, rounded_rectangle=(0, 0, 0, 0, rayon))
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *args):
        if self.avec_ombre:
            self._ombre_loin.pos = (self.x, self.y - 6)
            self._ombre_loin.size = self.size
            self._ombre_pres.pos = (self.x, self.y - 2)
            self._ombre_pres.size = self.size
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._bordure.rounded_rectangle = (self.x, self.y, self.width, self.height, self.rayon)


FICHIER_ICONE_MICRO = os.path.join(DOSSIER_ICONES, "micro.png")
FICHIER_ICONE_RECHERCHE = os.path.join(DOSSIER_ICONES, "loupe.png")

class BoutonMicro(ButtonBehavior, Widget):
    """Gros bouton microphone central, façon talkie-walkie : au repos il
    "respire" doucement en bleu pour inviter au toucher ; pendant
    l'écoute il devient rouge et pulse plus vite pour un retour visuel
    sans ambiguïté, visible même de loin sur le panneau. L'icône affichée
    dessus vient de FICHIER_ICONE_MICRO (icones/micro.png) ; si le fichier
    n'existe pas encore, le bouton reste un simple disque coloré (pas de
    plantage)."""

    pulsation = NumericProperty(0.0)  # 0..1, piloté par une Animation en boucle

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (172, 172)  # valeur par défaut, ajustée ensuite par le parent
        self.etat = "idle"
        with self.canvas.before:
            self._c_ombre = Color(*COULEUR_OMBRE, 0.10)
            self._ombre = Ellipse()
            self._c_halo = Color(*COULEUR_MICRO_IDLE, 0.22)
            self._halo = Ellipse()
            self._c_disque = Color(*COULEUR_MICRO_IDLE)
            self._disque = Ellipse()

        self.image = None
        if os.path.isfile(FICHIER_ICONE_MICRO):
            self.image = Image(source=FICHIER_ICONE_MICRO, allow_stretch=True,
                                keep_ratio=True)
            self.add_widget(self.image)
        else:
            print(f"[icônes] Fichier introuvable : '{FICHIER_ICONE_MICRO}' "
                  f"(bouton micro laissé sans icône).")

        self.bind(pos=self._redessiner, size=self._redessiner,
                  pulsation=self._redessiner)
        self._redessiner()
        self._animer_pulsation()

    def _redessiner(self, *args):
        x, y = self.pos
        w, h = self.size

        etirement = 0.16 * self.pulsation
        self._halo.pos = (x - w * etirement / 2, y - h * etirement / 2)
        self._halo.size = (w * (1 + etirement), h * (1 + etirement))
        self._ombre.pos = (x, y - h * 0.05)
        self._ombre.size = (w, h)
        self._disque.pos = (x, y)
        self._disque.size = (w, h)

        if self.image is not None:
            marge = w * 0.28
            self.image.pos = (x + marge, y + marge)
            self.image.size = (w - 2 * marge, h - 2 * marge)

    def _animer_pulsation(self):
        """Boucle "respiration" manuelle (aller-retour 0 -> 1 -> 0), plus
        rapide pendant l'écoute. Relit self.etat à chaque cycle, donc la
        vitesse s'ajuste automatiquement dès que definir_etat() change
        d'état."""
        duree = 0.5 if self.etat == "ecoute" else 1.5
        cible = 1.0 if self.pulsation < 0.5 else 0.0
        anim = Animation(pulsation=cible, duration=duree, t="in_out_sine")
        anim.bind(on_complete=lambda *a: self._animer_pulsation())
        anim.start(self)

    def definir_etat(self, etat: str):
        """etat: 'idle' | 'ecoute' | 'erreur'."""
        self.etat = etat
        couleur = {
            "idle": COULEUR_MICRO_IDLE,
            "ecoute": COULEUR_MICRO_ECOUTE,
            "erreur": COULEUR_MICRO_ERREUR,
        }.get(etat, COULEUR_MICRO_IDLE)
        self._c_disque.rgba = couleur
        self._c_halo.rgba = (*couleur[:3], 0.22)


class EcranVeille(ButtonBehavior, FloatLayout):
    """Écran de veille plein cadre : affiché après DUREE_AVANT_VEILLE
    secondes d'inactivité pour ne pas laisser la grille complète comme
    premier contact. Étant ajouté par-dessus tout le reste (voir
    BorneApp._afficher_veille), il intercepte tous les touchers tant
    qu'il est visible ; n'importe quel toucher (ButtonBehavior.on_release)
    le referme, sans déclencher quoi que ce soit en-dessous."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COULEUR_FOND)
            self._fond = RoundedRectangle(radius=[0])
        self.bind(pos=self._maj_fond, size=self._maj_fond)

        self.label_horloge = Label(text="", font_size="72sp", bold=True,
                                    color=COULEUR_TEXTE,
                                    size_hint=(0.9, 0.16),
                                    pos_hint={"center_x": 0.5, "center_y": 0.58})
        self.label_date = Label(text="", font_size="24sp", color=COULEUR_TEXTE_ATTENUE,
                                 size_hint=(0.9, 0.08),
                                 pos_hint={"center_x": 0.5, "center_y": 0.47})
        self.image_centrale = Image(
            source="CEJEFDivisiontechniquenew.png",
            allow_stretch=True, keep_ratio=True,
            size_hint=(0.4, 0.25),
            pos_hint={"center_x": 0.5, "center_y": 0.75})
        self.add_widget(self.image_centrale)
        self.label_invite = Label(
            text="Bienvenue à la DIVTEC !\n\nTouchez l'écran\npour rechercher une destination",
            font_size="20sp", bold=True, color=COULEUR_ACCENT, halign="center",
            size_hint=(0.9, 0.12), pos_hint={"center_x": 0.5, "center_y": 0.30})
        self.label_invite.bind(size=lambda inst, val: setattr(inst, "text_size", val))

        for etiquette in (self.label_horloge, self.label_date, self.label_invite):
            self.add_widget(etiquette)

    def _maj_fond(self, *args):
        self._fond.pos = self.pos
        self._fond.size = self.size

    def definir_heure(self, texte_heure: str, texte_date: str):
        self.label_horloge.text = texte_heure
        self.label_date.text = texte_date


# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------

class BorneApp(App):
    title = "Borne d'orientation"

    def build(self):
        self.destinations = core.charger_destinations()
        self.etage_filtre = None  # None = "Tous"

        self._ecoute_en_cours = False
        self._arret_event = threading.Event()
        self._ecoute_thread = None
        self._dernier_activite = time.time()

        # S'abonne pour surligner une carte et arrêter l'écoute même si la
        # destination a été reconnue par la VOIX pendant que l'écran est
        # affiché.
        core.ajouter_abonne(self._sur_destination_reconnue)

        racine = BoxLayout(orientation="vertical", padding=20, spacing=12)
        with racine.canvas.before:
            Color(*COULEUR_FOND)
            self._fond_rect = RoundedRectangle(radius=[0])
        racine.bind(pos=self._maj_fond, size=self._maj_fond)

        # --- Titre + horloge ---------------------------------------------------
        bloc_titre = BoxLayout(orientation="vertical", size_hint=(1, 0.10), spacing=2)
        ligne_titre = BoxLayout(orientation="horizontal")
        titre = Label(text="Où souhaitez-vous vous rendre ?", font_size="27sp",
                       bold=True, color=COULEUR_TEXTE, halign="left", valign="middle")
        titre.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.label_horloge = Label(text="", font_size="22sp", color=COULEUR_TEXTE_ATTENUE,
                                    size_hint=(0.24, 1), halign="right", valign="middle")
        self.label_horloge.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        ligne_titre.add_widget(titre)
        ligne_titre.add_widget(self.label_horloge)
        sous_titre = Label(text="Bâtiment B \u00b7 Division technique (Divtec)",
                            font_size="14sp", color=COULEUR_TEXTE_ATTENUE,
                            halign="left", valign="top")
        sous_titre.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        bloc_titre.add_widget(ligne_titre)
        bloc_titre.add_widget(sous_titre)
        racine.add_widget(bloc_titre)
        racine.add_widget(Diviseur())

        # --- Barre de recherche ------------------------------------------------
        barre_recherche = ConteneurArrondi(orientation="horizontal", size_hint=(1, 0.09),
                                            padding=(16, 10), spacing=10)
        self.champ_recherche = TextInput(
            hint_text="Tapez une destination (ex. C2-07, secrétariat...)",
            multiline=False, font_size="20sp", padding=(12, 14),
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
            foreground_color=COULEUR_TEXTE, hint_text_color=COULEUR_TEXTE_ATTENUE,
            cursor_color=COULEUR_ACCENT,
        )
        self.champ_recherche.bind(on_text_validate=self._lancer_recherche)
        bouton_recherche = BoutonAction("Rechercher", size_hint=(0.28, 1))
        bouton_recherche.bind(on_release=self._lancer_recherche)
        if os.path.isfile(FICHIER_ICONE_RECHERCHE):
            icone_recherche = Image(source=FICHIER_ICONE_RECHERCHE, allow_stretch=True,
                                     keep_ratio=True, size_hint=(None, 1), width=26)
            barre_recherche.add_widget(icone_recherche)
        else:
            print(f"[icônes] Fichier introuvable : '{FICHIER_ICONE_RECHERCHE}' "
                  f"(loupe de recherche laissée vide).")
        barre_recherche.add_widget(self.champ_recherche)
        barre_recherche.add_widget(bouton_recherche)
        racine.add_widget(barre_recherche)

        # --- Micro (gros bouton central) ---------------------------------------
        # Le diamètre du bouton est calculé à partir de l'espace réellement
        # disponible (voir _redimensionner_micro) plutôt que fixé en dur, pour
        # ne jamais chevaucher la barre de recherche ou le libellé d'état,
        # quelle que soit la résolution de l'écran de la borne.
        zone_micro = BoxLayout(orientation="vertical", size_hint=(1, 0.24), spacing=6)
        ancre_micro = AnchorLayout(anchor_x="center", anchor_y="bottom",
                                    size_hint=(1, 0.8))
        self.bouton_micro = BoutonMicro()
        self.bouton_micro.bind(on_release=self._basculer_ecoute)
        ancre_micro.add_widget(self.bouton_micro)
        ancre_micro.bind(size=self._redimensionner_micro)
        zone_micro.add_widget(ancre_micro)
        self.label_micro_statut = Label(text="Appuyez pour parler", size_hint=(1, 0.2),
                                         font_size="17sp", color=COULEUR_TEXTE_ATTENUE)
        zone_micro.add_widget(self.label_micro_statut)
        racine.add_widget(zone_micro)

        self.label_message = Label(text="", size_hint=(1, 0.05), font_size="17sp",
                                    color=COULEUR_ALERTE)
        racine.add_widget(self.label_message)

        # --- Filtres par étage ---------------------------------------------------
        etages_presents = sorted({d["etage"] for d in self.destinations
                                   if d["etage"] is not None})
        barre_etages = BoxLayout(orientation="horizontal", size_hint=(1, 0.08),
                                  spacing=10)
        self.pastilles_etage = {}
        pastille_tous = PastilleEtage("Tous")
        pastille_tous.definir_actif(True)  # "Tous" est actif par défaut
        pastille_tous.bind(on_release=lambda inst: self._filtrer_par_etage(None))
        barre_etages.add_widget(pastille_tous)
        self.pastilles_etage[None] = pastille_tous
        for etage in etages_presents:
            pastille = PastilleEtage(libelle_etage(etage))
            pastille.bind(on_release=lambda inst, e=etage: self._filtrer_par_etage(e))
            barre_etages.add_widget(pastille)
            self.pastilles_etage[etage] = pastille
        racine.add_widget(barre_etages)

        # --- Grille des destinations (scrollable) ---------------------------------
        self.grille = GridLayout(cols=3, spacing=14, size_hint_y=None, padding=(4, 8))
        self.grille.bind(minimum_height=self.grille.setter("height"))
        defilement = ScrollView(size_hint=(1, 0.47))
        defilement.add_widget(self.grille)
        racine.add_widget(defilement)

        self._cartes_destination = {}
        self._peupler_grille()

        # --- Assemblage final : contenu + écran de veille superposable -----------
        self._racine_flottante = FloatLayout()
        self._racine_flottante.add_widget(racine)

        self._ecran_veille = EcranVeille()
        self._ecran_veille.bind(on_release=self._masquer_veille)

        # Toute interaction tactile, où qu'elle ait lieu, remet le minuteur
        # de veille à zéro (voir _signaler_activite). L'appui sur le micro
        # et une reconnaissance vocale le remettent aussi à zéro ailleurs.
        Window.bind(on_touch_down=self._signaler_activite)
        # Affichage de l'écran de veille avec F1
        Window.bind(on_key_down=self._sur_touche_clavier)
        #Window.fullscreen = True # Lance l'application en fullscreen par défaut
        Clock.schedule_interval(self._verifier_veille, 5)
        Clock.schedule_interval(self._maj_horloge, 1)
        self._maj_horloge(0)

        return self._racine_flottante

    def _maj_fond(self, instance, valeur):
        self._fond_rect.pos = instance.pos
        self._fond_rect.size = instance.size

    
    def _sur_touche_clavier(self, window, key, *args):
        if key == 283:  # touche F2
            self._afficher_veille()
    

    # -- Horloge & écran de veille ----------------------------------------------

    def _maj_horloge(self, dt):
        maintenant = datetime.now()
        self.label_horloge.text = maintenant.strftime("%H:%M")
        if self._ecran_veille.parent is not None:
            self._ecran_veille.definir_heure(maintenant.strftime("%H:%M"),
                                              formater_date(maintenant))

    def _signaler_activite(self, *args):
        self._dernier_activite = time.time()

    def _verifier_veille(self, dt):
        if self._ecoute_en_cours or self._ecran_veille.parent is not None:
            return
        if time.time() - self._dernier_activite >= DUREE_AVANT_VEILLE:
            self._afficher_veille()

    def _afficher_veille(self):
        if self._ecran_veille.parent is not None:
            return
        self._racine_flottante.add_widget(self._ecran_veille)
        self._maj_horloge(0)  # renseigne l'horloge de la veille maintenant qu'elle est affichée

    def _masquer_veille(self, *args):
        if self._ecran_veille.parent is not None:
            self._racine_flottante.remove_widget(self._ecran_veille)
        self._dernier_activite = time.time()

    def _redimensionner_micro(self, instance, taille):
        """Garde le bouton micro rond et proportionné à l'espace qui lui est
        réellement alloué (85% du plus petit côté), avec une marge pour que
        le halo de pulsation ne déborde jamais sur les widgets voisins."""
        diametre = max(90, min(taille[0], taille[1]) * 1.0)
        self.bouton_micro.size = (diametre, diametre)

    def on_stop(self):
        # Empêche un thread d'écoute de rester accroché si on ferme
        # l'application pendant que le micro est actif, et libère les
        # abonnements globaux (utile notamment si l'app est relancée dans
        # le même process, ex. tests automatisés).
        self._arret_event.set()
        Clock.unschedule(self._verifier_veille)
        Clock.unschedule(self._maj_horloge)
        Window.unbind(on_touch_down=self._signaler_activite)

    # -- Filtrage / affichage -------------------------------------------------

    def _filtrer_par_etage(self, etage):
        self.etage_filtre = etage
        for e, pastille in self.pastilles_etage.items():
            pastille.definir_actif(e == etage)
        self._peupler_grille()

    def _peupler_grille(self):
        self.grille.clear_widgets()
        self._cartes_destination.clear()
        for dest in self.destinations:
            if self.etage_filtre is not None and dest["etage"] != self.etage_filtre:
                continue
            carte = CarteDestination(dest["id"], hex_vers_rgba(dest["couleur"]),
                                      type_icone=deduire_type_icone(dest),
                                      etage_texte=libelle_etage(dest["etage"]),
                                      size_hint_y=None, height=118)
            carte.bind(on_release=lambda inst, d=dest: self._selection_tactile(d))
            self.grille.add_widget(carte)
            self._cartes_destination[dest["id"]] = carte

    # -- Actions utilisateur (tactile) -----------------------------------------

    def _selection_tactile(self, dest):
        """L'utilisateur touche directement une carte de destination."""
        self.label_message.text = ""
        core.on_destination_reconnue(self.destinations, dest["id"], dest["id"],
                                      source="tactile")

    def _lancer_recherche(self, *args):
        """L'utilisateur tape dans la barre de recherche (réutilise le même
        matching flou que la reconnaissance vocale)."""
        texte = self.champ_recherche.text.strip()
        if not texte:
            return
        destination_id = core.trouver_destination(self.destinations, texte)
        if destination_id:
            self.label_message.text = ""
            core.on_destination_reconnue(self.destinations, destination_id, texte,
                                          source="tactile")
        else:
            core.on_non_compris(texte, source="tactile")
            self.label_message.text = "Destination non reconnue, essayez autrement."
        self.champ_recherche.text = ""

    # -- Actions utilisateur (micro) -------------------------------------------

    def _basculer_ecoute(self, *args):
        """Appui sur le gros bouton micro : démarre l'écoute, ou l'arrête
        si elle est déjà en cours (permet d'annuler manuellement)."""
        if self._ecoute_en_cours:
            self._arreter_ecoute("Écoute annulée.")
        else:
            self._demarrer_ecoute()

    def _demarrer_ecoute(self):
        if self._ecoute_en_cours:
            return
        self._ecoute_en_cours = True
        self._signaler_activite()
        self.bouton_micro.definir_etat("ecoute")
        self.label_micro_statut.text = "Je vous écoute..."
        self.label_message.text = ""

        evenement = threading.Event()
        self._arret_event = evenement
        self._ecoute_thread = threading.Thread(
            target=self._thread_ecoute, args=(evenement,), daemon=True)
        self._ecoute_thread.start()

        Clock.unschedule(self._expiration_ecoute)
        Clock.schedule_once(self._expiration_ecoute, DUREE_MAX_ECOUTE)

    def _thread_ecoute(self, evenement):
        """Exécuté dans un thread séparé : voix.ecouter() est bloquant et
        ne doit jamais tourner sur le thread principal Kivy (sinon
        l'écran tactile se fige pendant toute l'écoute)."""
        try:
            voix.ecouter(destinations=self.destinations, arret_event=evenement)
        except BaseException as exc:
            print(f"[micro] Erreur pendant l'écoute : {exc}")
            Clock.schedule_once(
                lambda dt: self._arreter_ecoute(
                    "Micro indisponible (vérifiez le micro et le modèle Vosk).",
                    erreur=True),
                0)
        else:
            Clock.schedule_once(lambda dt: self._arreter_ecoute(), 0)

    def _expiration_ecoute(self, dt):
        if self._ecoute_en_cours:
            self._arreter_ecoute("Je n'ai rien entendu, appuyez à nouveau pour réessayer.")

    def _arreter_ecoute(self, message=None, erreur=False):
        if not self._ecoute_en_cours:
            return
        self._ecoute_en_cours = False
        self._arret_event.set()
        Clock.unschedule(self._expiration_ecoute)
        if erreur:
            # Flash rouge bref pour signaler le problème, puis retour à
            # l'état "prêt" (bleu) pour permettre un nouvel essai.
            self.bouton_micro.definir_etat("erreur")
            Clock.schedule_once(lambda dt: self.bouton_micro.definir_etat("idle"), 2.0)
        else:
            self.bouton_micro.definir_etat("idle")
        self.label_micro_statut.text = message or "Appuyez pour parler"

    # -- Réaction à une reconnaissance venue d'ailleurs (voix ou tactile) ------

    def _sur_destination_reconnue(self, destination_id, dest, source):
        """Appelé pour CHAQUE destination reconnue (voix ou tactile), via
        core.ajouter_abonne. Peut être invoqué depuis le thread d'écoute :
        on repasse donc systématiquement par Clock.schedule_once pour ne
        toucher aux widgets Kivy que depuis le thread principal."""

        def _appliquer(dt):
            self._signaler_activite()
            carte = self._cartes_destination.get(destination_id)
            if carte is not None:
                carte.surligner()
            if source == "voix":
                # Reconnu à la voix -> on arrête l'écoute (push-to-talk).
                self._arreter_ecoute(f"Compris : {destination_id}")

        Clock.schedule_once(_appliquer, 0)


if __name__ == "__main__":
    BorneApp().run()