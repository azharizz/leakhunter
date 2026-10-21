"""Model-provider client. The benchmark never calls a real provider."""


def complete(prompt):
    raise RuntimeError("Model-provider calls are disabled in the synthetic benchmark")
