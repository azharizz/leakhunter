from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
from pathlib import Path

import yaml


INVARIANTS = {
    "secret_fields_never_in_external_payloads",
    "cross_tenant_reads_must_be_authorized",
    "no_real_secrets_in_test_artifacts",
}


def _keys(value: dict, allowed: set[str], name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unsupported {name} keys: {sorted(map(str, unknown))}")


def _strings(value, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    return value


class Policy:
    """Validated rank-based transfer policy; absent required context is not permission."""

    def __init__(self, raw: dict):
        _keys(raw, {"version", "classifications", "sources", "sinks", "invariants", "status", "approved_by"}, "policy")
        self.raw = copy.deepcopy(raw)
        self.version = raw.get("version", 1)
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(raw.get("status", "approved"), str) or raw.get("status", "approved") not in {"draft", "approved", "retired"}:
            raise ValueError("status must be draft, approved or retired")
        if "approved_by" in raw and (not isinstance(raw["approved_by"], str) or not raw["approved_by"].strip()):
            raise ValueError("approved_by must be a nonempty string")
        self.classifications = self.raw.get("classifications", {"PUBLIC": 0})
        if not isinstance(self.classifications, dict) or "PUBLIC" not in self.classifications:
            raise ValueError("classifications must contain PUBLIC")
        if any(not isinstance(key, str) or not key or not isinstance(rank, int) or isinstance(rank, bool) or rank < 0
               for key, rank in self.classifications.items()):
            raise ValueError("classifications must map names to nonnegative integer ranks")
        if self.classifications["PUBLIC"] != 0:
            raise ValueError("PUBLIC classification must have rank zero")
        self.sources = self.raw.get("sources", [])
        if not isinstance(self.sources, list):
            raise ValueError("sources must be a list")
        for source in self.sources:
            _keys(source, {"selector", "class"}, "source")
            if not isinstance(source.get("selector"), str) or not source["selector"]:
                raise ValueError("source selector must be a nonempty string")
            if not isinstance(source.get("class"), str) or source["class"] not in self.classifications:
                raise ValueError("source class must name a classification")
        sinks = self.raw.get("sinks", [])
        if not isinstance(sinks, list):
            raise ValueError("sinks must be a list")
        self.sinks = {}
        for sink in sinks:
            _keys(sink, {"kind", "allow", "audience", "recipient", "deny_fields", "require_contract", "require_authorization", "same_tenant"}, "sink")
            kind = sink.get("kind")
            if not isinstance(kind, str) or not kind or kind in self.sinks:
                raise ValueError("sink kind must be a unique nonempty string")
            for classification in _strings(sink.get("allow", ["PUBLIC"]), "sink allow"):
                if classification not in self.classifications:
                    raise ValueError(f"unknown allowed classification: {classification}")
            _strings(sink.get("deny_fields", []), "deny_fields")
            for key in ("audience", "recipient"):
                if key in sink:
                    values = [sink[key]] if isinstance(sink[key], str) else sink[key]
                    if not _strings(values, key):
                        raise ValueError(f"{key} must not be empty")
            for key in ("require_authorization", "same_tenant"):
                if key in sink and not isinstance(sink[key], bool):
                    raise ValueError(f"{key} must be boolean")
            contract = sink.get("require_contract", False)
            if not isinstance(contract, (bool, str)) or isinstance(contract, str) and not contract:
                raise ValueError("require_contract must be boolean or a nonempty contract name")
            self.sinks[kind] = sink
        self.invariants = _strings(self.raw.get("invariants", []), "invariants")
        unknown = set(self.invariants) - INVARIANTS
        if unknown:
            raise ValueError(f"unsupported invariants: {sorted(unknown)}")
        semantic = {key: value for key, value in self.raw.items() if key not in {"status", "approved_by"}}
        self.digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def classify(self, symbol: str) -> str:
        matches = [source["class"] for source in self.sources if fnmatch.fnmatchcase(symbol, source["selector"])]
        return max(matches, key=self.classifications.get) if matches else "PUBLIC"

    def evaluate(self, classification: str, sink_kind: str, symbol: str = "", context: dict | None = None) -> dict:
        context = {} if context is None else context
        if not isinstance(context, dict):
            raise ValueError("context must be a mapping")
        if any(not isinstance(value, str) for value in (classification, sink_kind, symbol)):
            raise ValueError("classification, sink kind and symbol must be strings")
        for key in ("audience", "recipient"):
            if key in context and (not isinstance(context[key], str) or not context[key]):
                raise ValueError(f"context {key} must be a nonempty string")
        for key in ("authorized", "synthetic"):
            if key in context and not isinstance(context[key], bool):
                raise ValueError(f"context {key} must be boolean")
        for key in ("tenant", "source_tenant"):
            if key in context and context[key] is not None and (not isinstance(context[key], (str, int)) or isinstance(context[key], bool)):
                raise ValueError(f"context {key} must be a string or integer tenant identifier")
        if "contract" in context:
            actual = context["contract"]
            if isinstance(actual, list):
                _strings(actual, "context contract")
            elif not isinstance(actual, (bool, str)) and actual is not None:
                raise ValueError("context contract must be boolean, a string or a string list")
        sink = self.sinks.get(sink_kind, {"allow": ["PUBLIC"]})
        reasons = []
        if classification not in self.classifications:
            reasons.append("unknown_classification")
        elif not any(self.classifications[classification] <= self.classifications[item]
                     for item in sink.get("allow", ["PUBLIC"])):
            reasons.append("classification_not_allowed")
        for key in ("audience", "recipient"):
            if key in sink:
                allowed = sink[key] if isinstance(sink[key], list) else [sink[key]]
                if context.get(key) not in allowed:
                    reasons.append(f"{key}_not_allowed" if key in context else f"{key}_unknown")
        if any(fnmatch.fnmatchcase(symbol, pattern) for pattern in sink.get("deny_fields", [])):
            reasons.append("field_denied")
        contract = sink.get("require_contract", False)
        actual = context.get("contract")
        if contract and (not actual or isinstance(contract, str) and
                         not (actual == contract or isinstance(actual, list) and contract in actual)):
            reasons.append("required_contract_missing")
        if sink.get("require_authorization") and context.get("authorized") is not True:
            reasons.append("authorization_required")
        tenant, source_tenant = context.get("tenant"), context.get("source_tenant")
        tenant_known = tenant is not None and source_tenant is not None and tenant != "" and source_tenant != ""
        if sink.get("same_tenant") and (not tenant_known or tenant != source_tenant):
            reasons.append("same_tenant_required")
        if "cross_tenant_reads_must_be_authorized" in self.invariants:
            if not tenant_known:
                reasons.append("tenant_context_unknown")
            elif tenant_known and tenant != source_tenant and context.get("authorized") is not True:
                reasons.append("cross_tenant_authorization_required")
        audience = context.get("audience", sink.get("audience"))
        external = sink_kind in {"HTTP_RESPONSE", "WEBHOOK", "THIRD_PARTY_ANALYTICS", "AI_PROMPT", "EMAIL", "URL", "CLOUD_STORAGE"}
        external = external or isinstance(audience, str) and audience in {"external_vendor", "public", "approved_partner"}
        if "secret_fields_never_in_external_payloads" in self.invariants and classification == "SECRET" and external:
            reasons.append("secret_fields_never_in_external_payloads")
        if ("no_real_secrets_in_test_artifacts" in self.invariants and
                sink_kind in {"TEST_ARTIFACT", "CI_ARTIFACT"} and classification != "PUBLIC" and context.get("synthetic") is not True):
            reasons.append("no_real_secrets_in_test_artifacts")
        return {"allowed": not reasons, "reasons": reasons}

    def allows(self, classification: str, sink_kind: str) -> bool:
        """Return whether a transfer is allowed without exposing policy details."""
        return self.evaluate(classification, sink_kind)["allowed"]


def load_policy(path: Path) -> Policy:
    return Policy(yaml.safe_load(Path(path).read_text()))
