# Architecture Documentation

This folder is the diagram-first companion to [`PLAN.md`](../PLAN.md) (the
original design write-up) and [`CLAUDE.md`](../CLAUDE.md) (the
implementation-detail/gotcha reference). Where those two are narrative,
these documents are structural: component/class/data diagrams and sequence
diagrams for the flows that matter most for understanding or changing this
integration safely.

Keep these in sync with the code the same way `PLAN.md`/`README.md` are
expected to be — if a flow described here changes shape, update the
relevant diagram in the same PR.

## Contents

1. [System Overview](01-system-overview.md) — component diagram, module
   responsibilities, runtime placement inside Home Assistant.
2. [Data Model](02-data-model.md) — persisted storage shape, in-memory
   types, and the subnet-hierarchy inference rules.
3. [Sequence Diagrams](03-sequence-diagrams.md) — setup/teardown, subnet
   CRUD + reparenting, the device-list merge pipeline, and manual IP→device
   assignment.
4. [Discovery Subsystem](04-discovery-subsystem.md) — active (ping-sweep)
   and passive (mDNS) discovery, their scheduling, and how results feed
   back into device matching.
5. [Frontend Panel](05-frontend-architecture.md) — the vanilla-JS custom
   element, its two views, and how it talks to the backend.

## How to read the diagrams

All diagrams are [Mermaid](https://mermaid.js.org/); they render natively
on GitHub and in most Markdown viewers. Class/type names match the actual
Python dataclasses, dict keys, and websocket command constants in
`custom_components/ip_management/` — grep for a name from a diagram to jump
straight to its implementation.
