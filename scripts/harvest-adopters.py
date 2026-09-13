#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the adopter registry from the API Evangelist catalog.

Evidence rules, applied without exception:

  declared  the provider publishes their own OpenAPI, harvested byte-identical from
            their site, and it declares operations in this profile. evidence_url points
            at that harvested artifact so anyone can check the grading.
  prose     the provider states compatibility in their own words and publishes no spec
            we can read. Recorded, and never promoted to a verdict.

A tier is only ever recorded for a `declared` entry, because only there is there an
artifact to read. Reaching a tier means:

  core      declares both core operations
  extended  reaches core AND declares at least one extended operation

A provider that declares only one core operation reaches no tier, and its
tier_verified stays null rather than being rounded up.
"""
import argparse, glob, json, os, re
from datetime import date
from pathlib import Path

import yaml

try:
    Loader, Dumper = yaml.CSafeLoader, yaml.CSafeDumper
except AttributeError:
    Loader, Dumper = yaml.SafeLoader, yaml.SafeDumper

ROOT = Path("/Users/kinlane/GitHub/all")
HERE = Path(__file__).resolve().parent.parent
S = Path("/private/tmp/claude-501/-Users-kinlane-GitHub/a4a7c19c-602a-46a7-b631-c682b206bbdf/scratchpad")
TODAY = date.today().isoformat()

ap = argparse.ArgumentParser()
ap.add_argument("--standard", default="openai-v1")
ap.add_argument("--candidates-key", default="OpenAI API",
                help="key in candidates.json naming the providers that CLAIM this standard")
ap.add_argument("--census", default="openai_declares.json")
ap.add_argument("--cohort", default="reimplementation")
ap.add_argument("--restrict-to-census", action="store_true", help=(
    "Only include providers present in the census. Use when a standard shares path shapes "
    "with another in the same domain, so that a prose claim cannot be cross-checked."))
args = ap.parse_args()
STANDARD = args.standard

profile = yaml.load((HERE / "standard" / STANDARD / "profile.yml").read_text(), Loader=Loader)
CORE = {f"{o['method']} {o['path']}" for o in profile["operations"] if o["tier"] == "core"}
EXTENDED = {f"{o['method']} {o['path']}" for o in profile["operations"] if o["tier"] == "extended"}

PREFIX = re.compile(r"^/(?:openai/)?(?:api/)?v\d+(?:beta\d*)?", re.I)
PARAM = re.compile(r"\{[^}]+\}")


def norm_key(key):
    method, path = key.split(" ", 1)
    return f"{method} {PARAM.sub('{x}', PREFIX.sub('', path)).rstrip('/').lower() or '/'}"


CORE_N = {norm_key(k) for k in CORE}
EXTENDED_N = {norm_key(k) for k in EXTENDED}

claimants = json.loads((S / "candidates.json").read_text())[args.candidates_key]
declares = json.loads((S / args.census).read_text())

by_slug = {}
for key, slugs in declares.items():
    for slug in slugs:
        by_slug.setdefault(slug, set()).add(key)

RELEVANT = {"Models", "LLM", "Inference", "Artificial Intelligence", "Machine Learning",
            "Generative AI", "AI", "Natural Language Processing", "API"}


def provider_facts(slug):
    """Name, a page the provider controls, and tags — read from their catalog entry."""
    path = ROOT / slug / "apis.yml"
    if not path.exists():
        return slug, None, []
    try:
        d = yaml.load(path.read_text(errors="ignore"), Loader=Loader)
    except Exception:
        return slug, None, []
    name = d.get("name") or slug
    tags = [t for t in (d.get("tags") or []) if t in RELEVANT]
    claim = None
    for api in d.get("apis") or []:
        for prop in api.get("properties") or []:
            url = prop.get("url") or ""
            if prop.get("type") in ("Documentation", "SwaggerUI") and url.startswith("http"):
                claim = url
                break
        if claim:
            break
    if not claim:
        for prop in (d.get("properties") or []):
            url = prop.get("url") or ""
            if prop.get("type") in ("Website", "Documentation") and url.startswith("http"):
                claim = url
                break
    return name, claim, sorted(set(tags))


def harvested_spec_url(slug):
    files = sorted(glob.glob(str(ROOT / slug / "openapi" / "_original" / "*")))
    if not files:
        return None
    return (f"https://raw.githubusercontent.com/api-evangelist/{slug}/main/"
            f"openapi/_original/{os.path.basename(files[0])}")


adopters, skipped = [], []
counts = {"declared": 0, "prose": 0, "core": 0, "extended": 0, "no_tier": 0}

population = sorted(set(claimants) | set(by_slug)) if not args.restrict_to_census \
    else sorted(set(claimants) & set(by_slug) | (set(by_slug) & set(claimants)))
if args.restrict_to_census:
    population = sorted(by_slug)

for slug in population:
    name, claim_url, tags = provider_facts(slug)
    if not claim_url:
        skipped.append(slug)
        continue

    ops = {norm_key(k) for k in by_slug.get(slug, set())}
    entry = {
        "name": name,
        "aid": slug,
        "standard": STANDARD,
        "claim_url": claim_url,
        "source_date": TODAY,
        "evidence": "prose",
        "tier_claimed": None,
        "tier_verified": None,
        "software_version": None,
        "tags": tags,
    }

    if ops:
        spec_url = harvested_spec_url(slug)
        entry["evidence"] = "declared"
        entry["evidence_url"] = spec_url
        counts["declared"] += 1
        reaches_core = CORE_N.issubset(ops)
        if reaches_core and ops & EXTENDED_N:
            tier = "extended"
        elif reaches_core:
            tier = "core"
        else:
            tier = None
        if tier:
            entry["tier_verified"] = tier
            entry["verified_on"] = TODAY
            counts[tier] += 1
        else:
            counts["no_tier"] += 1
            entry["divergence"] = [{
                "operation": " and ".join(sorted(CORE - {k for k in CORE if norm_key(k) in ops})),
                "note": ("Publishes an OpenAPI that declares part of this profile but not the "
                         "whole core tier, so no tier is recorded."),
                "url": spec_url,
            }]
    else:
        counts["prose"] += 1

    # Field order, so the file reads the same way everywhere.
    order = ["name", "aid", "standard", "claim_url", "source_date", "evidence", "evidence_url",
             "tier_claimed", "tier_verified", "verified_on", "software_version", "tags",
             "divergence"]
    adopters.append({k: entry[k] for k in order if k in entry})

doc = {
    "standard": STANDARD,
    "standard_url": "https://github.com/api-commons/models",
    "cohort": args.cohort,
    "source_date": TODAY,
    "generated_by": "scripts/harvest-adopters.py",
    "adopters": adopters,
}
(HERE / "adopters" / f"{STANDARD}.yml").write_text(
    "# SPDX-License-Identifier: CC-BY-NC-SA-4.0\n"
    "# Generated by scripts/harvest-adopters.py — do not hand-edit.\n"
    "# Every entry carries the URL it was read from and the date it was read.\n"
    + yaml.dump(doc, Dumper=Dumper, sort_keys=False, width=100, allow_unicode=True))

print(f"adopters:  {len(adopters)} entries  (skipped {len(skipped)} with no citable page)")
print(f"evidence:  declared {counts['declared']} · prose {counts['prose']}")
print(f"tiers:     core {counts['core']} · extended {counts['extended']} · "
      f"no tier {counts['no_tier']}")
if skipped:
    print(f"skipped:   {', '.join(skipped[:12])}{' …' if len(skipped) > 12 else ''}")


def write_matrix():
    """Operation x adopter, generated. Never hand-maintained."""
    ops = [o for o in profile["operations"] if o["tier"] in ("core", "extended")]
    ops.sort(key=lambda o: (-o["percent_of_cohort"], o["path"]))
    declared = [a for a in adopters if a["evidence"] == "declared"]
    rows = [f"# Adopter matrix — {profile['title']}",
            "",
            "Generated by `scripts/harvest-adopters.py`. Do not hand-edit.",
            "",
            f"Measured {TODAY} against {len(declared)} providers who publish their own OpenAPI, "
            f"out of {len(claimants)} that state {profile.get('originator', 'this')} "
            "compatibility in the "
            "[API Evangelist](https://apis.io) catalog. A provider may implement an operation "
            "without publishing a spec, so every share below is a floor.",
            "",
            "## By operation",
            "",
            "| Operation | Tier | Adopters | Share of cohort | |",
            "| --- | --- | ---: | ---: | --- |"]
    for o in ops:
        flag = ("**shared shape** — also an operation in another profile in this domain, "
                "so a declaration cannot be attributed to one interface by path alone"
                if o.get("ambiguous") else "")
        rows.append(f"| `{o['method']} {o['path']}` | {o['tier']} | {o['adopters_declaring']} "
                    f"| {o['percent_of_cohort']}% | {flag} |")
    tiers = {"extended": [], "core": [], None: []}
    for a in declared:
        tiers.setdefault(a["tier_verified"], []).append(a["name"])
    rows += ["", "## By adopter", "",
             f"**Reaches extended** ({len(tiers['extended'])}) — declares both core operations "
             "and at least one extended one.", "",
             ", ".join(sorted(tiers["extended"])) or "_none_", "",
             f"**Reaches core** ({len(tiers['core'])}) — declares both core operations.", "",
             ", ".join(sorted(tiers["core"])) or "_none_", "",
             f"**Publishes a spec, reaches no tier** ({len(tiers[None])}) — declares part of "
             "this profile but not the whole core tier. Not a failing grade: a partial "
             "implementation is a normal thing to be, and it is recorded rather than rounded up.",
             "", ", ".join(sorted(tiers[None])) or "_none_", ""]
    (HERE / "adopters" / f"{STANDARD}-matrix.md").write_text("\n".join(rows))
    print(f"{STANDARD}-matrix.md  {len(ops)} operations x {len(declared)} declaring adopters")


write_matrix()
