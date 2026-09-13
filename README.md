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

## What's here

```
standard/openai-v1/
  profile.yml        338 operations, each with its tier and the evidence for it
  openapi.yml        the core + extended surface, self-contained, x-tier on every operation
  overlay.yml        an OpenAPI Overlay that stamps the tiers onto the upstream spec
  schema/            JSON Schema 2020-12 for the core request and response bodies
  mcp/tools.json     MCP tool definitions for the core tier
  arazzo/            the flow that proves a core claim: list models, then use one
  spectral/          lint any spec against the profile
adopters/
  adopters.yml       175 entries, each with the URL it was read from and the date
  matrix.md          generated: operation x adopter
scripts/             every artifact above is generated; none is hand-maintained
```

## Check a provider

```
npx @stoplight/spectral-cli lint their-openapi.yaml \
  -r https://raw.githubusercontent.com/api-commons/models/main/standard/openai-v1/spectral/openai-profile.yaml
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
python3 scripts/build-profile.py --spec openai.yaml --sha <commit> \
        --census census.json --cohort 120 --claimants 211
python3 scripts/build-artifacts.py
python3 scripts/harvest-adopters.py
node scripts/test-ruleset.mjs
```

The upstream spec moves weekly, so re-pinning is a deliberate versioned act rather
than a silent drift.

## Provenance

Derived from [openai/openai-openapi](https://github.com/openai/openai-openapi) at commit
`38170fdddbb6a1813eae6c6587ee17cf2987185b` — OpenAPI 3.1.0, `info.version` 2.3.0, 215 paths, 338 operations. That repository
is **MIT**; this profile carries its attribution and does not republish it.

Not published by, affiliated with, or endorsed by OpenAI. "OpenAI" appears here as a
factual reference to the interface being described.

## Part of API Commons

**Related**
- [adopters](https://github.com/api-commons/adopters) — the schema behind the registry
- [storage](https://github.com/api-commons/storage) · [open-data](https://github.com/api-commons/open-data) · [blockchain](https://github.com/api-commons/blockchain) — the other standards from practice
- [api-validator](https://github.com/api-commons/api-validator) — lint in the browser

## License

Artifacts — the profile, schemas, and API descriptions — are licensed
**[CC BY-NC-SA 4.0](LICENSE)**. Code — everything in `scripts/` — is licensed
**[Apache-2.0](LICENSE-CODE)**.
