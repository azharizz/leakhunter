# Unspool

## Product

Unspool analyzes configured repositories for potential data exposure and lets
users inspect evidence, graph relationships, and durable knowledge annotations.
Static candidates are not proof; runtime results cover executed cases only.

## Users and task

The repository describes a developer-facing local analysis tool. The current
redesign prioritizes exploring the knowledge graph and creating, reading,
updating, and deleting nodes and edges.

## Platform

Web app. The confirmed design brief calls for connected flows and an exploratory
concept. Desktop is the primary workspace; narrow browser windows must remain
usable.

## Stack

Python HTTP API with plain HTML, CSS, JavaScript, and SVG. Preserve this stack and
the existing API contracts; no frontend framework is required.

## Constraints

- Live annotations survive analysis. Node IDs stay stable on update.
- Deleting a node removes connected edges and requires confirmation.
- Saved snapshots are immutable; mutation controls must be disabled while viewing one.
- Configuration, evidence, evaluation, policy approval, and repair tools remain
  accessible through secondary disclosures.
- Preserve keyboard access, visible focus, readable labels, error feedback, and
  reduced-motion support.
- The server is intended for local use, not public multi-user hosting.
