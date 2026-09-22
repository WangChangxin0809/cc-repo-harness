# Visual guide

The first two diagrams are the README overview. The remaining diagrams explain one mechanism at a time. All labels are in English, and each SVG adapts to the viewer's light or dark theme.

## Your model. Your project. One development workflow.

Connect provider choice, project knowledge, guards, checks, assessment, and learning.

<img src="../../.github/assets/diagrams/01-overview.architecture.svg" alt="Connect provider choice, project knowledge, guards, checks, assessment, and learning." width="960">

## One task, supported from context to delivery

Put context and checks at the moments when they support development.

<img src="../../.github/assets/diagrams/02-agent-turn.workflow.svg" alt="Put context and checks at the moments when they support development." width="960">

## /assess: evidence to next steps

Separate scripted measurements from agent judgments and close the loop with remeasurement.

<img src="../../.github/assets/diagrams/03-assess.workflow.svg" alt="Separate scripted measurements from agent judgments and close the loop with remeasurement." width="960">

## WikiSkill: experience to validated skills

Trace evidence, propose skills, validate strict improvement, and retain experience through rollback.

**Status:** implementation preview.

<img src="../../.github/assets/diagrams/04-wikiskill.workflow.svg" alt="Trace evidence, propose skills, validate strict improvement, and retain experience through rollback." width="960">

## AgentRoom: shared work

Coordinate participants and version-aware edits; validate the combined result.

**Status:** implementation preview.

<img src="../../.github/assets/diagrams/05-agentroom.architecture.svg" alt="Coordinate participants and version-aware edits; validate the combined result." width="960">

## Choose a model. Keep Claude Code.

Separate provider configuration from the optional runtime translation route.

<img src="../../.github/assets/diagrams/06-model-setup.architecture.svg" alt="Separate provider configuration from the optional runtime translation route." width="960">

## Shared project memory

Save private discoveries, inspect proposed changes, share records through Git, and recall cited context. `dream prepare/finish` supports bounded agent-assisted synthesis; publication follows the same proposal and review path.

<img src="../../.github/assets/diagrams/07-shared-memory.architecture.svg" alt="Private candidates feed a reviewable proposal, apply writes Git record changes, and verify and recall provide task context; dream is an optional private synthesis branch." width="960">

[Shared-memory guide](../how-to/shared-memory.md) · [Editable JSON](../../.github/assets/diagrams/07-shared-memory.architecture.json)

### Reproduce the shared-memory diagram

Diagram 07 is generated with [Archify v2.16.0](https://github.com/tt-a1i/archify/releases/tag/v2.16.0), then exported by its official browser SVG exporter. The JSON specification is the editable source; the SVG is a generated artifact. Node.js 18+ and local Chrome/Chromium are required only for diagram maintenance.

Download the [official release ZIP](https://github.com/tt-a1i/archify/releases/download/v2.16.0/archify.zip) into `tmp/shared-memory-implementation/archify-v2.16.0/`. Verify its SHA-256 is `4c59fa6557a2385beaaef8c7219cc414573acc9f0c30a932d5053b0b20689a46`, then extract it there; the resulting tool directory ends in `archify/`. No global installation or `npm install` is needed.

From the repository root:

```bash
node scripts/render_memory_diagram.mjs
# Or use a separately extracted copy:
node scripts/render_memory_diagram.mjs --archify /path/to/archify
```

The script runs Archify's showcase validation, atomic HTML delivery, and official `visual-check` implementation; it blocks HTTP(S) before opening the local HTML and calls `Archify.exportMenu.run('svg')` to save the exact export. It does not send repository content to a service. The v2.16.0 viewer's optional web font is blocked, so rendering uses system monospace fonts; font appearance can vary across machines.

The generated SVG replaces `.github/assets/diagrams/07-shared-memory.architecture.svg`. The interactive HTML, SHA-256 receipts, four viewport measurements, light/dark screenshots, and exported-image screenshots stay under ignored `tmp/shared-memory-implementation/`. Set `ARCHIFY_CHROME` if Chrome/Chromium is not auto-detected. Open the HTML locally to explore or use other native exports. Inspect both themes after generation: successful automated checks establish geometry and containment, while visual review remains a separate step.

The diagram follows the [memory operations design](../exec-plans/shared-project-memory/operations-and-experience.zh-CN.md) and the implemented Git-only runtime. Its overview does not claim measured improvements in agent outcomes. Archify and its original template are MIT-licensed; the retained copyright and permission text is in [diagram notices](../../.github/assets/diagrams/07-shared-memory.NOTICES.md).
