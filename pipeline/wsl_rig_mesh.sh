#!/usr/bin/env bash
# Reusable UniRig pipeline (REAL flash_attn): <input.glb> -> <input>_rigged.glb
# skeleton -> learned skin -> merge. Roster-general (takes any mesh path on /mnt/e).
# Run (from PowerShell): wsl.exe -- bash /mnt/e/AI-Models/_wsl_rig_mesh.sh /mnt/e/AI/.../mesh.glb
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export HF_HOME=/mnt/e/AI-Models/hf-cache
source "$HOME/unirig-env/bin/activate"
cd "$HOME/UniRig"
IN="$1"; BASE="${IN%.glb}"
SKEL="${BASE}_skeleton.fbx"; SKIN="${BASE}_skin.fbx"; OUT="${BASE}_rigged.glb"

echo "=== 1/3 skeleton: $(basename "$IN") ==="
bash launch/inference/generate_skeleton.sh --input "$IN" --output "$SKEL"
[ -f "$SKEL" ] && echo "SKEL_OK $(ls -la "$SKEL" | awk '{print $5}')" || { echo SKEL_FAIL; exit 1; }

echo "=== 2/3 learned skin (real flash_attn sm_120) ==="
bash launch/inference/generate_skin.sh --input "$SKEL" --output "$SKIN"
[ -f "$SKIN" ] && echo "SKIN_OK $(ls -la "$SKIN" | awk '{print $5}')" || { echo SKIN_FAIL; exit 1; }

echo "=== 3/3 merge -> rigged GLB ==="
bash launch/inference/merge.sh --source "$SKIN" --target "$IN" --output "$OUT"
[ -f "$OUT" ] && echo "RIGGED_OK $OUT ($(ls -la "$OUT" | awk '{print $5}') bytes)" || echo RIGGED_FAIL
echo DONE
