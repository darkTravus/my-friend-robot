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
- `python main.py --tts-test` : génère, lit et exporte cinq exemples vocaux de référence en WAV dans `tts-test-output`
  (connexion Internet nécessaire avec Edge TTS).
  Chaque lancement crée un nouveau dossier daté ; écoute les cinq fichiers dans l'ordre pour évaluer le naturel,
  l'intonation et les éventuelles coupures. Compare les voix avec `--tts-test-voice homme` ou un autre profil,
  et change le dossier racine avec `--tts-test-dir chemin`.
- `python -m unittest discover -s tests -v` : lance les tests unitaires du projet, y compris ceux des listes et du banc d'essai.
- Les listes vocales (ajout, consultation, suppression, export Markdown/TXT) sont stockées localement dans `data/`. Exemples : « ajoute du lait à ma liste courses », « montre ma liste courses », « retire le lait de ma liste courses » ou « exporte ma liste courses en texte ».
- L'identité du robot est définie par `robot.name` et `robot.description` dans `config.yaml`. Le robot est **Zéphyr**, un petit robot de compagnie ; son identité est injectée dans le prompt système.
- Le mot de réveil openWakeWord utilise un seuil renforcé, plusieurs trames successives et un filtre de niveau sonore minimal pour limiter les faux réveils. Ajuste `wake.threshold`, `wake.consecutive_frames` et `wake.minimum_rms` dans `config.yaml` selon le micro ; `python main.py --wake-test` permet de vérifier le score du mot prononcé. La voix et le genre grammatical configurés pour Zéphyr restent fixes quand le locuteur change. Si Edge TTS est indisponible, le journal indique le repli Piper, qui a un timbre différent.
- L'identification vocale expérimentale est désactivée par défaut pour préserver le démarrage sans dépendances ONNX et tenir compte du matériel cible. Installe ses dépendances facultatives avec `pip install -r requirements-speaker-benchmark.txt`, puis lance `python main.py --enroll-speaker` pour enregistrer cinq phrases et le nom d'usage / les centres d'intérêt. Au moins deux profils sont nécessaires pour tenter une identification. Les empreintes vocales sont conservées localement dans `data/speaker_profiles.json` ; les enregistrements bruts ne sont pas sauvegardés. Active ensuite `speaker_identification.enabled` dans `config.yaml`. Le seuil initial est provisoirement `0.30` ; une phrase de moins de 3 secondes ou un score ambigu est traité comme « inconnu », sans accès aux informations du profil. Le profil est vérifié à chaque prise de parole : le robot garde le contexte uniquement pour les tours successifs reconnus comme le même profil. Un changement de profil, un tour non authentifié ou un nouveau réveil efface l'historique avant l'appel STT/LLM, afin de ne pas transmettre au fournisseur ni révéler les données de l'interlocuteur précédent. Lorsqu'un profil est reconnu, son nom et ses centres d'intérêt sont ajoutés au contexte envoyé au fournisseur du LLM. Cette étape ne crée pas encore de mémoire personnelle persistante. Supprime un profil avec `python main.py --delete-speaker <identifiant>`.
- Le banc d'essai d'identification vocale est séparé du robot. Installe `requirements-speaker-benchmark.txt`, télécharge le modèle WeSpeaker ECAPA512 ONNX dans `data/models/voxceleb_ECAPA512.onnx`, puis lance :

      python scripts/benchmark_speakers.py --model data/models/voxceleb_ECAPA512.onnx --samples data/speaker-benchmark

  Pour chaque personne, sépare les fichiers ainsi : `data/speaker-benchmark/<personne>/enrollment/*.wav` et `data/speaker-benchmark/<personne>/test/*.wav`. Mets au moins deux WAV d'enrôlement et un WAV de test par personne, et au moins deux personnes. Les WAV doivent être mono PCM 16 bits à 16 kHz. Les enregistrements de test doivent être distincts de ceux utilisés pour créer le profil ; varie les phrases et conditions d'enregistrement. Le script calcule les profils et scores localement sans sauvegarder les empreintes.
  Le rapport mesure le taux de faux rejets (FRR) et le taux de fausses acceptations (FAR) par comparaison profil-test ; il compte aussi les bonnes et fausses identifications par extrait ainsi que les rejets selon plusieurs seuils. Ce balayage reste exploratoire : il ne valide pas un seuil sur des données indépendantes, et les FAR/FRR par comparaison ne sont pas des taux par personne. Les extraits de moins de 3 secondes sont signalés. Le modèle est un candidat expérimental entraîné sur VoxCeleb en anglais : il ne doit pas servir à attribuer des souvenirs tant que des tests français représentatifs n'ont pas confirmé les résultats. Le script affiche aussi les temps d'inférence sur le PC ; ces mesures ne préjugent pas des performances sur le Pi. Voir le [tableau officiel WeSpeaker](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md) et vérifier la licence du modèle avant toute redistribution.

## Structure

    main.py          boucle principale
    config.yaml      tous les réglages (fournisseur, modèles, prompt, audio)
    core/audio.py    micro + haut-parleur
    core/stt.py      voix -> texte
    core/llm.py      conversation et mémoire
    core/tts.py      texte -> voix (Edge TTS ou Piper)
    modules/         outils du robot : météo, actus, recherche web, listes...

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
3. Le mot d'activation est **"hey Zéphyr"**, avec le modèle personnalisé `model/hey_zephyr.onnx`.
   Pour régler le seuil ou tester le score du modèle, lance `python main.py --wake-test`.
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

Porcupine n'est pas utilisable avec un compte particulier. Le modèle personnalisé openWakeWord **"hey Zéphyr"** est installé
dans `model/hey_zephyr.onnx`. Guide d'entraînement : `docs/ENTRAINER_ZEPHYR.md`. Espace / Entrée restent disponibles en
mode manuel.
