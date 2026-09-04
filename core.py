#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borne interactive - Coeur commun (core)
========================================

Ce module contient TOUT ce qui est partagé entre les deux façons de
demander une destination :
    - à la voix        (voix.py, reconnaissance Vosk)
    - au toucher        (interface_tactile.py, écran Kivy)

Ni le micro ni l'écran ne connaissent la logique métier directement :
ils appellent tous les deux `on_destination_reconnue(...)` défini ici.
Ça garantit que la voix ET le tactile déclenchent exactement la même
réponse (voix + futur allumage LED), sans dupliquer de code.

Système d'abonnés
------------------
D'autres modules (l'écran tactile, plus tard la logique LED) peuvent
s'abonner pour être prévenus à chaque fois qu'une destination est
reconnue, quelle que soit la source (voix ou tactile) :

    import core
    core.ajouter_abonne(ma_fonction)

    def ma_fonction(destination_id, dest, source):
        ...  # ex: allumer les LED, surligner un bouton à l'écran, etc.

`source` vaut "voix" ou "tactile" pour savoir d'où vient la demande.
"""

import csv
import json
import sys
import unicodedata
from collections import Counter

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_PATH = "vosk-model-small-fr-0.22"   # dossier du modèle Vosk téléchargé
SAMPLE_RATE = 16000                       # requis par Vosk

DESTINATIONS_CSV_PATH = "Destinations.csv"

VOIX_ACTIVEE = True   # passe à False pour désactiver complètement la voix
VOIX_VITESSE = 150    # mots/minute (pyttsx3), ajuster selon préférence
VOIX_LANGUE_PRIORITAIRE = "fr"  # pyttsx3 cherchera une voix contenant "fr"

# Couleur par défaut utilisée par l'écran tactile si aucune couleur n'est
# précisée dans le CSV pour une destination (voir colonne "couleur").
COULEUR_PAR_DEFAUT = "#3E7CB1"  # bleu neutre

MOTS_PORTEURS = [
    "ou", "est", "se", "trouve", "je", "cherche", "veux", "aller", "a",
    "comment", "vais", "peux", "tu", "me", "dire", "chercher", "un", "une",
    "le", "la", "les", "salle", "svp", "s'il", "te", "plait", "bonjour",
]

MOTS_A_IGNORER_POUR_MATCHING = set(MOTS_PORTEURS) - {"un", "une"}


# ---------------------------------------------------------------------------
# CHARGEMENT DES DESTINATIONS
# ---------------------------------------------------------------------------

def charger_destinations(chemin_csv: str = None):
    """
    Charge la liste des destinations depuis un fichier CSV.

    Format attendu (en-tête obligatoire, séparateur ';') :
        id;aliases;etage;couleur
        C2-07;salle c2 07|c2 07|c deux zero sept;2;#3E7CB1
        SECRETARIAT;secretariat|le secretariat;0;#C0407A

    - "id"      : identifiant de la destination.
    - "aliases" : différentes façons de la prononcer, séparées par "|".
    - "etage"   : colonne optionnelle (0 = rez-de-chaussée, etc.).
    - "couleur" : colonne optionnelle, code hexadécimal (ex. "#C0407A"),
                  utilisée uniquement par l'écran tactile pour reproduire
                  le style du panneau physique (zones colorées par
                  catégorie : rouge = départements, bleu = salles, etc.).
                  Si absente, COULEUR_PAR_DEFAUT est utilisée.
    """
    chemin_csv = chemin_csv or DESTINATIONS_CSV_PATH
    destinations = []
    try:
        with open(chemin_csv, newline="", encoding="utf-8") as f:
            lecteur = csv.DictReader(f, delimiter=";")
            if lecteur.fieldnames is None or "id" not in lecteur.fieldnames \
                    or "aliases" not in lecteur.fieldnames:
                print(f"Le fichier '{chemin_csv}' doit avoir les colonnes "
                      f"'id' et 'aliases' (en-tête manquant ou incorrect).")
                sys.exit(1)

            a_colonne_etage = "etage" in lecteur.fieldnames
            a_colonne_couleur = "couleur" in lecteur.fieldnames

            for ligne in lecteur:
                identifiant = ligne["id"].strip()
                alias_bruts = ligne["aliases"].strip()
                if not identifiant or not alias_bruts:
                    continue
                aliases = [a.strip() for a in alias_bruts.split("|") if a.strip()]

                etage = None
                if a_colonne_etage:
                    etage_brut = (ligne.get("etage") or "").strip()
                    if etage_brut:
                        try:
                            etage = int(etage_brut)
                        except ValueError:
                            print(f"Attention : étage invalide ('{etage_brut}') "
                                  f"pour la destination '{identifiant}', ignoré.")

                couleur = COULEUR_PAR_DEFAUT
                if a_colonne_couleur:
                    couleur_brute = (ligne.get("couleur") or "").strip()
                    if couleur_brute:
                        couleur = couleur_brute

                destinations.append({
                    "id": identifiant,
                    "aliases": aliases,
                    "etage": etage,
                    "couleur": couleur,
                })

    except FileNotFoundError:
        print(f"Fichier de destinations introuvable : '{chemin_csv}'.\n"
              f"Crée ce fichier CSV (colonnes 'id', 'aliases', 'etage', "
              f"'couleur') à côté du script, ou modifie "
              f"DESTINATIONS_CSV_PATH.")
        sys.exit(1)

    if not destinations:
        print(f"Le fichier '{chemin_csv}' ne contient aucune destination valide.")
        sys.exit(1)

    return destinations


def trouver_destination_par_id(destinations, destination_id: str):
    for dest in destinations:
        if dest["id"] == destination_id:
            return dest
    return None


# ---------------------------------------------------------------------------
# MATCHING FLOU (texte -> destination)
# ---------------------------------------------------------------------------

def normaliser(texte: str) -> str:
    """Minuscule + suppression des accents, pour comparer facilement."""
    texte = texte.lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return texte


def construire_grammaire(destinations):
    """Liste de mots que Vosk a le droit de reconnaître (vocabulaire
    restreint = plus robuste au bruit ambiant)."""
    mots = set(MOTS_PORTEURS)
    for dest in destinations:
        for alias in dest["aliases"]:
            for mot in normaliser(alias).split():
                mots.add(mot)
    mots.add("[unk]")
    return json.dumps(list(mots), ensure_ascii=False)


def _compter_mots_alias(alias: str) -> Counter:
    compteur = Counter(normaliser(alias).split())
    for mot_ignore in MOTS_A_IGNORER_POUR_MATCHING:
        del compteur[mot_ignore]
    return compteur


def trouver_destination(destinations, texte_reconnu: str, seuil_ratio: float = 0.6,
                         score_min: int = 1, marge_min: float = 0.15):
    """
    Retrouve la destination correspondant à un texte libre (dit à la voix
    OU tapé dans la barre de recherche tactile : la fonction est la même
    dans les deux cas).
    """
    texte_norm = normaliser(texte_reconnu)
    mots_dits = Counter(texte_norm.split())

    resultats = []  # (ratio, score, id)

    for dest in destinations:
        meilleur_ratio_dest = 0.0
        meilleur_score_dest = 0
        for alias in dest["aliases"]:
            mots_alias = _compter_mots_alias(alias)
            total_alias = sum(mots_alias.values())
            if total_alias == 0:
                continue
            score = sum(min(compte, mots_dits.get(mot, 0))
                        for mot, compte in mots_alias.items())
            ratio = score / total_alias
            if (ratio, score) > (meilleur_ratio_dest, meilleur_score_dest):
                meilleur_ratio_dest = ratio
                meilleur_score_dest = score
        if meilleur_score_dest > 0:
            resultats.append((meilleur_ratio_dest, meilleur_score_dest, dest["id"]))

    if not resultats:
        return None

    resultats.sort(reverse=True)
    meilleur = resultats[0]

    if meilleur[1] < score_min or meilleur[0] < seuil_ratio:
        return None

    if len(resultats) > 1:
        second = resultats[1]
        if (meilleur[0] - second[0]) < marge_min and meilleur[1] == second[1]:
            return None  # trop ambigu

    return meilleur[2]


# ---------------------------------------------------------------------------
# SYNTHÈSE VOCALE (hors-ligne, via pyttsx3 / espeak-ng ou SAPI5 sur Windows)
# ---------------------------------------------------------------------------

def _creer_moteur_voix():
    """Recrée un moteur pyttsx3 à chaque phrase (contourne un bug connu
    où réutiliser la même instance bloque le son après la 1ère phrase)."""
    try:
        import pyttsx3
    except ImportError:
        print("[voix] Le module 'pyttsx3' n'est pas installé. Voix désactivée.")
        return None

    try:
        moteur = pyttsx3.init()
    except Exception as e:
        print(f"[voix] Impossible d'initialiser le moteur vocal : {e}")
        return None

    try:
        for voix in moteur.getProperty("voices"):
            identifiant = (voix.id or "").lower()
            nom = (voix.name or "").lower()
            if VOIX_LANGUE_PRIORITAIRE in identifiant or VOIX_LANGUE_PRIORITAIRE in nom:
                moteur.setProperty("voice", voix.id)
                break
    except Exception as e:
        print(f"[voix] Impossible de sélectionner une voix française : {e}")

    moteur.setProperty("rate", VOIX_VITESSE)
    return moteur


def parler(texte: str):
    if not VOIX_ACTIVEE:
        return
    moteur = _creer_moteur_voix()
    if moteur is None:
        return
    try:
        moteur.say(texte)
        moteur.runAndWait()
    finally:
        try:
            moteur.stop()
        except Exception:
            pass


def texte_etage(etage) -> str:
    """0 -> rez-de-chaussée, 1 -> premier étage, n -> n-ème étage.
    Convention projet : Bâtiment A = étage 4 dans le CSV."""
    if etage is None:
        return ""
    if etage == 0:
        return "au rez-de-chaussée"
    if etage == 1:
        return "au première étage"
    if etage == 4:
        return "dans le bâtiment A"
    return f"au {etage}ème étage"


# ---------------------------------------------------------------------------
# SYSTÈME D'ABONNÉS (voix + tactile + futur LED branchés ici)
# ---------------------------------------------------------------------------

_abonnes = []


def ajouter_abonne(fonction):
    """Enregistre une fonction appelée à chaque destination reconnue,
    quelle que soit la source. Signature attendue :
        fonction(destination_id: str, dest: dict, source: str)
    """
    _abonnes.append(fonction)


def on_destination_reconnue(destinations, destination_id: str, texte_brut: str,
                             source: str = "voix"):
    """
    Point d'entrée UNIQUE quand une destination est reconnue, que ce soit
    par la voix ou par l'écran tactile. Annonce le résultat (terminal +
    voix) puis prévient tous les abonnés (écran, futur module LED, etc.).
    """
    dest = trouver_destination_par_id(destinations, destination_id)
    etage = dest["etage"] if dest else None

    print(f"[OK] Destination comprise ({source}) : {destination_id}  "
          f"(entendu/saisi : « {texte_brut} »)")

    if etage is not None:
        phrase = (f"Destination comprise : {destination_id}. "
                  f"Votre destination se trouve {texte_etage(etage)}. "
                  f"Vous pouvez suivre le chemin lumineux indiqué sur le panneau ! ")
    else:
        phrase = (f"Destination comprise : {destination_id}. "
                  f"Vous pouvez suivre le chemin lumineux indiqué sur le panneau ! ")

    parler(phrase)

    for abonne in _abonnes:
        try:
            abonne(destination_id, dest, source)
        except Exception as e:
            print(f"[abonné] Erreur dans un abonné ({abonne}) : {e}")


def on_non_compris(texte_brut: str, source: str = "voix"):
    print(f"[?] Destination non comprise ({source}). (entendu/saisi : « {texte_brut} »)")
    parler("Désolé, je n'ai pas compris la destination demandée.")