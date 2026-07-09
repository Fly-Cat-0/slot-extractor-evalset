# Dataset Construction

## Goal

This split keeps the main evalset focused on the current Slot-Extractor training target:

- structured JSON output stability
- slot extraction accuracy
- context understanding
- tool-call decision accuracy
- hallucination control

## Split Rule

Start from the current `225`-case eval package, then separate out two special buckets:

1. `state_only confirmation probes`
   - cases where `history` looks like a meta confirmation-state message
   - useful for robustness probing
   - but not strongly grounded in a clearly modeled upstream message source

2. `async pending probes`
   - cases where `history` is still in a query-in-progress state such as `我来帮您查`
   - useful for orchestration stress tests
   - but not cleanly aligned with the current prompt's single-turn decision role

## Output Files

- main eval:
  - `slot_extractor_eval_v214_main.jsonl`
- split-out probes:
  - `probes_state_only_confirmation_8.jsonl`
  - `probes_async_pending_3.jsonl`

## Counts

- original combined set: `225`
- main eval: `214`
- state-only confirmation probes: `8`
- async pending probes: `3`

## Practical Use

- use the `214` main evalset for standard model comparison and training-loop evaluation
- use the two probe files for targeted stress testing or separate regression checks
