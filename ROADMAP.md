# Feuille de route du robot

Légende : ✅ fait · 🟡 en cours / à valider · ⏳ bloqué (matériel non reçu) · ⬜ à faire · 💤 reporté volontairement

## Phase 0 : Apprentissage (en continu)
- [x] Python, appels d'API, JSON, threads
- [ ] 🟡 Linux en ligne de commande, SSH, systemd (à pratiquer avec le Pi)
- [ ] ⬜ Électronique de base : câblage GPIO, I2S, SPI

## Phase 1 : Prototype sur PC ✅
- [x] ✅ Chaîne voix : micro -> Whisper -> LLM -> voix
- [x] ✅ Voix homme / femme au choix, sauvegardée, accord du genre
- [x] ✅ Voix en ligne (edge-tts) + repli local Piper
- [x] ✅ Outils : météo, actualités RSS, recherche web, lecture de page
- [x] ✅ Phrases d'attente, délai maximum des outils, historique allégé
- [ ] 🟡 Valider que gpt-oss-120b n'invente plus de titres

## Phase 1b : Écoute permanente et visage sur PC 🟡 (livré, à tester)
- [x] ✅ Micro en écoute continue, sans bouton
- [x] ✅ Mot d'activation local (openWakeWord, modèle personnalisé "hey Zéphyr") : entraîné, exporté et testé
- [x] ✅ Fenêtre de suite sans redire le mot d'activation
- [x] ✅ Animation d'écoute : 3 barres (spectre réel du micro)
- [x] ✅ Animation de parole : yeux de dessin animé (volume réel de la voix)
- [x] ❌ Porcupine : inutilisable (réservé aux entreprises, essai de 7 jours)
- [x] ✅ Entraîner, exporter et tester le modèle openWakeWord "Zéphyr" (model/hey_zephyr.onnx)
- [ ] ⬜ Plan B si le français passe mal : livekit-wakeword (voix de synthèse multilingues, plus complexe)
- [x] ✅ Émotions : joie, amusement, surprise, curiosité, tristesse, doute, sommeil (étiquette du LLM + règles locales)
- [x] ✅ Fin de conversation automatique (merci / au revoir / jugement du LLM), fenêtre plus longue après une question
- [x] ✅ Réponse de réveil vocale ("Oui ?") à la place du bip
- [x] ✅ Nom du robot : **Zéphyr**
- [x] ✅ Test avec de la musique en fond : pas de faux réveil, fin de conversation correcte

## Phase 1c : Expression vocale naturelle 🟡
- [x] ✅ Consignes de dialogue oral : hésitations rares et pertinentes, formulations fluides, pas de didascalies
- [x] ✅ Regrouper les phrases liées en segments Edge TTS pour limiter les coupures audibles
- [x] ✅ Tests de référence reproductibles en ligne de commande avec export WAV
- [ ] 🟡 Écouter les exemples sur les voix utilisées et ajuster le rythme / la taille des segments
- [ ] ⬜ Étudier plus tard l'ajout contrôlé de respirations, soupirs et autres effets sonores
- [ ] 💤 Remplacer à terme le moteur vocal par un TTS Gemini ou GPT-4o

## Phase 2 : Matériel Raspberry Pi 💤 (reportée)
- [ ] ⏳ Achat tranche 1 (Pi Zero 2 WH, alim, microSD, micro INMP441, ampli MAX98357A + haut-parleur, plaque + fils)
- [ ] ⏳ Raspberry Pi OS, SSH, Wi-Fi, installation du projet
- [ ] ⏳ Câblage micro I2S et ampli, test audio
- [ ] ⏳ Bouton physique de réveil (GPIO, ~1 €) : filet de sécurité si le mot d'activation est capricieux
- [ ] ⏳ Mesurer le coût CPU / RAM du mot d'activation openWakeWord sur le Zero 2 W
- [ ] ⏳ Mesure RAM / CPU / latence avec tout qui tourne
- [ ] ⏳ Démarrage automatique (systemd)

## Phase 3 : Visage sur écran SPI ⏳
- [ ] ⏳ Achat écran (ST7789 / ILI9341), câblage, pilote
- [ ] ⏳ Envoyer les images Pillow à l'écran (mises à jour partielles si trop lent)
- [ ] ⏳ Ajuster le rendu (scale 1, fps) pour le Zero 2 W

## Phase 4 : Outils du LLM
- [x] ✅ Météo, actualités, recherche web, lecture de page
- [x] ✅ Listes nommées (ajout, consultation, suppression, export .md / .txt, stockage local)
- [x] ✅ Identité explicite du robot (nom et description configurés)
- [ ] 💤 Mémoire entre conversations (notes)
- [ ] 💤 Surveillance d'un sujet + prévenir plus tard

## Phase 5 : Interface web sur téléphone (FastAPI / PWA) ⬜
- [ ] ⬜ Réglages : voix, mot d'activation, ville, volume
- [ ] ⬜ Accès aux listes et notes (quand elles existeront)

## Phase 6 : Identification du locuteur 🟡 (évaluation préliminaire)
- [x] ✅ Évaluer un modèle local WeSpeaker ONNX sur le jeu exploratoire de voix françaises
- [x] ✅ Première intégration expérimentale locale : profils nom/intérêts, enrôlement CLI, seuil provisoire et rejet des voix inconnues/ambiguës
- [x] ✅ Isolation du contexte entre personnes ; historique effacé si le locuteur change, n'est pas authentifié ou qu'une nouvelle conversation démarre
- [ ] ⬜ Évaluer l'intégration sur des conversations réelles, avec phrases courtes, bruit et plusieurs locuteurs
- [ ] ⬜ Enregistrer et gérer des personnes via l'interface
- [ ] ⬜ Tests de fiabilité (phrases courtes, bruit)
- [ ] ⬜ **Profils et souvenirs personnels** (idée du propriétaire) : retenir ce qu'une personne confie, par personne
  - Règles : jamais évoquer un souvenir personnel si la personne n'est pas identifiée avec confiance, ou si plusieurs voix / visages sont présents
  - Transparence : "qu'est-ce que tu sais sur moi ?", "oublie ça", suppression totale ; liste consultable sur le téléphone
  - Les souvenirs rappelés repartent chez le fournisseur du LLM dans le prompt : à signaler à l'utilisateur
  - Informations sensibles : demander une confirmation (téléphone) plutôt que se fier à la seule voix
  - Dépend de : mémoire entre conversations (Phase 4) + identification du locuteur

## Phase 7 : Caméra et détection de personnes ⬜ (tranche 3, ~15 €)

## Phase 8 : Spotify ⬜
- [ ] ⬜ Vérifier les conditions d'accès des développeurs (compte Premium, quotas)

## Phase 9 : Capteurs de présence Zigbee, boîtier ⬜
- [ ] ⬜ Capteurs Aqara/Tuya + clé USB Zigbee (~40-60 €)
- [ ] ⬜ Boîtier (carton / bois, puis impression 3D)

## Transversal
- [ ] ⬜ Tenir compte des limites du matériel cible (CPU, RAM, latence, réseau) dans les choix logiciels, même avant l'achat du Pi
- [ ] ⬜ Confidentialité : bouton de coupure micro / caméra, empreintes vocales en local
- [ ] ⬜ Sauvegarde et robustesse (logs, redémarrage, carte SD)
