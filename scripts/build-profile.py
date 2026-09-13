#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the OpenAI interface profile from a pinned upstream spec.

Re-runnable: point it at a new SHA and every artifact regenerates. Nothing here is
hand-typed, because long lists that are hand-edited lose entries silently.

Tiers are measured, not asserted. The denominator is the set of adopters who publish
their own OpenAPI, and the evidence for every placement is written into profile.yml.
"""
import argparse, json, re, sys
from pathlib import Path

import yaml

try:
    Loader, Dumper = yaml.CSafeLoader, yaml.CSafeDumper
except AttributeError:
    Loader, Dumper = yaml.SafeLoader, yaml.SafeDumper

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "standard" / "openai-v1"

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
PREFIX = re.compile(r"^/(?:openai/)?(?:api/)?v\d+(?:beta\d*)?", re.I)
PARAM = re.compile(r"\{[^}]+\}")

CORE_MIN = 50.0      # a majority of the publishing cohort
EXTENDED_MIN = 5.0   # materially emulated


def norm(path: str) -> str:
    p = PREFIX.sub("", path) or "/"
    return PARAM.sub("{x}", p).rstrip("/").lower() or "/"


def tier_for(pct: float) -> str:
    if pct >= CORE_MIN:
        return "core"
    if pct >= EXTENDED_MIN:
        return "extended"
    return "vendor"


def collect_refs(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                acc.add(v)
            else:
                collect_refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_refs(v, acc)


def resolve(spec, ref):
    if not ref.startswith("#/"):
        return None
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def prune_components(spec, kept_paths):
    """Keep only the components the retained paths can actually reach."""
    seen, frontier = set(), set()
    collect_refs({p: spec["paths"][p] for p in kept_paths}, frontier)
    while frontier:
        ref = frontier.pop()
        if ref in seen:
            continue
        seen.add(ref)
        target = resolve(spec, ref)
        if target is None:
            continue
        nxt = set()
        collect_refs(target, nxt)
        frontier |= nxt - seen

    components = {}
    for ref in seen:
        parts = ref[2:].split("/")
        if len(parts) != 3 or parts[0] != "components":
            continue
        _, group, name = parts
        target = resolve(spec, ref)
        if target is not None:
            components.setdefault(group, {})[name] = target
    return components


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="pinned upstream openapi.yaml")
    ap.add_argument("--sha", required=True, help="upstream commit SHA this was read at")
    ap.add_argument("--census", required=True, help="normalized path -> [adopter slugs]")
    ap.add_argument("--cohort", type=int, required=True, help="adopters publishing a spec")
    ap.add_argument("--claimants", type=int, required=True, help="adopters claiming compatibility")
    args = ap.parse_args()

    spec = yaml.load(Path(args.spec).read_text(), Loader=Loader)
    census = json.loads(Path(args.census).read_text())

    operations, tier_counts = [], {"core": 0, "extended": 0, "vendor": 0}
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in METHODS or not isinstance(op, dict):
                continue
            # Keyed on METHOD + path. A path-level count credits every method on that
            # path equally, which graded `GET /chat/completions` at the adoption rate of
            # `POST /chat/completions` and `DELETE /models/{id}` at that of `GET`.
            adopters = sorted(census.get(f"{method.upper()} {norm(path)}", []))
            pct = round(100 * len(adopters) / args.cohort, 1)
            tier = tier_for(pct)
            tier_counts[tier] += 1
            operations.append({
                "operationId": op.get("operationId"),
                "method": method.upper(),
                "path": path,
                "tier": tier,
                "adopters_declaring": len(adopters),
                "percent_of_cohort": pct,
                "evidence": (
                    f"{len(adopters)} of {args.cohort} adopters that publish their own OpenAPI "
                    f"declare this operation ({pct}%)." if adopters else
                    "No adopter that publishes an OpenAPI declares this operation."
                ),
            })

    # ---- profile.yml -------------------------------------------------------
    profile = {
        "profile": "openai-v1",
        "title": "The OpenAI Interface",
        "generated": "2026-09-13",
        "generated_by": "scripts/build-profile.py",
        "upstream": {
            "repository": "https://github.com/openai/openai-openapi",
            "commit": args.sha,
            "license": "MIT",
            "openapi": spec["openapi"],
            "info_version": spec["info"]["version"],
            "paths": len(spec["paths"]),
            "operations": len(operations),
        },
        "method": {
            "summary": (
                "Tiers are measured against what adopters publish, not asserted. Each METHOD and "
                "path is graded by the share of the publishing cohort that declares it. Grading "
                "by path alone credits every method on a path equally, which is wrong: GET and "
                "POST on /chat/completions are not implemented at the same rate."
            ),
            "cohort": args.cohort,
            "claimants": args.claimants,
            "cohort_definition": (
                f"{args.claimants} providers in the API Evangelist catalog state OpenAI "
                f"compatibility. {args.cohort} of them publish an OpenAPI harvested byte-identical "
                "from their own site, and those are the denominator. A provider may implement an "
                "operation without publishing a spec, so these shares are a floor."
            ),
            "thresholds": {
                "core": f">= {CORE_MIN}% of the cohort",
                "extended": f">= {EXTENDED_MIN}% and < {CORE_MIN}%",
                "vendor": f"< {EXTENDED_MIN}%",
            },
            "tiers": {
                "core": "Implement these or a compatibility claim is false.",
                "extended": "Materially emulated, and where implementations diverge.",
                "vendor": "Effectively OpenAI-only in practice.",
            },
        },
        "counts": tier_counts,
        "operations": sorted(operations, key=lambda o: (-o["percent_of_cohort"], o["path"], o["method"])),
    }
    (OUT / "profile.yml").write_text(
        "# SPDX-License-Identifier: CC-BY-NC-SA-4.0\n"
        + yaml.dump(profile, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True)
    )

    # ---- openapi.yml: core + extended, self-contained -----------------------
    by_path = {}
    for o in operations:
        by_path.setdefault(o["path"], set()).add(o["tier"])
    kept = [p for p, tiers in by_path.items() if tiers & {"core", "extended"}]

    paths_out = {}
    for path in kept:
        item = dict(spec["paths"][path])
        for method in list(item):
            if method in METHODS and isinstance(item[method], dict):
                op = dict(item[method])
                op["x-tier"] = next(o["tier"] for o in operations
                                    if o["path"] == path and o["method"] == method.upper())
                item[method] = op
        paths_out[path] = item

    out = {
        "openapi": spec["openapi"],
        "info": {
            "title": "The OpenAI Interface — API Commons profile",
            "summary": "The interoperable surface of the OpenAI API, as adopters actually implement it.",
            "description": (
                "A **profile**, not a copy. The OpenAI API became a de facto standard by being "
                "implemented by other people; this describes the part of it that the industry "
                "actually built, with every operation graded `x-tier` core or extended by measured "
                "adoption. Vendor-tier operations are documented in `profile.yml` and deliberately "
                "excluded here.\n\n"
                f"Derived from https://github.com/openai/openai-openapi at commit `{args.sha}` "
                "(MIT). Not published by, affiliated with, or endorsed by OpenAI.\n\n"
                "See https://github.com/api-commons/models for the profile and the adopter registry."
            ),
            "version": spec["info"]["version"],
            "contact": {"name": "API Commons", "url": "https://apicommons.org"},
            "license": {"name": "CC-BY-NC-SA-4.0",
                        "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"},
        },
        "externalDocs": {"description": "The profile on API Commons",
                         "url": "https://apicommons.org/standards/models/"},
        "servers": spec.get("servers", []),
        "paths": paths_out,
        "components": prune_components(spec, kept),
    }
    (OUT / "openapi.yml").write_text(
        "# SPDX-License-Identifier: CC-BY-NC-SA-4.0\n"
        + yaml.dump(out, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True)
    )

    # ---- overlay.yml: stamp x-tier onto the upstream spec --------------------
    actions = []
    for o in sorted(operations, key=lambda o: (o["path"], o["method"])):
        target = f"$.paths['{o['path']}'].{o['method'].lower()}"
        actions.append({"target": target, "update": {"x-tier": o["tier"]}})
    overlay = {
        "overlay": "1.0.0",
        "info": {
            "title": "OpenAI interface tiers",
            "version": "1.0.0",
            "description": (
                "Applies the API Commons tier grading to the upstream OpenAI OpenAPI without "
                f"copying it. Written against commit {args.sha}."
            ),
        },
        "actions": actions,
    }
    (OUT / "overlay.yml").write_text(
        "# SPDX-License-Identifier: CC-BY-NC-SA-4.0\n"
        + yaml.dump(overlay, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True)
    )

    print(f"profile.yml   {len(operations)} operations graded  {tier_counts}")
    print(f"openapi.yml   {len(kept)} paths kept (core + extended), "
          f"{sum(len(v) for v in out['components'].values())} components reachable")
    print(f"overlay.yml   {len(actions)} tier actions")


if __name__ == "__main__":
    main()
