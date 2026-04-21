"""Generate reference output files for digHolo regression testing.

Runs the current shared library against a fixed set of parameter
configurations using the built-in frame simulator (deterministic seed),
and saves all outputs as numpy arrays plus a JSON metadata file per case.
Run this once against the canonical build; use validate_references.py to
check future builds.

Usage:
    python generate_references.py [--lib PATH]

Outputs written to: tests/reference_data/<case_name>/
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from _dll import load_dll

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "reference_data"


def mode_count(maxMG: int) -> int:
    """Total HG modes for ``maxMG`` mode groups: sum(1..maxMG)."""
    return maxMG * (maxMG + 1) // 2


# --------------------------------------------------------------------------
# Test cases. frameCount must equal mode_count(maxMG) for the simulator to
# generate one frame per mode (identity transfer matrix). seed is fixed for
# full determinism across runs.
# --------------------------------------------------------------------------
TEST_CASES = [
    {"name": "standard",     "frameCount": mode_count(9), "frameWidth": 320, "frameHeight": 256,
     "pixelSize": 20e-6, "lambda0": 1565e-9, "polCount": 2, "nx": 128, "ny": 128, "resolutionMode": 1, "maxMG": 9, "seed": 1},
    {"name": "small_window", "frameCount": mode_count(6), "frameWidth": 320, "frameHeight": 256,
     "pixelSize": 20e-6, "lambda0": 1565e-9, "polCount": 1, "nx":  64, "ny":  64, "resolutionMode": 1, "maxMG": 6, "seed": 1},
    {"name": "single_pol",   "frameCount": mode_count(9), "frameWidth": 320, "frameHeight": 256,
     "pixelSize": 20e-6, "lambda0": 1565e-9, "polCount": 1, "nx": 128, "ny": 128, "resolutionMode": 1, "maxMG": 9, "seed": 1},
    {"name": "full_res",     "frameCount": mode_count(9), "frameWidth": 320, "frameHeight": 256,
     "pixelSize": 20e-6, "lambda0": 1565e-9, "polCount": 2, "nx": 128, "ny": 128, "resolutionMode": 0, "maxMG": 9, "seed": 1},
    {"name": "large_window", "frameCount": mode_count(9), "frameWidth": 640, "frameHeight": 512,
     "pixelSize": 20e-6, "lambda0": 1565e-9, "polCount": 2, "nx": 256, "ny": 256, "resolutionMode": 1, "maxMG": 9, "seed": 1},
]


def run_case(dll, p: dict) -> dict:
    name = p["name"]
    print(f"\n{'='*60}\nRunning test case: {name}\n{'='*60}")

    frame_ptr = dll.digHoloFrameSimulatorCreateSimple(
        ctypes.c_int(p["frameCount"]),    ctypes.c_int(p["frameWidth"]),
        ctypes.c_int(p["frameHeight"]),   ctypes.c_float(p["pixelSize"]),
        ctypes.c_int(p["polCount"]),      ctypes.c_float(p["lambda0"]),
        ctypes.c_int(p["seed"]),
    )
    if not frame_ptr:
        raise RuntimeError("digHoloFrameSimulatorCreateSimple returned null")
    frames = np.ctypeslib.as_array(
        frame_ptr, shape=(p["frameCount"], p["frameHeight"], p["frameWidth"])
    ).copy()

    handle = dll.digHoloCreate()
    dll.digHoloConfigSetVerbosity(handle, 1)
    dll.digHoloConfigSetFramePixelSize(handle, p["pixelSize"])
    dll.digHoloConfigSetFrameDimensions(handle, p["frameWidth"], p["frameHeight"])
    dll.digHoloConfigSetWavelengthCentre(handle, p["lambda0"])
    dll.digHoloConfigSetPolCount(handle, p["polCount"])
    dll.digHoloConfigSetfftWindowSizeX(handle, p["nx"])
    dll.digHoloConfigSetfftWindowSizeY(handle, p["ny"])
    dll.digHoloConfigSetIFFTResolutionMode(handle, p["resolutionMode"])
    dll.digHoloConfigSetBasisGroupCount(handle, p["maxMG"])
    for f in (
        dll.digHoloConfigSetAutoAlignBeamCentre,
        dll.digHoloConfigSetAutoAlignDefocus,
        dll.digHoloConfigSetAutoAlignTilt,
        dll.digHoloConfigSetAutoAlignBasisWaist,
        dll.digHoloConfigSetAutoAlignFourierWindowRadius,
    ):
        f(handle, 1)

    dll.digHoloSetBatch(handle, p["frameCount"], frame_ptr)
    dll.digHoloAutoAlign(handle)

    b_out = ctypes.c_int(0); pol_out = ctypes.c_int(0)
    x_ptr = ctypes.POINTER(ctypes.c_float)()
    y_ptr = ctypes.POINTER(ctypes.c_float)()
    w_out = ctypes.c_int(0); h_out = ctypes.c_int(0)

    fields_raw_ptr = dll.digHoloGetFields(
        handle, ctypes.byref(b_out), ctypes.byref(pol_out),
        ctypes.byref(x_ptr), ctypes.byref(y_ptr),
        ctypes.byref(w_out), ctypes.byref(h_out),
    )
    if not fields_raw_ptr:
        raise RuntimeError("digHoloGetFields returned null")

    b, pol, w, h = int(b_out.value), int(pol_out.value), int(w_out.value), int(h_out.value)
    raw_f = np.ctypeslib.as_array(fields_raw_ptr, shape=(b, pol * w, h * 2)).copy()
    fields = raw_f[:, :, 0::2] + 1j * raw_f[:, :, 1::2]
    x_axis = np.ctypeslib.as_array(x_ptr, shape=(w,)).copy() if x_ptr else np.array([])
    y_axis = np.ctypeslib.as_array(y_ptr, shape=(h,)).copy() if y_ptr else np.array([])

    cb_out = ctypes.c_int(0); cm_out = ctypes.c_int(0); cp_out = ctypes.c_int(0)
    coefs_raw_ptr = dll.digHoloBasisGetCoefs(
        handle, ctypes.byref(cb_out), ctypes.byref(cm_out), ctypes.byref(cp_out)
    )
    cb, cm, cp = int(cb_out.value), int(cm_out.value), int(cp_out.value)
    if coefs_raw_ptr and cb > 0 and cm > 0 and cp > 0:
        raw_c = np.ctypeslib.as_array(coefs_raw_ptr, shape=(cb, 2 * cm * cp)).copy()
        coefs = raw_c[:, 0::2] + 1j * raw_c[:, 1::2]
    else:
        coefs = np.zeros((0, 0), dtype=np.complex64)

    dll.digHoloDestroy(handle)

    print(f"  frames : {frames.shape}")
    print(f"  fields : {fields.shape}  (b={b}, pol={pol}, w={w}, h={h})")
    print(f"  coefs  : {coefs.shape}  (b={cb}, modes={cm}, pol={cp})")
    print(f"  x_axis : {x_axis.shape}  y_axis : {y_axis.shape}")

    return {
        "frames": frames, "fields": fields, "coefs": coefs,
        "x_axis": x_axis, "y_axis": y_axis,
        "meta": {
            "params": {k: float(v) if isinstance(v, float) else v for k, v in p.items()},
            "output_shapes": {
                "frames": list(frames.shape), "fields": list(fields.shape),
                "coefs":  list(coefs.shape),
                "x_axis": list(x_axis.shape), "y_axis": list(y_axis.shape),
            },
            "fields_dims": {"batch": b, "pol": pol, "w": w, "h": h},
            "coefs_dims":  {"batch": cb, "modes": cm, "pol": cp},
        },
    }


def save_case(case_name: str, result: dict, lib_path: Path) -> None:
    case_dir = OUTPUT_DIR / case_name
    case_dir.mkdir(parents=True, exist_ok=True)

    np.save(case_dir / "frames.npy", result["frames"])
    np.save(case_dir / "fields.npy", result["fields"])
    np.save(case_dir / "coefs.npy",  result["coefs"])
    np.save(case_dir / "x_axis.npy", result["x_axis"])
    np.save(case_dir / "y_axis.npy", result["y_axis"])

    meta = result["meta"].copy()
    meta["generated_at"] = datetime.utcnow().isoformat() + "Z"
    meta["lib_path"]     = str(lib_path)

    with open(case_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  Saved to {case_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", type=Path, default=None,
                        help="Path to the digHolo shared library. "
                             "Default: $DIGHOLO_LIB or auto-discover under build/.")
    args = parser.parse_args()

    print("digHolo reference generator")
    dll = load_dll(args.lib)
    print(f"Out : {OUTPUT_DIR}\n")

    lib_path = args.lib if args.lib is not None else Path("(auto-discovered)")
    for p in TEST_CASES:
        try:
            result = run_case(dll, p)
            save_case(p["name"], result, lib_path)
        except Exception as exc:
            print(f"\nERROR in case '{p['name']}': {exc}")
            raise

    print(f"\nDone. {len(TEST_CASES)} reference case(s) written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
