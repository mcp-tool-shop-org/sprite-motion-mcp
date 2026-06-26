#!/usr/bin/env node
/**
 * sprite-motion-mcp — drive the rigged-character pipeline headlessly.
 *
 * Proven loop (each step a measured-on-rig recipe in readouts/sprite-motion-knowledge):
 *   decimate → rig (UniRig WSL2) → propose-roles → apply-pose → rigidify → attach-weapon
 *            → export → render → cross-family vision JURY (the blocking critic) → batch_roster.
 *
 * Coordinate parity (load-bearing): poses are role-keyed WORLD-axis deltas (port across skeletons);
 * weapons are a char-root-relative rootTransform (Y-up) → C-convert. The Blender bridge owns the math.
 *
 * Uses the low-level Server + raw JSON-Schema tool defs (the high-level zod tool() inference OOMs tsc).
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { config } from "./config.js";
import { blender, python, wsl } from "./run.js";

const tmp = (name: string) => { mkdirSync(config.workDir, { recursive: true }); return join(config.workDir, name); };
const text = (s: string) => ({ content: [{ type: "text", text: s }] });
const lines = (out: string, re: RegExp, code: number, err: string) =>
  out.split("\n").filter((l) => re.test(l)).join("\n") || `[error ${code}] ${err.slice(-400)}`;

const REQUIRED_ROLES = [
  "hips", "spine", "chest", "neck", "head",
  "shoulder.R", "upperArm.R", "foreArm.R", "hand.R", "shoulder.L", "upperArm.L", "foreArm.L", "hand.L",
  "upperLeg.R", "lowerLeg.R", "foot.R", "upperLeg.L", "lowerLeg.L", "foot.L",
];

type Tool = { name: string; description: string; inputSchema: any; handler: (a: any) => Promise<any> };
const S = (props: any, required: string[] = []) => ({ type: "object", properties: props, required });
const str = (d: string) => ({ type: "string", description: d });
const num = (d: string) => ({ type: "number", description: d });

function writePlacement(roleMap: any, roleRotations: any, weapons: any[] = []) {
  const pj = tmp(`_placement_${Date.now() % 1e7}.json`);
  writeFileSync(pj, JSON.stringify({
    format: "sprite-motion.placement", version: 4, space: "gltf-y-up",
    roleMap, pose: { space: "world-axis-delta", roleRotations }, weapons,
  }, null, 2));
  return pj;
}
function parseVerdict(stdout: string) {
  try { return JSON.parse(stdout.trim().split("\n").pop() || "{}"); } catch { return {}; }
}

const TOOLS: Tool[] = [
  {
    name: "list_poses",
    description: "List the bundled combat key-poses (role-keyed, applicable to any tagged character via its roleMap).",
    inputSchema: S({}),
    handler: async () => {
      const poses = readdirSync(config.posesDir).filter((f) => f.endsWith(".json")).map((f) => {
        const d = JSON.parse(readFileSync(join(config.posesDir, f), "utf8"));
        return `${d.name}  (${Object.keys(d.roleRotations || {}).length} roles) — ${(d.note || "").split(".")[0]}`;
      });
      return text("Combat key-poses (sprite-motion.pose, world-axis-delta):\n- " + poses.join("\n- "));
    },
  },
  {
    name: "load_rig",
    description: "Import a rigged GLB and report its armature (bones + world head/tail) so a roleMap can be confirmed (UNCERTAINTY_GATED: the auto-proposal must be human-confirmed).",
    inputSchema: S({ glb: str("absolute path to a rigged .glb") }, ["glb"]),
    handler: async ({ glb }) => {
      const r = await blender("bones.py", ["--glb", glb, "--out", tmp("_load")], "load_rig");
      const bones = r.stdout.split("\n").filter((l) => /ARM=|^\s+bone_|\[mesh bbox\]/.test(l)).join("\n");
      return text((r.code === 0 ? "[loaded]\n" : `[error ${r.code}]\n${r.stderr.slice(-400)}\n`) + bones +
        "\n\nConfirm a roleMap (role → boneName) for the required roles: " + REQUIRED_ROLES.join(", "));
    },
  },
  {
    name: "decimate_mesh",
    description: "Decimate a dense TRELLIS mesh to a game-weight tri count WITH sliver cleanup (removes the ribbon/shard armor artifacts — measured fix).",
    inputSchema: S({ input: str("dense GLB"), out: str("output GLB"), targetTris: num("default 150000") }, ["input", "out"]),
    handler: async ({ input, out, targetTris }) => {
      const r = await blender("decimate.py", ["--in", input, "--out", out, "--target", String(targetTris ?? 150000)], "decimate");
      return text(lines(r.stdout, /\[(before|after|clean|export)\]|DECIMATE OK/, r.code, r.stderr));
    },
  },
  {
    name: "rig_mesh",
    description: "Auto-rig a clean mesh via UniRig in WSL2 (skeleton + learned skin + merge). Returns <input>_rigged.glb.",
    inputSchema: S({ wslMeshPath: str("/mnt/-style WSL path to the input mesh GLB") }, ["wslMeshPath"]),
    handler: async ({ wslMeshPath }) => {
      const script = config.rigScriptWslPath || "/mnt/e/AI-Models/_wsl_rig_mesh.sh";
      const r = await wsl(script, [wslMeshPath], "rig_mesh");
      return text((r.code === 0 ? "[rigged]\n" : `[wsl exit ${r.code}]\n`) +
        r.stdout.split("\n").filter((l) => /SKEL_OK|SKIN_OK|RIGGED_OK|_FAIL|DONE/.test(l)).join("\n"));
    },
  },
  {
    name: "rigidify_skin",
    description: "Rigidify limb + torso armor skin (push verts toward the dominant bone) so rigid plate creases instead of melting under posing. Measured: posed jury 0/3 → 2/3.",
    inputSchema: S({ glb: str("rigged GLB"), out: str("output GLB"), factor: num("0..1, default 0.75") }, ["glb", "out"]),
    handler: async ({ glb, out, factor }) => {
      const r = await blender("clean_skin.py", ["--glb", glb, "--apply", "--rigidify", String(factor ?? 0.75), "--out", out], "rigidify");
      return text(lines(r.stdout, /elbow-band|\[clean\]|\[export\]|CLEAN DONE/, r.code, r.stderr));
    },
  },
  {
    name: "apply_pose",
    description: "Apply a combat key-pose (named from the library, or inline world-axis roleRotations) to a rigged+role-mapped character. ROM-capped, DQS-baked.",
    inputSchema: S({
      char: str("rigged (ideally rigidified) GLB"), out: str("output GLB"),
      roleMap: { type: "object", description: "role → boneName for this character", additionalProperties: { type: "string" } },
      pose: str("a bundled pose name: guard/idle/anticipation/strike/recovery/hurt"),
      roleRotations: { type: "object", description: "inline {role: [{axis:[x,y,z],deg}]} if not using a bundled pose" },
    }, ["char", "out", "roleMap"]),
    handler: async ({ char, out, roleMap, pose, roleRotations }) => {
      let rr = roleRotations;
      if (pose && !rr) rr = JSON.parse(readFileSync(join(config.posesDir, `${pose}.json`), "utf8")).roleRotations;
      if (!rr) return text("[error] provide a `pose` name or inline `roleRotations`.");
      const pj = writePlacement(roleMap, rr);
      const r = await blender("apply_placement.py", ["--char", char, "--placement", pj, "--out", out], "apply_pose");
      return text(lines(r.stdout, /\[posed|\[export\]|BRIDGE DONE/, r.code, r.stderr));
    },
  },
  {
    name: "attach_weapon",
    description: "Attach a weapon GLB to a character via a v4 placement (rootTransform + grip/tip), riding the posed hand bone (WYSIWYG, no auto-orientation).",
    inputSchema: S({
      char: str("rigged GLB"), out: str("output GLB"),
      placement: str("a sprite-motion.placement v4 JSON path (carries roleMap?, pose?, weapons[])"),
      weapons: { type: "object", description: "asset → weapon GLB path, e.g. {halberd:'/path/halberd.glb'}", additionalProperties: { type: "string" } },
    }, ["char", "out", "placement", "weapons"]),
    handler: async ({ char, out, placement, weapons }) => {
      const wargs = Object.entries(weapons || {}).map(([k, v]) => `${k}=${v}`).join(",");
      const r = await blender("apply_placement.py", ["--char", char, "--placement", placement, "--weapons", wargs, "--out", out], "attach_weapon");
      return text(lines(r.stdout, /\[placed|\[posed|\[export\]|BRIDGE DONE/, r.code, r.stderr));
    },
  },
  {
    name: "render_turntable",
    description: "Render a lit N-view turntable of a GLB (grey ambient + 3-point) for inspection + the jury. view 0=front, 2=right, 4=back.",
    inputSchema: S({ glb: str("GLB"), outDir: str("output dir"), views: num("default 8"), size: num("default 768"), tag: str("filename tag") }, ["glb", "outDir"]),
    handler: async ({ glb, outDir, views, size, tag }) => {
      const t = tag || "view"; const v = views ?? 8;
      const r = await blender("turntable.py", ["--glb", glb, "--out", outDir, "--views", String(v), "--size", String(size ?? 768), "--tag", t], "render");
      return text(lines(r.stdout, /\[bbox\]|MONTAGE|TURNTABLE DONE/, r.code, r.stderr) + `\n(views in ${outDir}: ${t}_0..${v - 1}.png)`);
    },
  },
  {
    name: "jury_render",
    description: "EXTERNAL_VERIFIER: run the cross-family cloud-vision jury on a render (the blocking critic). Optional bug-free reference anchors it (kills false positives on dark/ornate assets). Returns PASS/FAIL.",
    inputSchema: S({
      image: str("test render PNG"), context: str("what the asset is"), checklist: str("defect categories to flag"),
      reference: str("a verified-clean render of the same character"), intended: str("intended features to never flag"),
    }, ["image", "context", "checklist"]),
    handler: async ({ image, context, checklist, reference, intended }) => {
      const args = ["--image", image, "--context", context, "--checklist", checklist,
        "--models", config.juryModels.join(","), "--canary", config.juryCanary, "--ollama", config.ollama];
      if (reference) args.push("--reference", reference);
      if (intended) args.push("--intended", intended);
      const r = await python("jury.py", args, "jury");
      const v = parseVerdict(r.stdout);
      const detail = (v.jurors || []).map((j: any) =>
        `  [${j.pass ? "pass" : j.pass === false ? "FAIL" : "n/a"}]${j.model === v.canary ? " (canary)" : ""} ${j.model}: ${(j.issues || []).join("; ") || j.error || ""}`).join("\n");
      return text(`[${v.verdict || "ERROR"}] ${v.passes ?? "?"}/${v.of ?? "?"} jury pass` +
        (v.verdict && v.verdict !== "PASS" ? "  ← ANDON: do not export/ship until resolved (canary-only FAIL = soft warning)" : "") +
        `\n${detail}` + (r.code !== 0 && !v.verdict ? `\n[error] ${r.stderr.slice(-300)}` : ""));
    },
  },
  {
    name: "batch_roster",
    description: "Planner: run the pipeline across a roster (idempotent per character). Each character: pose → render → JURY gate. Halts a character on a jury FAIL (ANDON); others continue.",
    inputSchema: S({
      roster: { type: "array", description: "[{name, char, roleMap, pose?, reference?, intended?}]", items: { type: "object" } },
      outDir: str("output dir"), checklist: str("defect checklist (has a default)"),
    }, ["roster", "outDir"]),
    handler: async ({ roster, outDir, checklist }) => {
      mkdirSync(outDir, { recursive: true });
      const chk = checklist || "torn/melted/collapsed geometry at a bent joint; a detached limb; holes in the armor; not a coherent armored humanoid";
      const out: string[] = [`[batch_roster] ${roster.length} character(s)`];
      for (const c of roster) {
        const pose = c.pose || "guard";
        const posed = join(outDir, `${c.name}_${pose}.glb`);
        const viewDir = join(outDir, `${c.name}_views`);
        const lib = JSON.parse(readFileSync(join(config.posesDir, `${pose}.json`), "utf8"));
        const pj = writePlacement(c.roleMap, lib.roleRotations);
        const rp = await blender("apply_placement.py", ["--char", c.char, "--placement", pj, "--out", posed], `pose:${c.name}`);
        if (rp.code !== 0) { out.push(`  [SKIP] ${c.name}: pose failed — ${rp.stderr.slice(-120)}`); continue; }
        await blender("turntable.py", ["--glb", posed, "--out", viewDir, "--views", "8", "--size", "768", "--tag", c.name], `render:${c.name}`);
        const args = ["--image", join(viewDir, `${c.name}_0.png`),
          "--context", `the ${c.name} game character in a ${pose} pose, front view, grey bg`,
          "--checklist", chk, "--models", config.juryModels.join(","), "--canary", config.juryCanary, "--ollama", config.ollama];
        if (c.reference) args.push("--reference", c.reference);
        if (c.intended) args.push("--intended", c.intended);
        const rj = await python("jury.py", args, `jury:${c.name}`);
        const v = parseVerdict(rj.stdout);
        out.push(`  [${v.verdict || "ERR"}] ${c.name}  (${v.passes ?? "?"}/${v.of ?? "?"})  -> ${posed}` +
          (v.verdict && v.verdict !== "PASS" ? "  ⛔ ANDON HALT (review before ship)" : ""));
      }
      out.push(`\nIdempotent: re-run to refresh. Compensator: delete <name>_*.glb to revert a character.`);
      return text(out.join("\n"));
    },
  },
];

if (process.argv.includes("--selftest")) {
  console.log("sprite-motion-mcp selftest OK — tools: " + TOOLS.map((t) => t.name).join(", "));
  process.exit(0);
}

const server = new Server({ name: "sprite-motion-mcp", version: "0.1.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map((t) => ({ name: t.name, description: t.description, inputSchema: t.inputSchema })),
}));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const t = TOOLS.find((x) => x.name === req.params.name);
  if (!t) return text(`[error] unknown tool ${req.params.name}`);
  try { return await t.handler(req.params.arguments || {}); }
  catch (e) { return text(`[error] ${t.name}: ${String(e).slice(0, 400)}`); }
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("sprite-motion-mcp running on stdio");
