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
- [x] ✅ Mot d'activation local (openWakeWord, "hey jarvis" pour valider) : fonctionne
- [x] ✅ Fenêtre de suite sans redire le mot d'activation
- [x] ✅ Animation d'écoute : 3 barres (spectre réel du micro)
- [x] ✅ Animation de parole : yeux de dessin animé (volume réel de la voix)
- [x] ❌ Porcupine : inutilisable (réservé aux entreprises, essai de 7 jours)
- [ ] ⬜ Entraîner un modèle openWakeWord "Zéphyr" sur Colab gratuit (guide : docs/ENTRAINER_ZEPHYR.md), puis le tester avec --wake-test
- [ ] ⬜ Plan B si le français passe mal : livekit-wakeword (voix de synthèse multilingues, plus complexe)
- [x] ✅ Émotions : joie, amusement, surprise, curiosité, tristesse, doute, sommeil (étiquette du LLM + règles locales)
- [x] ✅ Fin de conversation automatique (merci / au revoir / jugement du LLM), fenêtre plus longue après une question
- [x] ✅ Réponse de réveil vocale ("Oui ?") à la place du bip
- [x] ✅ Nom du robot : **Zéphyr**
- [x] ✅ Test avec de la musique en fond : pas de faux réveil, fin de conversation correcte

## Phase 2 : Matériel Raspberry Pi ⏳
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
- [ ] 💤 Listes (courses, animés) avec export .md / .txt
- [ ] 💤 Mémoire entre conversations (notes)
- [ ] 💤 Surveillance d'un sujet + prévenir plus tard

## Phase 5 : Interface web sur téléphone (FastAPI / PWA) ⬜
- [ ] ⬜ Réglages : voix, mot d'activation, ville, volume
- [ ] ⬜ Accès aux listes et notes (quand elles existeront)

## Phase 6 : Identification du locuteur ⬜
- [ ] ⬜ Enregistrer des personnes via l'interface
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
- [ ] ⬜ Confidentialité : bouton de coupure micro / caméra, empreintes vocales en local
- [ ] ⬜ Sauvegarde et robustesse (logs, redémarrage, carte SD)
