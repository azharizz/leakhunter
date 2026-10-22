"""Offline OpenAI-shaped transport used only by the synthetic runtime fixture."""


class _Completions:
    def create(self, *, messages):
        return {"summary": "synthetic model response"}


class _Chat:
    completions = _Completions()


chat = _Chat()
