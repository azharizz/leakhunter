# Graph workspace

Designed with OpenDesign using Local Codex, then adapted to the existing live API.
The graph and its record inspector form the primary workspace. The confirmed
brief calls for a web app, connected flows, and an exploratory concept.

## Visual decisions

- An off-white canvas, white controls, dark ink, and restrained green selection.
- System UI typography for controls; monospace only for code labels and graph data.
- A compact header and toolbar; filters, workspace settings, snapshots, and
  analysis evidence use progressive disclosure.
- A right inspector on desktop, stacked below the graph on narrow screens.
- Curved connections, a subtle selected-node stroke animation, and a short
  inspector transition. Reduced-motion preferences disable animation.
- Visible graph counts and a default 30-node limit keep large analyses legible;
  the full graph remains searchable and available in the record selectors.
  Sources, transforms, sinks, functions, and calls take precedence over syntax details.

## Verification

Run `node tests/test_dashboard.cjs` for the inspector, graph selection, snapshot
locks, filter reset, zoom bounds, and compact canvas regression checks.

Verified on 2026-10-20:

- 67 Python regression tests passed; dashboard regression checks and JS syntax passed.
- Browser checks covered node creation/update, edge creation/update/delete, graph
  selection, and snapshot editing locks using a separate temporary state directory.
- Desktop, 390px, and 320px layouts were inspected. The 320px page has no document
  overflow; the graph itself intentionally scrolls.
- The final design detector returned no findings. Earlier small-text and contrast
  findings were fixed; no rules were suppressed.
- Model calls, runtime execution, and repair runs were outside this UI verification.

The standalone generated concept is available in [Local Codex](http://127.0.0.1:49573/projects/leakhunter-graph-workspace-b38d/conversations/3d6ff489-06f2-4bb9-ad1a-01aff7b4740d/files/index.html).
The integrated app is available at [the local preview](http://127.0.0.1:8787/)
while the preview server is running. Preview data is separate from the user's saved workspace.
