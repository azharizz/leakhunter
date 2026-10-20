import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("recovery_observer", Path(__file__).parents[1] / "benchmarks/recovery/observe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ObserverTest(unittest.TestCase):
    def test_server_result_is_preserved_and_writes_are_never_dispatched(self):
        api = Mock()
        result = {"status": "real response"}
        api.request.return_value = result
        observer = module.ReadOnlyObservation(api, "none")
        self.assertIs(observer.request("GET", "projects/1"), result)
        for method in ("POST", "PUT", "DELETE"):
            with self.assertRaises(RuntimeError):
                observer.request(method, "projects/1")
        self.assertEqual(api.request.call_count, 1)

    def test_crash_is_injected_only_after_real_server_read(self):
        api = Mock()
        observer = module.ReadOnlyObservation(api, "after-evidence")
        with patch.object(module.os, "kill", side_effect=RuntimeError("injected")) as kill:
            observer.request("GET", "projects/1/merge_requests/2")
            kill.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "injected"):
                observer.request("GET", "projects/1/jobs/1/artifacts/acceptance/evidence.json")
            self.assertEqual(api.request.call_count, 2)
            kill.assert_called_once_with(module.os.getpid(), module.signal.SIGKILL)
