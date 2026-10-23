"""Production composition root: CLI, provider wiring, and HTTP server startup."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from leakhunter.api.server import create_handler
from leakhunter.application import service
from leakhunter.providers.openrouter import ProviderFactory

# Compatibility state for callers that historically configured the provider through this module.
API_URL = ""
API_KEY = ""


def configure(args: argparse.Namespace) -> None:
    global API_URL, API_KEY
    API_URL, API_KEY = args.provider_url, os.getenv("AGENT_PROVIDER_API_KEY", "")
    service.configure(args, call_model)


def call_model(model: str, prompt: str, *, questions: dict | None = None) -> tuple[str | dict, int, str]:
    provider = ProviderFactory.create(API_URL, API_KEY, opener=urlopen)
    result = provider.call(model, prompt, questions=questions)
    service.record_model_usage(provider.last_usage)
    return result


current_policy = service.current_policy
runtime_config = service.runtime_config
graph = service.graph
revision_sha = service.revision_sha
mapped_finding = service.mapped_finding
attach_evidence = service.attach_evidence
release_gate = service.release_gate
analyze = service.analyze
repair = service.repair
evaluate = service.evaluate
Handler = create_handler(service)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["diff"]:
        from unspool.exposure_diff import main as diff_main
        diff_main(argv[1:])
        return
    parser = argparse.ArgumentParser(
        description="Analyze, execute synthetic proofs, and independently verify repairs for a configured repository")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--language", choices=("python", "javascript", "typescript", "go", "rust"),
                        help="Defaults to the runtime manifest language, or Python without a manifest")
    parser.add_argument("--policy", type=Path,
                        help="Operator policy YAML; omit to use the built-in sensitive-field catalogue")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--provider-url", default=os.getenv("AGENT_PROVIDER_URL", ""))
    parser.add_argument("--decision-model", default=os.getenv("AGENT_PROVIDER_MODEL", ""))
    parser.add_argument("--repair-model", default=os.getenv("DUO_PROVIDER_MODEL", ""))
    parser.add_argument("--decision-mode", choices=("required", "advisory"),
                        default=os.getenv("UNSPOOL_DECISION_MODE", "required"),
                        help="required (default): require complete Luna triage and configured probes for non-clear "
                             "boundaries; advisory: record triage without making its completeness a gate requirement")
    parser.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--runtime-backend", choices=("docker", "local"), default="docker",
                        help="local executes trusted target code without a security sandbox")
    parser.add_argument("--runtime-timeout", type=int, default=30)
    parser.add_argument("--once", choices=("analyze", "repair", "evaluate"),
                        help="Print JSON and exit instead of serving the UI")
    parser.add_argument("--gate", action="store_true", help="CI release gate for --once analyze or repair only")
    parser.add_argument("--branch", default="main", help="Named snapshot pointer; non-main branches are isolated overlays")
    parser.add_argument("--base-snapshot-id", help="Incremental baseline for a branch/MR overlay")
    args = parser.parse_args(argv)
    if args.gate and args.once not in {"analyze", "repair"}:
        parser.error("--gate requires --once analyze or repair; evaluation accuracy is not release safety")
    try:
        configure(args)
        if args.once:
            result = (analyze(branch=args.branch, base_snapshot_id=args.base_snapshot_id)
                      if args.once == "analyze" else repair() if args.once == "repair" else evaluate())
            print(service.encoded(result), flush=True)
            if args.gate and not (
                result.get("gate", {}).get("passed") if args.once == "analyze" else
                result.get("passed")):
                raise SystemExit(1)
            return
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Unspool running at http://localhost:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
