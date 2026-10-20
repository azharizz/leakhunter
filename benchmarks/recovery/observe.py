"""Real-GitLab read-only recovery drill; requires an existing MR and review config.

Use an installed Unspool interpreter outside the target checkout. The wrapper
never substitutes a server response, permits mutations or changes verifier logic.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import time

from unspool.handoff import GitLab, from_issue
from unspool.handoff_config import HandoffConfig
from unspool.handoff_state import RunJournal


class ReadOnlyObservation:
    def __init__(self, api, fault):
        self.api, self.fault, self.reads = api, fault, 0

    def request(self, method, path, body=None):
        if method != "GET":
            raise RuntimeError("Recovery drill refuses all GitLab mutations; an existing MR is required")
        result = self.api.request(method, path, body)
        self.reads += 1
        mr_read = "/merge_requests/" in path and path.rsplit("/", 1)[-1].isdigit()
        evidence_read = "/artifacts/" in path and path.endswith("evidence.json")
        boundary = "after-mr" if mr_read else "after-evidence" if evidence_read else None
        if boundary and self.fault in {boundary, "hold-" + boundary}:
            print(json.dumps({"event": "fault-boundary", "boundary": boundary, "reads": self.reads}), flush=True)
            if self.fault.startswith("hold-"):
                time.sleep(30)
                raise RuntimeError("Controller was not interrupted during the hold window")
            os.kill(os.getpid(), signal.SIGKILL)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--fault", choices=("none", "after-mr", "after-evidence", "hold-after-mr"), default="none")
    args = parser.parse_args()
    config = HandoffConfig.load(args.config)
    if config.mode != "review" or args.issue <= 0:
        parser.error("A review-only configuration and positive existing issue are required")
    api = ReadOnlyObservation(GitLab(), args.fault)
    with RunJournal(args.state_dir, config.project_id, config.target_branch, f"issue:{args.issue}", config.digest) as journal:
        result = from_issue(config.project_id, args.issue, api=api, config=config,
                            timeout=config.timeout, interval=config.poll_interval, journal=journal)
    print(json.dumps({"result": result, "read_requests": api.reads, "write_requests": 0}))


if __name__ == "__main__":
    main()
