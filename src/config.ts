// Environment-overridable configuration. The MCP shells out to Blender (Windows exe), the bundled
// Blender-python pipeline scripts, WSL2 UniRig, and a cloud-vision jury. Nothing here is a secret;
// these are host paths + the verifier roster. Override per-rig via env.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, ".."); // repo root (dist/ -> ..)

export const config = {
  /** Blender executable (5.x). The pipeline scripts run inside Blender's python. */
  blender: process.env.SPRITE_MOTION_BLENDER || "blender",
  /** A standalone python (with urllib) for the jury (talks to Ollama). Not Blender's python. */
  python: process.env.SPRITE_MOTION_PYTHON || "python",
  /** Bundled pipeline + pose library (shipped with the package). */
  pipelineDir: process.env.SPRITE_MOTION_PIPELINE || join(ROOT, "pipeline"),
  posesDir: process.env.SPRITE_MOTION_POSES || join(ROOT, "poses"),
  /** Where outputs land unless a tool is given an explicit out path. */
  workDir: process.env.SPRITE_MOTION_WORKDIR || join(ROOT, "_runs"),
  /** WSL UniRig: how to invoke the rig script. The script path is /mnt/ translated by the tool. */
  wslDistro: process.env.SPRITE_MOTION_WSL_DISTRO || "", // "" = default distro
   rigScriptWslPath: process.env.SPRITE_MOTION_RIG_WSL || "", // e.g. /mnt/e/AI-Models/_wsl_rig_mesh.sh; "" => bundled
  /** Cross-family vision jury (EXTERNAL_VERIFIER). Roster is volatile — re-confirm models at run time. */
  ollama: process.env.SPRITE_MOTION_OLLAMA || "http://127.0.0.1:11434",
  juryModels: (process.env.SPRITE_MOTION_JURY ||
    "minimax-m3:cloud,kimi-k2.6:cloud,gemini-3-flash-preview:cloud").split(","),
  juryCanary: process.env.SPRITE_MOTION_JURY_CANARY || "gemini-3-flash-preview:cloud",
};
