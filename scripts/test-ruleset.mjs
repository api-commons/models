// SPDX-License-Identifier: Apache-2.0
//
// The harness is the contract. It asserts three things:
//   1. every rule declared in the ruleset fires on at least one failing fixture
//   2. the clean fixture is silent
//   3. no rule throws
//
// Rule ids are parsed straight out of the YAML, so adding a rule without a fixture
// case fails the build rather than shipping a rule that only appears to check something.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// Every profile in the repo, so adding one without fixtures fails the build.
const PROFILES = [
  { standard: "openai-v1", ruleset: "openai-profile.yaml" },
  { standard: "anthropic-messages-v1", ruleset: "anthropic-profile.yaml" },
];

const FAILING = ["noncompliant.yaml", "missing-core.yaml"];
const CLEAN = ["clean.yaml", "clean-composed.yaml"];

let SPECTRAL, RULESET, FIXTURES, declared;

function lint(fixture) {
  const file = resolve(FIXTURES, fixture);
  try {
    const out = execFileSync(
      "npx",
      ["--yes", "@stoplight/spectral-cli", "lint", file, "-r", RULESET, "-f", "json", "-q"],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
    return JSON.parse(out || "[]");
  } catch (err) {
    // Spectral exits non-zero when it finds problems; that is the normal path here.
    const stdout = (err.stdout || "").trim();
    if (!stdout.startsWith("[")) {
      console.error(`\n  spectral failed on ${fixture}:\n${err.stderr || err.message}`);
      process.exit(1);
    }
    return JSON.parse(stdout);
  }
}

let anyFailed = false;

for (const profile of PROFILES) {
SPECTRAL = resolve(HERE, `../standard/${profile.standard}/spectral`);
RULESET = resolve(SPECTRAL, profile.ruleset);
FIXTURES = resolve(SPECTRAL, "fixtures");
declared = [
  ...readFileSync(RULESET, "utf8").matchAll(/^ {2}([a-z][a-z0-9-]*):$/gm),
].map((m) => m[1]);

console.log(`\n=== ${profile.standard} — ${profile.ruleset}, ${declared.length} rules ===\n`);

const fired = new Set();
for (const fixture of FAILING) {
  const results = lint(fixture);
  const codes = [...new Set(results.map((r) => r.code))];
  codes.forEach((c) => fired.add(c));
  console.log(`  ${fixture}: ${results.length} findings across ${codes.length} rules`);
  for (const code of codes.sort()) {
    const n = results.filter((r) => r.code === code).length;
    console.log(`      · ${code} (${n})`);
  }
}

const cleanResults = [];
for (const fixture of CLEAN) {
  const results = lint(fixture);
  console.log(`\n  ${fixture}: ${results.length} findings`);
  for (const r of results) console.log(`      · ${r.code}: ${r.message}`);
  cleanResults.push(...results);
}

const dead = declared.filter((r) => !fired.has(r));
const unknown = [...fired].filter((r) => !declared.includes(r));

console.log();
let failed = false;
if (dead.length) {
  console.log(`FAIL  ${dead.length} rule(s) never fired — they check nothing:`);
  dead.forEach((r) => console.log(`        · ${r}`));
  failed = true;
} else {
  console.log(`PASS  all ${declared.length} rules fire on a fixture`);
}
if (unknown.length) {
  console.log(`FAIL  findings from undeclared rules: ${unknown.join(", ")}`);
  failed = true;
}
if (cleanResults.length) {
  console.log(`FAIL  a clean fixture is not silent`);
  failed = true;
} else {
  console.log(`PASS  both clean fixtures are silent`);
}

if (failed) anyFailed = true;
}

process.exit(anyFailed ? 1 : 0);
