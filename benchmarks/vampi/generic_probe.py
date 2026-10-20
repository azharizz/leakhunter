"""Benchmark adapter only: a vulnerable baseline must remain a failed gate."""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expect-fixed", action="store_true")
    expected.add_argument("--expect-vulnerable", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("acceptance", "/acceptance.py")
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    try:
        plan = acceptance.strict_json(Path("/plan.json").read_bytes())
        result = acceptance.check("http://vampi:8080", plan)
        runtime = result["runtime"]
        observed = any(case["observations"] for case in runtime["cases"] if case["id"] == "debug")
        reproduced = (runtime["functional_passed"] is True
                      and runtime["passed"] is (not args.expect_vulnerable)
                      and observed is args.expect_vulnerable)
        result["expected_behavior_reproduced"] = reproduced
        print(json.dumps(result))
        if not reproduced:
            raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"status": "STOPPED", "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
