r"""tools/collect_prop1.py

Small utility to read an Aspen Tree node (via COM) and return the value for
`\Data\Blocks\CARBFLO\Output\Prop Data\ANALPROP\PROP-1`.

- Does NOT modify `CodeLibrary.py`.
- Exposes `get_tree_node_value(node_path)` and `get_prop1_from_carbflo()`.
- CLI: `--prop1` prints the numeric value (default unit: kmol/hr).

Usage examples:
  python tools/collect_prop1.py --prop1
  from tools.collect_prop1 import get_prop1_from_carbflo
  v = get_prop1_from_carbflo(as_unit='mol/s')
"""
from pathlib import Path
from typing import Any, Optional

try:
    import win32com.client as win32
except Exception:  # pragma: no cover - runtime dependency
    win32 = None

NODE_PROP1 = r"\Data\Blocks\CARBFLO\Output\Prop Data\ANALPROP\PROP-1"


def _get_apwn_doc(fallback_bkp: Optional[Path] = None):
    """Attach to an existing Aspen APWN Document or raise informative error."""
    if win32 is None:
        raise RuntimeError("pywin32 is required to access Aspen COM (install with `pip install pywin32`)")

    # prefer active object
    try:
        doc = win32.GetActiveObject("Apwn.Document")
        # quick check
        _ = doc.Tree
        return doc
    except Exception:
        pass

    # fallback: try to dispatch (may create a COM object)
    try:
        doc = win32.gencache.EnsureDispatch("Apwn.Document")  # type: ignore[attr-defined]
        # if Tree isn't initialized and a fallback .bkp path was provided, attempt InitFromArchive2
        try:
            _ = doc.Tree
            return doc
        except Exception:
            if fallback_bkp is not None and Path(fallback_bkp).exists():
                doc.InitFromArchive2(str(Path(fallback_bkp).resolve()))
                return doc
            raise RuntimeError("Aspen COM object is available but no active document found; provide fallback_bkp to load archive")
    except Exception as e:
        raise RuntimeError(f"Unable to attach to Aspen COM Document: {e}") from e


def get_tree_node_value(node_path: str, fallback_bkp: Optional[Path] = None) -> Any:
    """Return the .Value of a Tree node located by `node_path`.

    Args:
      node_path: string path accepted by `Application.Tree.FindNode`, e.g.
                 "\\Data\\Blocks\\CARBFLO\\Output\\Prop Data\\ANALPROP\\PROP-1".
      fallback_bkp: optional Path to a .bkp to load if no active document is attached.

    Returns:
      The node.Value (type depends on the Aspen property).

    Raises:
      KeyError if node not found.
      RuntimeError for COM errors or missing Aspen session.
    """
    doc = _get_apwn_doc(fallback_bkp=fallback_bkp)
    try:
        tree = doc.Tree
    except Exception as e:
        raise RuntimeError(f"Aspen document tree not available: {e}") from e

    node = tree.FindNode(node_path)
    if node is None:
        raise KeyError(f"Tree node not found: {node_path}")
    return node.Value


def get_prop1_from_carbflo(as_unit: str = "kmol/hr", fallback_bkp: Optional[Path] = None) -> float:
    """Read PROP-1 from CARBFLO and return as a float.

    Args:
      as_unit: either 'kmol/hr' (default) or 'mol/s'.
      fallback_bkp: optional .bkp path if no active Aspen doc is present.
    """
    raw = get_tree_node_value(NODE_PROP1, fallback_bkp=fallback_bkp)
    try:
        val = float(raw)
    except Exception:
        raise RuntimeError(f"PROP-1 value is not numeric: {raw!r}")

    if as_unit == "kmol/hr":
        return val
    if as_unit == "mol/s":
        return val * 1000.0 / 3600.0
    raise ValueError("Unsupported unit. Use 'kmol/hr' or 'mol/s'.")


def get_stream_moleflow(stream_name: str, component: str | None = None, as_unit: str = "kmol/hr", fallback_bkp: Optional[Path] = None) -> float:
    """Return the mole flow for a stream.

    - If `component` is provided, return that component's mole flow in the stream.
    - Otherwise return the stream total (sum of per-component mole flows).

    Units returned: `kmol/hr` (default) or `mol/s` when `as_unit='mol/s'`.
    """
    # attach to Aspen
    doc = _get_apwn_doc(fallback_bkp=fallback_bkp)
    try:
        streams = doc.Tree.Elements("Data").Elements("Streams")
        s = streams.Elements(stream_name)
    except Exception:
        raise KeyError(f"Stream not found in Aspen Tree: {stream_name}")

    # try reading per-component mole flows first (preferred)
    try:
        comp_nodes = s.Elements("Output").Elements("MOLEFRAC").Elements("MIXED").Elements
        comp_names = [c.Name for c in comp_nodes]
        moleflows = []
        for cname in comp_names:
            try:
                v = s.Elements("Output").Elements("STR_MAIN").Elements("MOLEFLOW").Elements("MIXED").Elements(cname).Value
            except Exception:
                v = 0.0
            moleflows.append(float(v))

        if component:
            # find matching component (case-insensitive)
            idx = next((i for i, n in enumerate(comp_names) if str(n).upper() == component.upper()), None)
            if idx is None:
                raise KeyError(f"Component '{component}' not found in stream '{stream_name}'")
            value_kmol_hr = float(moleflows[idx])
        else:
            value_kmol_hr = float(sum(moleflows))
    except Exception:
        # fallback: try reading a scalar node (some flowsheets expose total MOLEFLOW.MIXED.Value)
        try:
            val_node = s.Elements("Output").Elements("STR_MAIN").Elements("MOLEFLOW").Elements("MIXED")
            value_kmol_hr = float(val_node.Value)
        except Exception as e:
            raise RuntimeError(f"Unable to read mole flows for stream '{stream_name}': {e}") from e

    if as_unit == "kmol/hr":
        return value_kmol_hr
    if as_unit == "mol/s":
        return value_kmol_hr * 1000.0 / 3600.0
    raise ValueError("Unsupported unit. Use 'kmol/hr' or 'mol/s'.")


def get_1_h2o_mu_flow(as_unit: str = "kmol/hr", fallback_bkp: Optional[Path] = None) -> float:
    """Convenience wrapper: read `1-H2O-MU` stream mole flow.

    - Prefer the `H2O` component mole flow if present; otherwise return stream total.
    """
    try:
        return get_stream_moleflow('1-H2O-MU', component='H2O', as_unit=as_unit, fallback_bkp=fallback_bkp)
    except KeyError:
        # component not present — return stream total instead
        return get_stream_moleflow('1-H2O-MU', component=None, as_unit=as_unit, fallback_bkp=fallback_bkp)


# ---------------------- MIX-REF helpers ---------------------------------
def get_mixref_liq_ratio(fallback_bkp: Optional[Path] = None) -> float:
    """Read `MIX-REF` block `Output.LIQ_RATIO` and return numeric value.

    Path used: "\\Data\\Blocks\\MIX-REF\\Output\\LIQ_RATIO"
    Raises KeyError if node not present, RuntimeError for COM issues.
    """
    node = r"\Data\Blocks\MIX-REF\Output\LIQ_RATIO"
    raw = get_tree_node_value(node, fallback_bkp=fallback_bkp)
    try:
        return float(raw)
    except Exception:
        raise RuntimeError(f"MIX-REF LIQ_RATIO is not numeric: {raw!r}")


def set_mixref_liqfrac(value: float, fallback_bkp: Optional[Path] = None) -> float:
    """Write `MIX-REF.Input.LIQFRAC` to the provided numeric `value` and return read-back.

    Path used: "\\Data\\Blocks\\MIX-REF\\Input\\LIQFRAC"
    Returns the value read back from Aspen after write.
    """
    node_path = r"\Data\Blocks\MIX-REF\Input\LIQFRAC"
    # attach to Aspen and find node
    doc = _get_apwn_doc(fallback_bkp=fallback_bkp)
    try:
        tree = doc.Tree
    except Exception as e:
        raise RuntimeError(f"Aspen document tree not available: {e}") from e

    n = tree.FindNode(node_path)
    if n is None:
        raise KeyError(f"Tree node not found: {node_path}")

    try:
        n.Value = float(value)
    except Exception as e:
        raise RuntimeError(f"Failed to write LIQFRAC at {node_path}: {e}") from e

    # read back and return
    try:
        return float(n.Value)
    except Exception:
        raise RuntimeError(f"Write succeeded but read-back failed for {node_path}")


# ---- CLI / convenience --------------------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Read PROP-1 or specific stream flows via Aspen Tree/COM")
    p.add_argument("--prop1", action="store_true", help="Print PROP-1 (kmol/hr)")
    p.add_argument("--molpersec", action="store_true", help="Print PROP-1 in mol/s instead of kmol/hr")
    p.add_argument("--h2o-flow", action="store_true", help="Print 1-H2O-MU flow (kmol/hr)")
    p.add_argument("--h2o-molpersec", action="store_true", help="Print 1-H2O-MU flow in mol/s instead of kmol/hr")
    p.add_argument("--bkp", type=str, default=None, help="Optional .bkp path to load if Aspen isn't attached")
    args = p.parse_args()

    if args.prop1:
        val = get_prop1_from_carbflo(as_unit=("mol/s" if args.molpersec else "kmol/hr"), fallback_bkp=Path(args.bkp) if args.bkp else None)
        unit = "mol/s" if args.molpersec else "kmol/hr"
        print(f"PROP-1 = {val} {unit}")
    elif args.h2o_flow:
        val = get_1_h2o_mu_flow(as_unit=("mol/s" if args.h2o_molpersec else "kmol/hr"), fallback_bkp=Path(args.bkp) if args.bkp else None)
        unit = "mol/s" if args.h2o_molpersec else "kmol/hr"
        print(f"1-H2O-MU flow = {val} {unit}")
    else:
        p.print_help()
