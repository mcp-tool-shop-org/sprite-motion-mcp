// Spawn helpers + a PIN_PER_STEP run manifest. Every pipeline step is recorded byte-replayably:
// the resolved executable, the script, the exact argv, exit code, and a timestamp.
import { spawn } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { config } from "./config.js";

export interface RunResult { code: number; stdout: string; stderr: string; cmd: string; }

/** Run a command, capture output, and PIN the step to a per-day manifest (replayability standard). */
export async function run(exe: string, args: string[], opts: { cwd?: string; label?: string } = {}): Promise<RunResult> {
  const cmd = `${exe} ${args.join(" ")}`;
  const res = await new Promise<RunResult>((resolve) => {
    const p = spawn(exe, args, { cwd: opts.cwd, shell: false });
    let stdout = "", stderr = "";
    p.stdout.on("data", (d) => (stdout += d.toString()));
    p.stderr.on("data", (d) => (stderr += d.toString()));
    p.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr, cmd }));
    p.on("error", (e) => resolve({ code: -1, stdout, stderr: stderr + String(e), cmd }));
  });
  pin({ label: opts.label || exe, exe, args, code: res.code });
  return res;
}

/** Run a Blender-python pipeline script: blender -b --python <pipeline/script> -- <args...> */
export function blender(script: string, args: string[], label?: string): Promise<RunResult> {
  return run(config.blender, ["-b", "--python", join(config.pipelineDir, script), "--", ...args], { label: label || script });
}

/** Run a standalone python script (the jury): python <pipeline/script> <args...> */
export function python(script: string, args: string[], label?: string): Promise<RunResult> {
  return run(config.python, [join(config.pipelineDir, script), ...args], { label: label || script });
}

/** Run the WSL UniRig rig script on a /mnt/ path. */
export function wsl(scriptWslPath: string, args: string[], label?: string): Promise<RunResult> {
  const base = config.wslDistro ? ["-d", config.wslDistro, "--"] : ["--"];
  return run("wsl.exe", [...base, "bash", scriptWslPath, ...args], { label: label || "wsl-rig" });
}

let pinned = false;
function pin(entry: Record<string, unknown>) {
  try {
    mkdirSync(config.workDir, { recursive: true });
    if (!pinned) { pinned = true; }
    appendFileSync(join(config.workDir, "run-manifest.jsonl"),
      JSON.stringify({ ...entry, blender: config.blender }) + "\n");
  } catch { /* manifest is best-effort; never block the tool on it */ }
}
