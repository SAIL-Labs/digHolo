"""Validate a digHolo build against the reference data under reference_data/.

For every parameter set recorded in reference_data/<case>/meta.json, re-run
the pipeline against the current shared library and check that fields,
coefficients and axes match the recorded values within tolerance.

The simulator output (frames) is checked for shape and dtype only — its
content is exercised end-to-end by the fields/coefs comparisons (the
pipeline takes those frames as input), so a separate stored copy would
duplicate coverage at ~100 MB of repo bloat. Cross-architecture float
reorderings inside the simulator also make a bit-exact comparison
impractical without per-platform reference sets.

Library lookup priority:
  1. ``--lib PATH``
  2. ``DIGHOLO_LIB`` environment variable
  3. Auto-discovery under ``build/<preset>/`` for the current OS

Exit code: 0 = all pass, 1 = one or more failures.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path

import numpy as np

from _dll import load_dll

SCRIPT_DIR = Path(__file__).resolve().parent
REF_DIR = SCRIPT_DIR / "reference_data"


def run_case(dll, p: dict):
    frame_ptr = dll.digHoloFrameSimulatorCreateSimple(
        ctypes.c_int(int(p["frameCount"])),    ctypes.c_int(int(p["frameWidth"])),
        ctypes.c_int(int(p["frameHeight"])),   ctypes.c_float(float(p["pixelSize"])),
        ctypes.c_int(int(p["polCount"])),      ctypes.c_float(float(p["lambda0"])),
        ctypes.c_int(int(p["seed"])),
    )
    if not frame_ptr:
        raise RuntimeError("digHoloFrameSimulatorCreateSimple returned null")

    frames = np.ctypeslib.as_array(
        frame_ptr, shape=(int(p["frameCount"]), int(p["frameHeight"]), int(p["frameWidth"]))
    ).copy()

    handle = dll.digHoloCreate()
    dll.digHoloConfigSetVerbosity(handle, 0)
    dll.digHoloConfigSetFramePixelSize(handle, float(p["pixelSize"]))
    dll.digHoloConfigSetFrameDimensions(handle, int(p["frameWidth"]), int(p["frameHeight"]))
    dll.digHoloConfigSetWavelengthCentre(handle, float(p["lambda0"]))
    dll.digHoloConfigSetPolCount(handle, int(p["polCount"]))
    dll.digHoloConfigSetfftWindowSizeX(handle, int(p["nx"]))
    dll.digHoloConfigSetfftWindowSizeY(handle, int(p["ny"]))
    dll.digHoloConfigSetIFFTResolutionMode(handle, int(p["resolutionMode"]))
    dll.digHoloConfigSetBasisGroupCount(handle, int(p["maxMG"]))
    for f in (
        dll.digHoloConfigSetAutoAlignBeamCentre,
        dll.digHoloConfigSetAutoAlignDefocus,
        dll.digHoloConfigSetAutoAlignTilt,
        dll.digHoloConfigSetAutoAlignBasisWaist,
        dll.digHoloConfigSetAutoAlignFourierWindowRadius,
    ):
        f(handle, 1)

    dll.digHoloSetBatch(handle, int(p["frameCount"]), frame_ptr)
    dll.digHoloAutoAlign(handle)

    b_out = ctypes.c_int(0); pol_out = ctypes.c_int(0)
    x_ptr = ctypes.POINTER(ctypes.c_float)()
    y_ptr = ctypes.POINTER(ctypes.c_float)()
    w_out = ctypes.c_int(0); h_out = ctypes.c_int(0)

    fptr = dll.digHoloGetFields(
        handle, ctypes.byref(b_out), ctypes.byref(pol_out),
        ctypes.byref(x_ptr), ctypes.byref(y_ptr),
        ctypes.byref(w_out), ctypes.byref(h_out),
    )
    if not fptr:
        raise RuntimeError("digHoloGetFields returned null")

    b, pol, w, h = int(b_out.value), int(pol_out.value), int(w_out.value), int(h_out.value)
    raw = np.ctypeslib.as_array(fptr, shape=(b, pol * w, h * 2)).copy()
    fields = raw[:, :, 0::2] + 1j * raw[:, :, 1::2]
    x_axis = np.ctypeslib.as_array(x_ptr, shape=(w,)).copy() if x_ptr else np.array([])
    y_axis = np.ctypeslib.as_array(y_ptr, shape=(h,)).copy() if y_ptr else np.array([])

    cb_out = ctypes.c_int(0); cm_out = ctypes.c_int(0); cp_out = ctypes.c_int(0)
    cptr = dll.digHoloBasisGetCoefs(
        handle, ctypes.byref(cb_out), ctypes.byref(cm_out), ctypes.byref(cp_out)
    )
    cb, cm, cp = int(cb_out.value), int(cm_out.value), int(cp_out.value)
    if cptr and cb > 0 and cm > 0 and cp > 0:
        raw_c = np.ctypeslib.as_array(cptr, shape=(cb, 2 * cm * cp)).copy()
        coefs = raw_c[:, 0::2] + 1j * raw_c[:, 1::2]
    else:
        coefs = np.zeros((0, 0), dtype=np.complex64)

    dll.digHoloDestroy(handle)
    return frames, fields, coefs, x_axis, y_axis


def compare(label: str, ref: np.ndarray, new: np.ndarray, tol: float) -> bool:
    if ref.shape != new.shape:
        print(f"    FAIL  {label}: shape mismatch  ref={ref.shape}  new={new.shape}")
        return False
    scale = float(np.max(np.abs(ref))) if np.max(np.abs(ref)) > 0 else 1.0
    err = float(np.max(np.abs(ref - new)) / scale)
    ok = err <= tol
    print(f"    {'PASS' if ok else 'FAIL'}  {label}: max_rel_err={err:.2e}  (tol={tol:.0e})")
    return ok


def check_frames_shape(frames: np.ndarray, p: dict) -> bool:
    expected_shape = (int(p["frameCount"]), int(p["frameHeight"]), int(p["frameWidth"]))
    if frames.dtype != np.float32:
        print(f"    FAIL  frames (simulator): dtype={frames.dtype} (want float32)")
        return False
    if frames.shape != expected_shape:
        print(f"    FAIL  frames (simulator): shape={frames.shape} (want {expected_shape})")
        return False
    print(f"    PASS  frames (simulator): shape={frames.shape} dtype={frames.dtype}")
    return True


def validate_case(dll, case_dir: Path, tol_fields: float, tol_coefs: float):
    meta_path = case_dir / "meta.json"
    if not meta_path.exists():
        print(f"  SKIP  {case_dir.name}: no meta.json")
        return None

    with open(meta_path) as f:
        meta = json.load(f)
    p = meta["params"]

    print(f"\nCase: {case_dir.name}")

    ref_fields = np.load(case_dir / "fields.npy")
    ref_coefs  = np.load(case_dir / "coefs.npy")
    ref_x      = np.load(case_dir / "x_axis.npy")
    ref_y      = np.load(case_dir / "y_axis.npy")

    frames, fields, coefs, x_axis, y_axis = run_case(dll, p)

    return all([
        check_frames_shape(frames, p),
        compare("fields",  ref_fields,  fields,  tol_fields),
        compare("coefs",   ref_coefs,   coefs,   tol_coefs),
        compare("x_axis",  ref_x,       x_axis,  1e-9),
        compare("y_axis",  ref_y,       y_axis,  1e-9),
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", type=Path, default=None,
                        help="Path to the digHolo shared library (.so/.dll/.dylib). "
                             "Default: $DIGHOLO_LIB or auto-discover under build/.")
    parser.add_argument("--tol-fields", type=float, default=1e-4)
    parser.add_argument("--tol-coefs",  type=float, default=1e-4)
    parser.add_argument("--case", type=str, default=None,
                        help="Run only this named case (default: all)")
    args = parser.parse_args()

    if not REF_DIR.exists():
        sys.exit(f"ERROR: reference_data not found at {REF_DIR}\n"
                 "Run generate_references.py first.")

    case_dirs = sorted(REF_DIR.iterdir()) if args.case is None else [REF_DIR / args.case]

    dll = load_dll(args.lib)
    outcomes: dict[str, bool] = {}
    for cd in case_dirs:
        if cd.is_dir():
            ok = validate_case(dll, cd, args.tol_fields, args.tol_coefs)
            if ok is not None:
                outcomes[cd.name] = ok

    print(f"\n{'='*60}")
    for name, ok in outcomes.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    passed = sum(outcomes.values())
    total  = len(outcomes)
    print(f"\n{passed}/{total} cases passed")
    sys.exit(0 if passed == total and total > 0 else 1)


if __name__ == "__main__":
    main()
