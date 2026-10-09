# Entraîner le mot d'activation "Zéphyr" (openWakeWord, gratuit)

Source : notebook communautaire `alfiedennen/openwakeword-colab-2026` (licence MIT), qui corrige le notebook officiel devenu
inutilisable en 2026. C'est un projet très peu connu : lis les cellules avant de les lancer et n'accorde à Colab que les accès
strictement nécessaires.

## Étapes

1. Ouvre le notebook dans Colab :
   https://colab.research.google.com/github/alfiedennen/openwakeword-colab-2026/blob/main/train_wakeword.ipynb
2. Exécution > Modifier le type d'exécution > **GPU T4** (gratuit). Compte environ 2 h 30 contre 75 à 90 min avec un GPU L4
   (Colab Pro, 10 $/mois, inutile pour toi). Garde l'onglet ouvert et actif : Colab peut déconnecter un onglet en arrière-plan.
3. Dans la cellule 10, modifie deux lignes. Toutes les variantes déclenchent le même modèle ; la voix de synthèse est
   anglaise, donc on ajoute des orthographes qui se lisent comme un français dirait "Zéphyr" (variantes à tester) :

       TARGET_PHRASE = ['hey zephyr', 'hey zay feer', 'hay zeh feer']
       MODEL_NAME    = 'zephyr'

4. Exécution > **Tout exécuter**, puis attends. Le notebook télécharge environ 25 Go **dans Colab** (pas sur ton PC).
   La dernière cellule télécharge `zephyr.onnx`.
5. Place `zephyr.onnx` dans le dossier `voices/` du projet, puis dans `config.yaml` :

       wake:
         mode: "openwakeword"
         models: ["voices/zephyr.onnx"]
         threshold: 0.5

6. `python main.py --wake-test` : dis "hey Zéphyr" plusieurs fois (loin, près, doucement, fort), puis laisse la télé ou la
   musique : note les scores. Ajuste `wake.threshold` (0.6 à 0.7 = moins de faux réveils, un peu moins de réussite).

## Si ça ne marche pas assez bien (conseils du notebook)

- **Il ne réagit pas assez (moins de 18 réussites sur 20)** : dans la cellule 20, passe `n_samples` à 5000, ou `target_recall`
  de 0.5 à 0.7, ou ajoute `augmentation_rounds: 2`.
- **Faux réveils (plus d'un toutes les 30 minutes)** : passe `max_negative_weight` de 1500 à 3000.
- **Limite connue** : les voix de synthèse sont anglaises. Si l'accent français pose problème, plan B : livekit-wakeword
  (synthèse multilingue VoxCPM, français pris en charge ; la précision hors anglais y est annoncée plus faible).
