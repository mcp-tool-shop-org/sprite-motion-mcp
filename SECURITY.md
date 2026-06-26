# Security

## Threat model

`sprite-motion-mcp` is a **local orchestration server**. It spawns local processes (Blender, python, WSL)
and makes outbound calls to an Ollama endpoint for the vision jury. It does **not** run a network service,
store credentials, accept inbound connections, or publish/push anything.

### Trust boundaries

- **Inputs are file paths + JSON** (mesh/GLB paths, roleMaps, pose data) supplied by the calling agent.
  Tools pass these as **argv** to the bundled scripts via `spawn(..., { shell: false })` — there is **no
  shell interpolation**, so path contents cannot inject shell commands.
- **Bundled pipeline scripts** (`pipeline/*.py`, `*.sh`) are the only code executed in Blender / WSL; they
  are shipped with the package and version-controlled. The server does not execute caller-supplied code.
- **The jury** sends rendered PNGs (base64) to the configured Ollama endpoint. Renders of in-development
  game assets leave the machine when a cloud jury model is used — point `SPRITE_MOTION_OLLAMA` at a local
  model if that matters for a given project.

### What this server will not do

- No `npm publish`, `git push`, release creation, or any irreversible external action. Distribution of the
  (large) rigged GLBs is a separate, Director-gated step. If a `publish_assets` tool is ever added it must
  ship with a named rollback compensator first (see `docs/design.md`).
- No telemetry. No secrets are read or written; configuration is non-secret host paths + a model roster.

### Operator notes

- Treat input mesh/GLB paths as trusted local files; the server reads and rewrites them via Blender.
- WSL UniRig runs with your WSL user's privileges; the rig script path is configurable
  (`SPRITE_MOTION_RIG_WSL`) and should point only at the audited bundled/staged script.

## Reporting

Open a private security advisory on the repository, or contact the maintainer
(64996768+mcp-tool-shop@users.noreply.github.com).
