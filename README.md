# Robot conversationnel - Phase 1 (prototype PC)

Chaîne : micro (écoute permanente) -> mot d'activation -> STT (Whisper en ligne) -> LLM + outils (API) -> TTS -> haut-parleur,
avec un visage animé (3 barres à l'écoute, yeux quand il parle).

## Installation

1. **Python 3.10+** (python.org). Vérifie avec `python --version`.
2. Dans le dossier du projet, crée un environnement virtuel :
   - Windows : `python -m venv .venv` puis `.venv\Scripts\activate`
   - Mac/Linux : `python3 -m venv .venv` puis `source .venv/bin/activate`
3. `pip install -r requirements.txt`
   (Linux : si sounddevice se plaint, `sudo apt install libportaudio2`.)
4. **Voix Piper** (une seule fois, dans le dossier du projet) :
   `python -m piper.download_voices fr_FR-siwis-medium --download-dir voices`
   Si cette commande n'existe pas dans ta version, télécharge les deux fichiers
   `fr_FR-siwis-medium.onnx` et `fr_FR-siwis-medium.onnx.json` depuis la page
   Hugging Face "rhasspy/piper-voices" (dossier fr/fr_FR/siwis/medium) et place-les dans `voices/`.
5. **Clé d'API** : crée un compte sur console.groq.com, génère une clé,
   copie `.env.example` en `.env` et colle la clé dedans.
6. Vérifie dans `config.yaml` que les noms de modèles existent encore
   (console.groq.com/docs/models) : ils changent régulièrement. Attention aux modèles marqués
   "Enterprise / Contact Sales" : ils ne sont pas accessibles avec un compte normal.

## Lancer

    python main.py

Puis : dis le mot d'activation, ou appuie sur **Espace** dans la fenêtre / **Entrée** dans la console.

## Réglages utiles

- `python main.py --devices` : liste les micros et haut-parleurs (mets le numéro dans config.yaml).
- `python main.py --noise` : mesure le bruit ambiant pour régler `silence_threshold`.
  Trop bas : le robot n'arrête jamais d'écouter. Trop haut : il ne t'entend pas.
- Les temps STT / LLM / TTS sont affichés : c'est ce qui te dira plus tard si le Pi Zero tiendra.

## Structure

    main.py          boucle principale
    config.yaml      tous les réglages (fournisseur, modèles, prompt, audio)
    core/audio.py    micro + haut-parleur
    core/stt.py      voix -> texte
    core/llm.py      conversation et mémoire
    core/tts.py      texte -> voix (Piper)
    modules/         (vide) futurs outils : météo, actus, Spotify...

## Changer de fournisseur

Dans `config.yaml`, change `base_url`, `api_key_env` et les noms de modèles.
Tout service compatible OpenAI convient, sans toucher au code.

## Dépannage voix (Piper)

- La voix est chargée une seule fois au démarrage (1 à 3 s d'attente au lancement, c'est normal).
- Le texte est nettoyé avant lecture (apostrophes courbes, guillemets, symboles) : voir `clean_for_speech` dans `core/tts.py`.
- Si une erreur mentionne `synthesize`, donne-moi le résultat de `pip show piper-tts`.
- Le temps "1er son" est ce qui compte pour le ressenti : la lecture complète dépend de la longueur de la réponse.

## Choix de la voix

- `tts.engine: "edge"` : voix neuronales Microsoft via le paquet `edge-tts`. Gratuit, nettement plus naturel que Piper,
  mais service **non officiel** (peut cesser de fonctionner) et le texte des réponses transite par Microsoft.
  Si le réseau ou le service échoue, le robot bascule automatiquement sur Piper.
- `tts.engine: "piper"` : 100 % local, gratuit, hors-ligne, mais voix plus mécanique.
- Pour lister les voix françaises edge : `edge-tts --list-voices | findstr fr-` (Windows) ou `| grep fr-` (Mac/Linux).

## Changer de voix (homme / femme)

- En direct : tape `v` puis Entrée (liste numérotée), ou `v homme` directement. Le choix est sauvegardé dans `settings.json`.
- Le robot accorde aussi ses phrases au genre de la voix (prête / prêt).
- Pour ajouter une voix : copie une ligne de `tts.voices` dans `config.yaml` (liste des voix : `edge-tts --list-voices`).
- Voix de secours hors-ligne masculine (facultative) :
  `python -m piper.download_voices fr_FR-tom-medium --download-dir voices`

## Outils : météo et actualités

- `python main.py --tools` teste la météo et chaque flux RSS **sans voix ni LLM** : à lancer en premier.
- Météo : Open-Meteo (gratuit, sans clé). Ville par défaut dans `config.yaml` (`location.city`).
- Actualités : flux RSS listés dans `config.yaml` (`news.feeds`). Si un flux est en échec, remplace son URL.
- Le LLM décide seul d'appeler un outil (tool calling) : tu vois `[outil] get_weather {...}` dans la console.
- Ajouter un outil : un fichier `modules/mon_outil.py` avec `spec(cfg)` et `run(args, cfg)` (voir `modules/__init__.py`).
  Aucun autre fichier à modifier.

## Recherche web

- Par défaut : `ddgs` (aucune clé). En cas de blocage ou de quotas : crée un compte sur tavily.com, mets la clé dans `.env`
  (`TAVILY_API_KEY`) et passe `web_search.provider` à `"tavily"` dans `config.yaml`.
- `python main.py --tools` teste aussi la recherche web. En cas d'échec, la cause est affichée sur une ligne `[recherche web : échec ...]`.

## Phrases d'attente

- Si un outil met plus de `fillers.delay_seconds` (0,7 s), le robot dit une phrase comme « Un instant s'il te plaît, le temps que je fasse une recherche » pendant que l'outil travaille.
- Les phrases sont définies par outil (`FILLERS = [...]` dans `modules/xxx.py`) et pré-synthétisées au démarrage : la lecture est instantanée.
  Si une phrase n'est pas encore prête (démarrage tout juste lancé, hors-ligne), le robot reste silencieux plutôt que de retarder la réponse.
- Une seule phrase d'attente par question. Désactivation : `fillers.enabled: false`.

## Lecture de pages web

`read_webpage` lit une page issue d'un résultat de recherche quand l'extrait ne suffit pas. Seules les URL renvoyées par `search_web` sont acceptées.

## Écoute permanente et mot d'activation

1. Installe le détecteur (à part, car il est facultatif) : `pip install -r requirements-wake.txt`
2. Règle `wake.threshold` avec `python main.py --wake-test` : il affiche le score en direct quand tu dis le mot.
   Trop de faux réveils : monte le seuil (0.6). Il ne réagit pas : baisse-le (0.4).
3. Par défaut le mot est **"hey jarvis"** (modèle anglais prêt à l'emploi, pour valider le fonctionnement).
   Autres modèles prêts : `alexa`, `hey_mycroft`, `hey_rhasspy`. Un mot en français (le nom du robot) demande un modèle
   personnalisé : voir ROADMAP.md.
4. Si le détecteur n'est pas installé, le robot passe tout seul en mode manuel (Espace / Entrée).

Déroulé : veille -> mot d'activation -> le robot répond ("Oui ?") -> tu parles -> réponse -> **fenêtre de suite** (6 s pour enchaîner sans
redire le mot) -> retour en veille. Le micro est ignoré pendant que le robot parle (pas de réveil par sa propre voix).

## Visage

- **Veille** : yeux calmes qui clignent. **Écoute** : 3 barres verticales (graves, médiums, aigus) calculées par FFT sur le
  vrai son du micro, avec une porte de bruit. **Réflexion** : yeux qui regardent en haut + 3 points. **Parole** : yeux de dessin
  animé qui rebondissent avec le volume réel de la voix.
- Réglages dans `config.yaml` (section `ui`). `--no-ui` pour la console seule. Sous Linux : `sudo apt install python3-tk`.
- Le dessin est fait avec Pillow : le même code servira sur l'écran SPI du robot (phase 3).

## Commandes console

Entrée = réveiller | `v` = liste des voix, `v 3` ou `v homme` = choisir | `r` = nouvelle conversation | `q` = quitter

## Émotions

- Le LLM commence chaque réponse par une étiquette `[joie]`, `[tristesse]`, `[doute]`... jamais lue à voix haute : coût nul en calcul.
  Si elle manque, une règle locale (mots-clés) devine l'émotion. Émotions : neutre, joie, amusement, surprise, curiosité,
  tristesse, doute ; plus le sommeil (veille prolongée, `ui.sleep_after_seconds`).
- Pour ajouter une émotion : une ligne dans `PRESETS` (ui/face.py) et son nom dans `EMOTIONS` (core/dialogue.py).

## Fin de conversation automatique

- Tu dis "merci", "à plus tard", "c'est tout", "bonne nuit"..., ou le LLM juge la discussion close (`[fin]`) : le robot répond
  puis repasse tout de suite en veille, sans attendre.
- Le robot vient de poser une question : fenêtre d'écoute plus longue (`follow_up_question_seconds`).
- Bruit ou télé : les phrases fantômes de Whisper ("Sous-titrage...", "Merci d'avoir regardé...") sont ignorées.
- Désactivation : `conversation.auto_end: false`.

## Réponse de réveil

`conversation.wake_reply` : `"voice"` (le robot dit "Oui ?", "Je t'écoute"...), `"beep"` ou `"none"`. Les phrases sont
pré-synthétisées au démarrage : si l'une n'est pas encore prête, le robot retombe sur le bip.

## Mot d'activation "Zéphyr"

Porcupine n'est pas utilisable avec un compte particulier. Voie retenue : entraîner un modèle openWakeWord gratuit.
Guide pas à pas : `docs/ENTRAINER_ZEPHYR.md`. En attendant, "hey jarvis" fait office de mot de test, ou Espace / Entrée.
