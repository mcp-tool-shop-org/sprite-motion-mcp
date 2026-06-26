# sprite-motion-mcp — design

Productizes the **proven** sprite-motion rigged-character loop (each step a measured-on-rig recipe in
`readouts/sprite-motion-knowledge`) as MCP tools an agent can drive headlessly:

```
decimate → rig (UniRig WSL2) → propose-roles → apply-pose → rigidify → attach-weapon
         → export → render → cross-family vision JURY (blocking critic) → batch_roster
```

## Architecture (planner / executor / verifier)

Per the posing-system design (3D-GPT / L3GO F14; SceneCraft / Planner-Actor-Critic F15): split **planning**
(`batch_roster` sequences the roster) from **execution** (per-character Blender/UniRig tools), with a
**blocking verifier** (`jury_render`) before anything is treated as shippable.

- **Executors** are thin TypeScript wrappers (`src/run.ts`) that shell out to the **bundled** Blender-python
  pipeline (`pipeline/*.py`) and WSL2 UniRig (`pipeline/wsl_rig_mesh.sh`). The coordinate math (three.js
  Y-up ↔ Blender Z-up; world-axis pose deltas; v4 weapon `rootTransform`) lives in the bridge
  (`pipeline/apply_placement.py`), never restated in TS.
- **Poses** are a role-keyed library (`poses/*.json`, `sprite-motion.pose` world-axis deltas) — apply to
  any tagged character via its `roleMap`. ROM is capped ≤85° (clean-LBS zone) and the bake uses DQS.
- **The verifier** (`pipeline/jury.py`) is a cross-family cloud-vision jury, refute-by-default, 2-of-3
  consensus, reference-anchored (GlitchBench F16) so it stops false-positiving on dark/ornate characters.

## Standards compliance (the six workflow standards)

Scored 0–3 (0 missing · 1 prose-only · 2 enforced · 3 enforced + documented + receipts).

| Standard | Score | Evidence | Remediation |
|---|---|---|---|
| **PIN_PER_STEP** | **2** | `src/run.ts` pins every step to `_runs/run-manifest.jsonl` (resolved exe + script + exact argv + exit code + Blender path). Jury model roster is pinned in `config`. | P1: hash the pose + roleMap per `batch_roster` run into the manifest so a wave is byte-replayable; record the UniRig env + Blender versions. |
| **ANDON_AUTHORITY** | **2** | `jury_render` returns a blocking PASS/FAIL; `batch_roster` halts a character on jury FAIL (other characters continue). Canary-only FAIL is a soft warning, not a halt. | P2: add a `validate_geometry` tool (non-manifold / loose-vert / bbox sanity) that halts BEFORE export (F14), and a per-character retry budget. |
| **NAMED_COMPENSATORS** | **2** | Every tool writes **reversible** local artifacts (GLB / FBX / PNG). Compensator table below. This MCP performs **no irreversible external action** — it never publishes, pushes, or charges; distribution is a separate, Director-gated step. | P3: when a `publish_assets` tool is added, it MUST ship with a `delete_release` compensator + owner before use (no skip). |
| **DECOMPOSE_BY_SECRETS** | **2** | Stable modules (pipeline scripts, pose library, role profile) are separate from volatile inputs (per-character `roleMap`, per-rig `config` paths/jury roster). One concern per module. | P3: split the role profile into its own `profile.json` shipped artifact (currently inline in `index.ts`). |
| **UNCERTAINTY_GATED_HUMANS** | **2** | `load_rig` returns a roleMap **proposal** for human confirmation (no auto-rig is trusted blind). Jury `INCONCLUSIVE` and `batch_roster` ANDON halts surface to the human for review. | P3: frame the roleMap proposal contrastively ("you probably expected bone_N = hand.R; I mapped bone_M because…"). |
| **EXTERNAL_VERIFIER** | **3** | `jury_render` is a **different-family** panel (MiniMax + Moonshot + a Google canary), render-only — it never sees the generator's reasoning or the pose spec, only the image. Reference-anchored, refute-by-default, 2-of-3. This is the whole point of the gate. | — (keep the roster fresh; re-confirm cloud models per run). |

### Compensators table (NAMED_COMPENSATORS)

| Action | Irreversible? | Compensator | Post-rollback state | Owner |
|---|---|---|---|---|
| `apply_pose` / `attach_weapon` / `decimate_mesh` / `rigidify_skin` write a GLB | No | delete the output GLB | input untouched | tool caller |
| `render_turntable` writes PNGs | No | delete the view dir | — | tool caller |
| `batch_roster` writes `<name>_*.glb` + views | No | delete `<name>_*` for the character | other characters intact (idempotent) | tool caller |
| `rig_mesh` (UniRig WSL2) writes `<input>_rigged.glb` | No | delete the rigged GLB | input mesh untouched | tool caller |
| *(future)* `publish_assets` | **YES** | **must add `delete_release` + owner before shipping the tool — no skip** | — | Director |

## Coordinate parity (load-bearing — do not relearn)

WORLD-relative transforms PORT across three.js (Y-up) ↔ Blender (Z-up) by conjugation `C = Rx(+90°)`;
LOCAL bone deltas do NOT. So poses travel as per-role **world-axis** deltas and weapons as a char-root
**rootTransform** (Y-up) → C-convert. The bridge owns all of this; tools pass data, never math.
