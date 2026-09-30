# Robot conversationnel - Phase 1 (prototype PC)

Chaîne : micro -> STT (Whisper en ligne) -> LLM (API) -> TTS (Piper local) -> haut-parleur.

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
   (console.groq.com/docs/models) : ils changent régulièrement.

## Lancer

    python main.py

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
