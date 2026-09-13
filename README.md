# Models

De facto standards for the model layer, published by the
[API Commons](https://apicommons.org).

OpenAI published an API. The industry turned it into a wire format. Today a chat
completion request written for one provider runs against hundreds of others, and
"OpenAI-compatible" appears in the documentation of **211 providers** in the
[API Evangelist](https://apis.io) catalog — without anyone ever having written down what
the phrase commits you to.

This repository writes it down.

## What "compatible" turns out to mean

Two operations.

| Operation | Adopters | Share |
| --- | ---: | ---: |
| `POST /chat/completions` | 105 | 87.5% |
| `GET /models` | 86 | 71.7% |
| `POST /embeddings` | 39 | 32.5% |

Nothing else clears a third of the cohort. The gap between 71.7% and 32.5% is the
tier boundary, and it was measured rather than chosen: every one of OpenAI's 338
operations is graded by the share of adopters who declare it in **their own**
published OpenAPI.

Of the 211 providers claiming compatibility, **67 demonstrably reach the core tier**.
101 publish a spec we can read; 34 of those declare part of the profile but not all of
it. The rest say it in prose. None of that is a failing grade — a partial
implementation is a normal thing to be. It is recorded rather than rounded up.

## The second dialect

A growing share of model hosts speak Anthropic's Messages API alongside OpenAI's. Profiling
it turned out to need a different denominator, and the reason is worth stating plainly.

**29 of Anthropic's operations share a path shape with the OpenAI interface** — `/models`,
`/files`, `/skills`, `/vaults`, `/agents`. Measured against everyone who publishes a spec,
`GET /models` came out at 86.3% for the Anthropic profile. That number was measuring OpenAI.
The cohort is therefore restricted to the **29 providers declaring at least one operation
unique to Anthropic**, and every shared operation carries `ambiguous: true` in the profile
and a warning in the matrix.

| Operation | Adopters | Share |
| --- | ---: | ---: |
| `GET /v1/models` | 21 | 72.4% (shared shape) |
| `POST /v1/messages` | 20 | 69.0% |
| `POST /v1/messages/count_tokens` | 4 | 13.8% |

The dialects differ in a way that breaks shims: **Anthropic requires `max_tokens`** where
OpenAI treats it as optional, and returns `content` blocks where OpenAI returns `choices`.
Both are rules in the Anthropic ruleset, and both fire on real providers — `0g-labs` and
`friendliai` declare a messages request without `max_tokens`.

## What's here

```
standard/openai-v1/              338 operations graded, 2 core
standard/anthropic-messages-v1/  244 operations graded, 2 core
  profile.yml        every operation with its tier and the evidence for it
  openapi.yml        the core + extended surface, self-contained, x-tier on every operation
  overlay.yml        an OpenAPI Overlay that stamps the tiers onto the upstream spec
  schema/            JSON Schema 2020-12 for the core request and response bodies
  mcp/tools.json     MCP tool definitions for the core tier
  arazzo/            the flow that proves a core claim: list models, then use one
  spectral/          lint any spec against the profile, with fixtures and a harness
adopters/
  openai-v1.yml                    175 entries
  anthropic-messages-v1.yml         20 entries
  *-matrix.md                      generated: operation x adopter
scripts/             every artifact above is generated; none is hand-maintained
```

## Check a provider

```
npx @stoplight/spectral-cli lint their-openapi.yaml \
  -r https://raw.githubusercontent.com/api-commons/models/main/standard/openai-v1/spectral/openai-profile.yaml

npx @stoplight/spectral-cli lint their-openapi.yaml \
  -r https://raw.githubusercontent.com/api-commons/models/main/standard/anthropic-messages-v1/spectral/anthropic-profile.yaml
```

It reports whether they reach the core tier and whether the operations they declare
have the shape a client written against OpenAI expects. Run against real providers on
2026-09-13: Groq and OpenRouter lint clean, Cerebras declares no model listing, and
DeepInfra's response shapes differ from the profile.

### What it does not check

Runtime behaviour — a spec is a claim about a server, not the server. Streaming
semantics, because SSE framing is not expressible in OpenAPI. Whether `gpt-4o` means
the same thing at two providers, which no ruleset can answer. Extended and vendor tiers
beyond one informational notice, because declaring them is not a defect.

### A known upstream limitation

`spectral:oas` cannot lint this profile. Spectral 6.16.3 crashes on it with
`Cannot read properties of null (reading 'enum')` — and crashes identically on OpenAI's
own untouched upstream spec, which is how we know it is not caused by anything done
here. It is not the null `default` or null `example` values either; both were ruled out
by elimination. The profile's own ruleset runs clean over the same document, and the
generated Arazzo and JSON Schema artifacts validate normally.

## Regenerate

```
python3 scripts/build-profile.py   --spec <upstream> --sha <commit> --census <census> \
                                   --cohort <n> --claimants <n> [--standard <id>] ...
python3 scripts/build-artifacts.py --standard <id>
python3 scripts/harvest-adopters.py --standard <id> --candidates-key "<claim>" --census <census>
node scripts/test-ruleset.mjs      # every profile, every rule, both clean fixtures
```

The upstream spec moves weekly, so re-pinning is a deliberate versioned act rather
than a silent drift.

## Provenance

**The OpenAI interface** is derived from
[openai/openai-openapi](https://github.com/openai/openai-openapi) at commit
`38170fdddbb6a1813eae6c6587ee17cf2987185b` — OpenAPI 3.1.0, `info.version` 2.3.0, 215 paths, 338 operations. That repository
is **MIT**; this profile carries its attribution and does not republish it.

**The Anthropic Messages dialect** is derived from `scripts/mock-spec.json.gz` in
[anthropics/anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) —
OpenAPI 3.1.0, 165 paths, 244 operations, no declared `info.version`. That repository is
**MIT**. Anthropic bundled this spec into their own repo on 2026-09-03, in the same commit
that removed the Stainless CDN URL from `.stats.yml`; the in-repo file is a better source
than the CDN copy, because it is first-party and pinnable by commit.

Not published by, affiliated with, or endorsed by OpenAI or Anthropic. Both names appear
here as factual references to the interfaces being described.

## Part of API Commons

**Related**
- [adopters](https://github.com/api-commons/adopters) — the schema behind the registry
- [storage](https://github.com/api-commons/storage) · [open-data](https://github.com/api-commons/open-data) · [blockchain](https://github.com/api-commons/blockchain) — the other standards from practice
- [api-validator](https://github.com/api-commons/api-validator) — lint in the browser

## License

Artifacts — the profile, schemas, and API descriptions — are licensed
**[CC BY-NC-SA 4.0](LICENSE)**. Code — everything in `scripts/` — is licensed
**[Apache-2.0](LICENSE-CODE)**.
