"""Example-owned defaults; the application never imports this module."""
from pathlib import Path
import argparse
import os

from unspool.app import main

HERE = Path(__file__).resolve().parent


def run():
    parser = argparse.ArgumentParser(description="Run Unspool against the bundled example")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--offline", action="store_true", help="Disable provider calls")
    parser.add_argument("--env-file", type=Path, default=HERE.parent / ".env")
    parser.add_argument("--runtime-manifest", type=Path, default=HERE / "runtime.yaml")
    parser.add_argument("--runtime-backend", choices=("docker", "local"), default="docker")
    parser.add_argument("--trusted-local", action="store_true",
                        help="Explicitly trust this synthetic target and execute it without Docker")
    args = parser.parse_args()
    if args.runtime_backend == "local" and not args.trusted_local:
        parser.error("--runtime-backend local requires --trusted-local")
    if not args.offline and args.env_file.exists():
        for line in args.env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    main([
        "--repository", str(HERE / "fixtures"),
        "--policy", str(HERE / "unspool-policy.yaml"),
        "--data-dir", str(HERE / "data"),
        "--port", str(args.port),
        "--runtime-manifest", str(args.runtime_manifest),
        "--runtime-backend", "local" if args.trusted_local else args.runtime_backend,
        "--provider-url", "" if args.offline else os.getenv("AGENT_PROVIDER_URL", "https://openrouter.ai/api/v1/chat/completions"),
        "--decision-model", "" if args.offline else os.getenv("AGENT_PROVIDER_MODEL", "openai/gpt-6-luna-decisions"),
        "--repair-model", "" if args.offline else os.getenv("DUO_PROVIDER_MODEL", "deepseek/deepseek-v4.1-flash"),
    ])


if __name__ == "__main__":
    run()
