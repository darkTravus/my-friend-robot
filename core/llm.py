"""Le 'cerveau' : conversation avec mémoire courte et appel d'outils (météo, actualités...)."""
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime

from openai import OpenAI

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MAX_TOOL_ROUNDS = 4  # garde-fou : le LLM ne peut pas enchaîner des outils à l'infini


def now_fr() -> str:
    n = datetime.now()
    return f"{JOURS[n.weekday()]} {n.day} {MOIS[n.month - 1]} {n.year}, {n.hour}h{n.minute:02d}"


class Brain:
    def __init__(self, client: OpenAI, cfg: dict, model: str, tools=None):
        self.client, self.model, self.tools = client, model, tools
        self.base_prompt = cfg["system_prompt"].strip()
        self.gender_line = ""
        self.max_history = cfg["max_history_messages"]
        self.temperature = cfg["temperature"]
        self.max_tokens = cfg["max_tokens"]
        self.reasoning_effort = cfg.get("reasoning_effort")
        self.history = []
        self.on_slow_tool = None   # fonction(nom_outil) appelée si un outil dépasse tool_delay
        self.tool_delay = 0.7
        self.tool_timeout = 12.0   # au-delà, l'outil est abandonné et le LLM répond sans lui
        self.debug_timing = cfg.get("debug_timing", False)

    def _system(self) -> str:
        s = self.base_prompt + f"\nNous sommes le {now_fr()}."
        if self.gender_line:
            s += "\n" + self.gender_line
        return s

    def _compact(self):
        """Nouveau tour : on oublie les résultats d'outils des tours précédents (moins de tokens, moins de confusion)."""
        self.history = [m for m in self.history
                        if m["role"] == "user" or (m["role"] == "assistant" and not m.get("tool_calls"))]

    def _trim(self):
        """Garde les derniers messages, sans jamais commencer par un résultat d'outil orphelin."""
        self.history = self.history[-self.max_history:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def reply(self, user_text: str) -> str:
        self._compact()
        self.history.append({"role": "user", "content": user_text})
        self._trim()
        extra = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
        specs = self.tools.specs() if self.tools else []

        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = dict(model=self.model,
                          messages=[{"role": "system", "content": self._system()}] + self.history,
                          temperature=self.temperature, max_tokens=self.max_tokens, extra_body=extra)
            if specs:
                kwargs.update(tools=specs, tool_choice="auto")
            t_llm = time.time()
            msg = self.client.chat.completions.create(**kwargs).choices[0].message
            if self.debug_timing:
                print(f"  [llm {time.time() - t_llm:.1f}s]")

            calls = getattr(msg, "tool_calls", None)
            if calls:  # le LLM demande à utiliser un outil
                self.history.append({
                    "role": "assistant", "content": msg.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function",
                                    "function": {"name": tc.function.name,
                                                 "arguments": tc.function.arguments or "{}"}} for tc in calls]})
                for tc in calls:
                    print(f"  [outil] {tc.function.name} {tc.function.arguments}")
                results = self._run_tools(calls)
                for tc, result in zip(calls, results):
                    self.history.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue

            answer = (msg.content or "").strip() or "Désolé, je n'ai pas réussi à formuler une réponse."
            self.history.append({"role": "assistant", "content": answer})
            return answer

        answer = "Désolé, je n'arrive pas à terminer cette recherche."
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def _run_tools(self, calls):
        """Exécute les outils en parallèle. Phrase d'attente si lent, abandon si trop lent."""
        def timed(tc):
            t0 = time.time()
            return self.tools.call(tc.function.name, tc.function.arguments), time.time() - t0

        ex = ThreadPoolExecutor(max_workers=len(calls))
        futs = [ex.submit(timed, tc) for tc in calls]
        _, pending = wait(futs, timeout=self.tool_delay)
        if pending and self.on_slow_tool:
            self.on_slow_tool(calls[0].function.name)
        wait(futs, timeout=max(0.0, self.tool_timeout - self.tool_delay))
        results = []
        for tc, f in zip(calls, futs):
            if f.done():
                result, dt = f.result()
                print(f"  [outil] {tc.function.name} terminé en {dt:.1f}s")
                results.append(result)
            else:
                print(f"  [outil] {tc.function.name} trop lent (> {self.tool_timeout:g}s) : abandonné")
                results.append("[Résultat indisponible : l'outil n'a pas répondu à temps.]")
        ex.shutdown(wait=False)  # n'attend pas un outil bloqué
        return results

    def last_answer(self) -> str:
        """Dernière phrase du robot : sert de contexte à la transcription (noms propres)."""
        for m in reversed(self.history):
            if m["role"] == "assistant" and m.get("content"):
                return m["content"]
        return ""

    def set_gender(self, genre: str | None):
        """'f' ou 'm' : accorde les phrases du robot avec sa voix (prête / prêt)."""
        self.gender_line = {
            "f": "Tu es une voix féminine : accorde tout au féminin (je suis prête, contente...).",
            "m": "Tu es une voix masculine : accorde tout au masculin (je suis prêt, content...).",
        }.get(genre, "")

    def reset(self):
        self.history.clear()
