"""POSE SOLVER (numpy, no Blender) — replicate the upgraded apply_role_pose FK exactly
(per-bone sequence of WORLD-axis deltas, each pivoting about the bone's CURRENT posed head,
parent-first, children rigidly follow), then grid-search arm angles to land the hands at a
target so we author a believable GUARD stance numerically before spending render cycles.

Frame: Blender Z-up world (== this rig's armature space, arm.matrix_world=I, probe-confirmed).
+X=char-right  +Z=up  -Y=forward (char faces -Y).
"""
import json, numpy as np, itertools

SK = json.load(open(r"E:/AI/sprite-motion/public/samples/blackguard.skeleton.json", encoding="utf-8"))
B = {b["name"]: b for b in SK["bones"]}
HEAD = {n: np.array(b["head"], float) for n, b in B.items()}
TAIL = {n: np.array(b["tail"], float) for n, b in B.items()}
PARENT = {n: b["parent"] for n, b in B.items()}

def rot(axis, deg):
    a = np.array(axis, float); a = a / np.linalg.norm(a); t = np.radians(deg)
    x, y, z = a; c, s = np.cos(t), np.sin(t); C = 1 - c
    return np.array([[c+x*x*C, x*y*C-z*s, x*z*C+y*s],
                     [y*x*C+z*s, c+y*y*C, y*z*C-x*s],
                     [z*x*C-y*s, z*y*C+x*s, c+z*z*C]])

def aff(R=np.eye(3), t=np.zeros(3)):
    M = np.eye(4); M[:3,:3] = R; M[:3,3] = t; return M

def pivot(R, p):  # rotate by R about world point p
    return aff(R, p - R @ p)

# parent-first order over the full skeleton
order = []
seen = set()
def visit(n):
    if n in seen: return
    if PARENT[n] is not None: visit(PARENT[n])
    seen.add(n); order.append(n)
for n in B: visit(n)

def solve(pose):
    """pose: {bone: [(axis,deg),...]}. Returns posed head/tail dict (world)."""
    A = {}  # accumulated rest->posed affine per bone
    H = {}; T = {}
    for n in order:
        p = PARENT[n]
        A[n] = A[p].copy() if p is not None else np.eye(4)
        h = (A[n] @ np.append(HEAD[n], 1.0))[:3]
        for axis, deg in pose.get(n, []):
            D = pivot(rot(axis, deg), h)
            A[n] = D @ A[n]
            # h fixed (rotation about h)
        H[n] = (A[n] @ np.append(HEAD[n], 1.0))[:3]
        T[n] = (A[n] @ np.append(TAIL[n], 1.0))[:3]
    return H, T

# role -> bone
RM = {"upperArm.R":"bone_7","foreArm.R":"bone_8","hand.R":"bone_9",
      "upperArm.L":"bone_20","foreArm.L":"bone_21","hand.L":"bone_22",
      "shoulder.R":"bone_6","shoulder.L":"bone_19","spine":"bone_1","chest":"bone_3"}

def handpos(pose, side):
    H, T = solve(pose)
    return T[RM[f"hand.{side}"]], H[RM[f"foreArm.{side}"]]  # hand tip, elbow

# ---- search one arm: upperArm [X then Y], foreArm [X then Y] ----
def search(side, target, spine_deg=-6):
    base = {"bone_1":[([1,0,0], spine_deg)]}  # slight forward spine lean shared
    ua = RM[f"upperArm.{side}"]; fa = RM[f"foreArm.{side}"]
    best = None
    XS_ua = range(-50, 21, 5)       # upper-arm pitch about world X
    YS_ua = range(-40, 41, 10)      # upper-arm about world Y (ab/adduct)
    XS_fa = range(-70, 1, 5)        # elbow flex about world X (capped -70: rigid plate can't take a 100deg bend cleanly)
    YS_fa = range(-40, 41, 20)      # forearm about world Y (steer in/out)
    for ax_ua in XS_ua:
        for ay_ua in YS_ua:
            for ax_fa in XS_fa:
                for ay_fa in YS_fa:
                    pose = dict(base)
                    pose[ua] = [([1,0,0], ax_ua), ([0,1,0], ay_ua)]
                    pose[fa] = [([1,0,0], ax_fa), ([0,1,0], ay_fa)]
                    hand, elbow = handpos(pose, side)
                    d = np.linalg.norm(hand - target)
                    # prefer elbow lower than hand (hand raised) and elbow not flared past |x|>0.28
                    pen = max(0, elbow[2]-hand[2])*0.5 + max(0, abs(elbow[0])-0.26)*1.0
                    score = d + pen
                    if best is None or score < best[0]:
                        best = (score, d, ax_ua, ay_ua, ax_fa, ay_fa, hand.copy(), elbow.copy())
    return best

print("rest hand.R tail:", np.round(TAIL["bone_9"],3), " hand.L tail:", np.round(TAIL["bone_22"],3))
# guard target: hands up at UPPER chest, tighter + closer (forearms more vertical = tight guard silhouette)
TR = np.array([0.09, -0.13, 0.26]); TL = np.array([-0.09, -0.13, 0.26])
for side, tgt in [("R", TR), ("L", TL)]:
    s, d, axu, ayu, axf, ayf, hand, elbow = search(side, tgt)
    print(f"\n[{side}] target={np.round(tgt,3)}  best dist={d:.3f}")
    print(f"  upperArm.{side}: X{axu:+d} then Y{ayu:+d}   foreArm.{side}: X{axf:+d} then Y{ayf:+d}")
    print(f"  -> hand={np.round(hand,3)} elbow={np.round(elbow,3)}")
print("\nSOLVE DONE")
