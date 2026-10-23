"""Compatibility alias: Unspool was named LeakHunter, so ``leakhunter.*`` imports resolve to ``unspool.*``."""
import importlib
import importlib.abc
import importlib.util
import sys


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name.startswith(__name__ + "."):
            real = importlib.util.find_spec(_target(name))
            return real and importlib.util.spec_from_loader(name, self, origin=real.origin)
        return None

    def create_module(self, spec):
        module = importlib.import_module(_target(spec.name))
        spec.loader_state = module.__spec__
        return module

    def exec_module(self, module):
        # The import system stamps the alias spec on the shared module; give it back its real one.
        real = module.__spec__.loader_state
        module.__spec__, module.__loader__ = real, real.loader

    def get_code(self, name):  # lets ``python -m leakhunter.<module>`` keep working
        return importlib.util.find_spec(_target(name)).loader.get_code(_target(name))


def _target(name):
    return "unspool" + name[len(__name__):]


sys.meta_path.insert(0, _Alias())
