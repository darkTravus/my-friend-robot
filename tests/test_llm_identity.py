import unittest

from core.llm import Brain


class BrainIdentityTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(
            None,
            {"system_prompt": "Réponds en français.", "max_history_messages": 16,
             "temperature": 0.6, "max_tokens": 1000},
            "test-model",
            robot_identity={"name": "Zéphyr", "description": "robot de compagnie"},
        )

    def test_system_prompt_contains_robot_identity(self):
        prompt = self.brain._system()

        self.assertIn("tu es Zéphyr, robot de compagnie", prompt)

    def test_unknown_speaker_cannot_receive_personal_profile_context(self):
        prompt = self.brain._system()

        self.assertIn("n'est pas authentifiée avec confiance", prompt)
        self.assertIn("n'utilise aucune information personnelle", prompt)
        self.assertIn("historique et leurs données personnelles ne sont pas disponibles", prompt)
        self.assertNotIn("centres d'intérêt enregistrés", prompt)

    def test_identified_speaker_context_is_explicit_and_resettable(self):
        self.brain.set_current_speaker({
            "display_name": "Alice",
            "interests": ["mangas", "musique"],
        })
        prompt = self.brain._system()

        self.assertIn('réponds qu\'il s\'agit de "Alice"', prompt)
        self.assertIn("son prénom", prompt)
        self.assertIn('["mangas", "musique"]', prompt)
        self.brain.reset()
        self.assertNotIn("Alice", self.brain._system())

    def test_short_unknown_turn_clears_previous_speaker_context(self):
        self.brain.set_current_speaker({
            "profile_id": "alice",
            "display_name": "Alice",
            "interests": ["mangas"],
        })
        self.brain.history.append({"role": "assistant", "content": "Alice aime les mangas."})

        context_reset = self.brain.set_current_speaker(None, "phrase trop courte")

        self.assertTrue(context_reset)
        self.assertEqual(self.brain.history, [])
        self.assertIsNone(self.brain.current_speaker)
        prompt = self.brain._system()
        self.assertIn("trop court pour tenter une identification fiable", prompt)
        self.assertNotIn("Alice", prompt)

    def test_switching_profiles_clears_previous_conversation_history(self):
        alice = {"profile_id": "alice", "display_name": "Alice", "interests": ["mangas"]}
        bob = {"profile_id": "bob", "display_name": "Bob", "interests": ["musique"]}
        self.brain.set_current_speaker(alice)
        self.brain.history.append({"role": "assistant", "content": "Information privée d'Alice."})

        context_reset = self.brain.set_current_speaker(bob)

        self.assertTrue(context_reset)
        self.assertEqual(self.brain.history, [])
        self.assertEqual(self.brain.current_speaker["display_name"], "Bob")
        self.assertNotIn("Alice", self.brain._system())
        self.assertIn('"Bob"', self.brain._system())

    def test_same_profile_keeps_context_between_identified_turns(self):
        profile = {"profile_id": "alice", "display_name": "Alice", "interests": []}
        self.brain.set_current_speaker(profile)
        self.brain.history.append({"role": "assistant", "content": "Contexte d'Alice."})

        context_reset = self.brain.set_current_speaker(profile)

        self.assertFalse(context_reset)
        self.assertEqual(len(self.brain.history), 1)

    def test_robot_voice_gender_does_not_change_with_speaker(self):
        self.brain.set_gender("f")
        self.brain.set_current_speaker({
            "profile_id": "alice",
            "display_name": "Alice",
            "interests": [],
        })
        female_voice_prompt = self.brain._system()
        self.brain.set_current_speaker({
            "profile_id": "bob",
            "display_name": "Bob",
            "interests": [],
        })
        switched_speaker_prompt = self.brain._system()

        self.assertIn("accorde tout au féminin", female_voice_prompt)
        self.assertIn("accorde tout au féminin", switched_speaker_prompt)
        self.assertIn("ne les adapte jamais à la personne", switched_speaker_prompt)
        self.assertNotIn("accorde tout au masculin", switched_speaker_prompt)


if __name__ == "__main__":
    unittest.main()
