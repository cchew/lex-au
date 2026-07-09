# AU Legislative Intelligence Stack — discovery

Read this first if you're an agent (or a human) connecting to any repo in this stack for
the first time. It tells you what exists, where, and which tool to call for which question.

## Components

```
Corpus:       lex-au         — AKN 3.0 XML corpus (this repo)
Retrieval:    lex-au-search  — hybrid search API + MCP
              lex-au-graph   — cross-reference graph + definition resolution
Applications: ClauseKit       — rule extraction JSON (obligation/trigger/threshold/penalty)
              term-comparison — definition-comparison bot (IM2026 entry)
```

All four downstream repos consume lex-au's AKN XML corpus. `lex-au-search` and
`lex-au-graph` are peers at the retrieval layer — neither supersedes the other, they
answer different questions (see below). `ClauseKit` and `term-comparison` are peers at
the applications layer — both are consumer-facing tools built on the retrieval layer,
not on each other.

- lex-au: https://github.com/cchew/lex-au (this repo)
- lex-au-search: https://github.com/cchew/lex-au-search
- lex-au-graph: https://github.com/cchew/lex-au-graph
- ClauseKit: https://github.com/cchew/clause-kit
- term-comparison: IM2026 "Build a Bureaucrat Bot" entry, not yet public

## Which tool to call

| Question shape | Call this | Not this |
|---|---|---|
| "What does the law say about X?" / topic search | `lex-au-search`'s `search_legislation` MCP tool | — |
| "What does term X mean?" / cross-Act definition chains | `lex-au-graph`'s `resolve_definition` / `find_all_definitions` MCP tool | `lex-au-search` alone — it matches on semantic similarity and can return the wrong Act's use of a homonymous term |
| "Give me the full text of Act X" | `lex-au-search`'s `get_act_sections`, filtered | `get_act_text` — full-Act dumps exceed most context windows for large Acts (Corporations Act, Migration Act, Income Tax Assessment Act) |
| "Does this fact pattern trigger an obligation?" | `ClauseKit`'s rule JSON, if the Act/domain has been extracted | raw section text — check ClauseKit's `rules/` directory first |
| "Does this term mean the same thing everywhere?" | `term-comparison` | — |

## Precedence rule

For any query mentioning a defined term, call `lex-au-graph` before or alongside
`lex-au-search`. Graph resolution is authoritative (FRBR-scoped, deterministic); search is
fuzzy semantic retrieval. Skipping the graph call risks silently hallucinating a
definition from training data instead of the corpus.

## Compliance/quality caveats

AKN compliance percentages quoted in each repo's README are self-assessed estimates
against a manually catalogued applicable element set — not the output of an automated
conformance test. Treat as directional.
