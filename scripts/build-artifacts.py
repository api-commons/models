#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Derive the JSON Schema, MCP and Arazzo artifacts from the generated profile.

Everything here is generated from standard/openai-v1/openapi.yml so that a re-pin of
the upstream spec regenerates the whole artifact set. Nothing is hand-typed: long
lists that are hand-edited lose entries silently.
"""
import json, re
from pathlib import Path

import yaml

try:
    Loader, Dumper = yaml.CSafeLoader, yaml.CSafeDumper
except AttributeError:
    Loader, Dumper = yaml.SafeLoader, yaml.SafeDumper

import argparse

ROOT = Path(__file__).resolve().parent.parent

# Per-standard conformance flow. The payload differs because the dialects differ — most
# visibly, Anthropic requires max_tokens where OpenAI does not.
FLOWS = {
    "openai-v1": {
        "title": "OpenAI interface core conformance",
        "list_op": "listModels",
        "call_op": "createChatCompletion",
        "list_path": "GET /models",
        "call_path": "POST /chat/completions",
        "list_share": "71.7%",
        "call_share": "87.5%",
        "list_output": "$response.body#/data/0/id",
        "list_criteria": "$.data[0].id",
        "payload": {
            "model": "$steps.listModels.outputs.modelId",
            "messages": [{"role": "user", "content": "$inputs.prompt"}],
        },
        "reply_criteria": "$.choices[0].message.content",
        "reply_output": "$response.body#/choices/0/message/content",
    },
    "anthropic-messages-v1": {
        "title": "Anthropic Messages core conformance",
        "list_op": "models_list",
        "call_op": "messages_post",
        "list_path": "GET /v1/models",
        "call_path": "POST /v1/messages",
        "list_share": "72.4%",
        "call_share": "69.0%",
        "list_output": "$response.body#/data/0/id",
        "list_criteria": "$.data[0].id",
        "payload": {
            "model": "$steps.models_list.outputs.modelId",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "$inputs.prompt"}],
        },
        "reply_criteria": "$.content[0].text",
        "reply_output": "$response.body#/content/0/text",
    },
}

_ap = argparse.ArgumentParser()
_ap.add_argument("--standard", default="openai-v1")
_args = _ap.parse_args()
STANDARD = _args.standard
FLOW = FLOWS[STANDARD]
STD = ROOT / "standard" / STANDARD
SPDX_ART = "# SPDX-License-Identifier: CC-BY-NC-SA-4.0\n"
METHODS = ("get", "post", "put", "patch", "delete")

spec = yaml.load((STD / "openapi.yml").read_text(), Loader=Loader)
profile = yaml.load((STD / "profile.yml").read_text(), Loader=Loader)
by_tier = {(o["method"], o["path"]): o["tier"] for o in profile["operations"]}


def deref(node, seen=None):
    """Inline $refs so each artifact stands alone. Cycles become a permissive object."""
    seen = seen or set()
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/"):
            ref = node["$ref"]
            if ref in seen:
                return {"type": "object", "description": f"Recursive reference to {ref}"}
            target = spec
            for part in ref[2:].split("/"):
                target = target.get(part, {})
            return deref(target, seen | {ref})
        return {k: deref(v, seen) for k, v in node.items() if k != "$ref"}
    if isinstance(node, list):
        return [deref(v, seen) for v in node]
    return node


def core_ops():
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in METHODS and isinstance(op, dict):
                if by_tier.get((method.upper(), path)) == "core":
                    yield path, method, op


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ---- JSON Schema: one per core request and response body --------------------
written = []
for path, method, op in core_ops():
    base = op.get("operationId") or slug(f"{method}-{path}")
    body = (op.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema")
    if body:
        doc = deref(body)
        doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        doc["$id"] = (f"https://raw.githubusercontent.com/api-commons/models/main/standard/"
                     f"{STANDARD}/schema/{base}-request.json")
        doc["title"] = f"{base} request"
        (STD / "schema" / f"{base}-request.json").write_text(json.dumps(doc, indent=2) + "\n")
        written.append(f"{base}-request.json")
    ok = (op.get("responses") or {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
    if ok:
        doc = deref(ok)
        doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        doc["$id"] = (f"https://raw.githubusercontent.com/api-commons/models/main/standard/"
                     f"{STANDARD}/schema/{base}-response.json")
        doc["title"] = f"{base} response"
        (STD / "schema" / f"{base}-response.json").write_text(json.dumps(doc, indent=2) + "\n")
        written.append(f"{base}-response.json")

# ---- MCP tool definitions for the core tier ---------------------------------
tools = []
for path, method, op in core_ops():
    name = op.get("operationId") or slug(f"{method}-{path}")
    body = (op.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema")
    schema = deref(body) if body else {"type": "object", "properties": {}}
    schema.pop("$schema", None)
    desc = (op.get("summary") or op.get("description") or name).strip().split("\n")[0]
    tools.append({
        "name": name,
        "description": f"{desc} Core-tier operation: {method.upper()} {path}.",
        "inputSchema": schema,
        "_meta": {
            "apicommons.org/standard": STANDARD,
            "apicommons.org/tier": "core",
            "apicommons.org/operation": f"{method.upper()} {path}",
        },
    })
(STD / "mcp" / "tools.json").write_text(json.dumps(
    {
        "$comment": ("MCP tool definitions for the core tier of the OpenAI interface profile. "
                     "Generated by scripts/build-artifacts.py — do not hand-edit. "
                     "SPDX-License-Identifier: CC-BY-NC-SA-4.0"),
        "standard": STANDARD,
        "tier": "core",
        "tools": tools,
    }, indent=2) + "\n")

# ---- Arazzo: the flow that proves a compatibility claim ---------------------
arazzo = {
    "arazzo": "1.0.1",
    "info": {
        "title": FLOW["title"],
        "version": "1.0.0",
        "summary": "Discover a model, then use it. The smallest flow that proves core-tier support.",
        "description": (
            "Run this against a provider that claims compatibility. Step one reads the model list "
            "and takes the first identifier it offers, so the flow never hardcodes a model name "
            "that only one provider serves. Step two sends the smallest possible request with it. "
            "A provider that completes both steps supports the interoperable core of this "
            "interface; a provider that cannot has no basis for the claim."
        ),
    },
    "sourceDescriptions": [{"name": "profile", "url": "./openapi.yml", "type": "openapi"}],
    "workflows": [{
        "workflowId": "core-conformance",
        "summary": "List models, then send the smallest request with the first one.",
        "description": (
            f"Both core operations in the order a real client uses them: {FLOW['list_path']} "
            f"({FLOW['list_share']} of the cohort) then {FLOW['call_path']} "
            f"({FLOW['call_share']})."
        ),
        "inputs": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "default": "Reply with the word: ok"}},
        },
        "steps": [
            {
                "stepId": FLOW["list_op"],
                "description": f"{FLOW['list_path']} — declared by {FLOW['list_share']} of the cohort.",
                "operationId": f"$sourceDescriptions.profile.{FLOW['list_op']}",
                "successCriteria": [
                    {"condition": "$statusCode == 200"},
                    {"context": "$response.body", "condition": FLOW["list_criteria"],
                     "type": "jsonpath"},
                ],
                "outputs": {"modelId": FLOW["list_output"]},
            },
            {
                "stepId": FLOW["call_op"],
                "description": f"{FLOW['call_path']} — declared by {FLOW['call_share']} of the cohort.",
                "operationId": f"$sourceDescriptions.profile.{FLOW['call_op']}",
                "requestBody": {"contentType": "application/json", "payload": FLOW["payload"]},
                "successCriteria": [
                    {"condition": "$statusCode == 200"},
                    {"context": "$response.body", "condition": FLOW["reply_criteria"],
                     "type": "jsonpath"},
                ],
                "outputs": {"reply": FLOW["reply_output"]},
            },
        ],
        "outputs": {
            "model": f"$steps.{FLOW['list_op']}.outputs.modelId",
            "reply": f"$steps.{FLOW['call_op']}.outputs.reply",
        },
    }],
}
(STD / "arazzo" / "core-conformance.yml").write_text(
    SPDX_ART + yaml.dump(arazzo, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True))

print(f"schema/   {len(written)} documents: {', '.join(written)}")
print(f"mcp/      {len(tools)} core tools: {', '.join(t['name'] for t in tools)}")
print(f"arazzo/   core-conformance.yml ({len(arazzo['workflows'][0]['steps'])} steps)")
