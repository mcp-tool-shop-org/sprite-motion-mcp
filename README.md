# sprite-motion-mcp

**Drive the studio's rigged-character pipeline from an agent — decimate, auto-rig, pose, attach weapons, render, and verify, without touching a browser or a shell.**

`sprite-motion-mcp` exposes the proven [sprite-motion](https://github.com/mcp-tool-shop-org/sprite-motion) loop as Model Context Protocol tools. An agent (or you, from any MCP client) can take a generated character mesh all the way to a posed, weapon-attached, jury-verified game asset — and batch it across a whole roster — by calling tools, not by hand-running Blender.

Every step is a measured-on-rig recipe from `sprite-motion-knowledge` (the studio's motion KB). The hard part — coordinate parity (three.js Y-up ↔ Blender Z-up), rigid-armor deformation, and a vision verifier that doesn't hallucinate — is already solved and baked into the bundled pipeline.

## The loop

```
decimate → rig (UniRig, WSL2) → propose-roles → apply-pose → rigidify → attach-weapon
         → export → render → cross-family vision JURY (blocking) → batch_roster
```

## Tools

| Tool | What it does |
|------|--------------|
| `list_poses` | List the bundled combat key-poses (idle-ready / guard / anticipation / strike / recovery / hurt). |
| `load_rig` | Import a rigged GLB; report its skeleton so you can confirm a `roleMap`. |
| `decimate_mesh` | Decimate a dense TRELLIS mesh to a game-weight tri count **with sliver cleanup** (kills the ribbon/shard armor artifacts). |
| `rig_mesh` | Auto-rig a clean mesh via **UniRig in WSL2** (skeleton + learned skin + merge). |
| `rigidify_skin` | Rigidify limb + torso armor so rigid plate **creases instead of melts** when posed. |
| `apply_pose` | Apply a named key-pose (or inline world-axis deltas) — ROM-capped, DQS-baked. |
| `attach_weapon` | Attach a weapon GLB onto the (posed) hand via a v4 `rootTransform` placement. |
| `render_turntable` | Lit 8-direction render for inspection + the jury. |
| `jury_render` | **The blocking critic** — a cross-family cloud-vision jury, reference-anchored, returns PASS/FAIL. |
| `batch_roster` | Run the whole chain across a roster; ANDON-halts a character on a jury FAIL, idempotent per character. |

## Requirements

- **Blender 5.x** on `PATH` (or set `SPRITE_MOTION_BLENDER`). The pipeline runs inside Blender's python.
- A standalone **python** for the jury (set `SPRITE_MOTION_PYTHON`).
- **WSL2 + a UniRig env** for `rig_mesh` (the verified install recipe lives in the studio's mesh-line notes).
- **Ollama** reachable with cloud auth for the jury (`SPRITE_MOTION_OLLAMA`, default `http://127.0.0.1:11434`).

The jury roster is volatile — re-confirm the cloud vision models per run (`SPRITE_MOTION_JURY`).

## Install / run

```bash
npm install && npm run build
# register dist/index.js as an MCP server in your client (stdio transport)
node dist/index.js --selftest   # lists the tools, exits 0
```

Configure paths via env (see `src/config.ts`): `SPRITE_MOTION_BLENDER`, `SPRITE_MOTION_PYTHON`, `SPRITE_MOTION_OLLAMA`, `SPRITE_MOTION_JURY`, `SPRITE_MOTION_RIG_WSL`.

## Design + standards

Architecture (planner / executor / blocking verifier) and the six-standards compliance scorecard are in [docs/design.md](docs/design.md). The verifier (`jury_render`) is a different-model-family panel that sees only the render — never the generator's reasoning.

## License

[MIT](LICENSE).
