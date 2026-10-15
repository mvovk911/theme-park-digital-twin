# Project brief and original prompts

Owner's requests from 15 October 2026. This file preserves the intended project
scope so progress can be reviewed against it. The polished brief below summarizes
the original prompts; the original wording follows verbatim. Deployment credentials,
private infrastructure context and unrelated chat context are excluded.

## Working brief

Build a theme-park digital-twin proof of concept inspired by NVIDIA's Factory
Operations (FOX) blueprint. Explore connected systems and use cases, propose the
aggregation and operational coordination layer, and explain how OpenUSD, Omniverse,
OVStage and OVRTX make the experience spatial and interactive.

Deliver:

1. A short illustrated PDF slide deck: vision, API ecosystem, architecture, use
   cases, starting plan and measurable added value.
2. A simple but recognizable 3D park: perimeter railing, trees, water, one or two
   real ride types and facilities supporting the proposed operational use cases.
3. Python services and synthetic domain systems, backed by a small database; a
   clicked scene object must resolve to its asset record and current telemetry.
4. An interactive application rendered by actual OVRTX, with OVStage scene state,
   running on a provisioned Horde GPU.
5. A public repository on the owner's GitHub containing the PDF, editable source,
   application, assets, project prompt and progress renders.
6. Visible progress and honest distinctions between implemented behavior, synthetic
   simulation and proposed real-world integrations.

Use subagents for independent work on the backend, scene and frontend. Keep the
owner informed when there are obstacles. Do not present a browser-only 3D mockup
as the requested OVRTX application.

Acceptance evidence: real GPU screenshots, working camera controls and native
pick-to-record behavior, synthetic scenario/workflow changes, reproducible scene
and service startup, and a reviewable progress page in the public repository.

## Original requests

### Research and architecture — 20:43 CEST

> im interested in digital twins. digital shadows of real factory, or smart city.
> think about all possible API to system project like this could connect. What would be the aggreagtion layer, vizalization with omniverse openused, rendering...
> read and study this:
> https://blogs.nvidia.com/blog/factory-operations-fox-blueprint-ai-brain/
>
> Now go for doing this for amusment park.
> theam park.
> think about numerous usecases this could be used for. list a few. having it as databackbone, erp layer, mes layer like utiliy.
>
> how would idea, most optimzed, digital twin of amuzment park look like. think about the external system connections ith wouol have and how this would be visualized and used.
>
> do explor, study ideas, generate a few directions and keep me in the loop if you stuggle

### Illustrated PDF — 20:49 CEST

> generate a few page pdf document illustraion this, how to start, what to do , added value, etc...
> graphical connection between multiple api systems and other visualiyation of the project. think of it as project slidedeck

### GPU proof of concept — 20:56 CEST

> when finished things start to be more interesting.
> provison a GPU Horde instance you have skills to do.
> install Blender or other modeling tools and design a simple theam park. in 3d. outside railing, trees, water, and a real ride or two. something that covers all the use cases you introduced in the last document.
> generate simple python apps that would simulate senzor data, or call to a simple data base to idetify object by clicking to it. genearte a few synthetic data sytstems that would emulate the functionality.
>
> now take OV libs. especialy stage and OVRTX and render these models, data, info from Apis, etc...
>
> BUild a POC of project you described.
> An interactive, OVRTX rendered, application, taht would enable end users to experiance the project you envisioned.

### Public repository — 21:06 CEST

> can you make a public repo of this project on my github you use from omnistation

### Include deck and continue with subagents — 21:10 CEST

> can you upload the PDF, the slide deck, to the repo as well
>
> and then continue the work with subagents, building on the promt I started with

### Reviewable progress — 21:32 CEST

> put the prompt for this project, assets, and few renderes of progres on the repo as well. so im able to controll the progress

## Scope interpretation

The prototype demonstrates the operating workflows in the concept deck. It does
not claim to implement every eventual park system, a calibrated optimizer,
commercial ERP/MES replacements, or physical ride control. The
[progress page](progress.md) maps current deliverables and remaining work; the
[integration roadmap](integration-roadmap.md) describes a real-world pilot.
