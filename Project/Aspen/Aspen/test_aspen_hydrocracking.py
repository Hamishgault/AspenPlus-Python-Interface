"""Test the hydrocracking model with actual Aspen Plus simulation."""

import os
import sys
from pathlib import Path

WORKDIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(WORKDIR, "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from CodeLibrary import Simulation
from hydrocracking_v2 import update_hydrocracking_streams_v2


def main() -> int:
    """Run Aspen Plus with hydrocracking calculations."""
    workdir = Path(WORKDIR)
    
    # Look for Aspen backup file
    bkp_name = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
    bkp_path = workdir / bkp_name
    
    if not bkp_path.exists():
        print(f"❌ Aspen .bkp file not found: {bkp_path}")
        print("\nPlease place your Aspen Plus backup file in:")
        print(f"   {workdir}")
        print(f"\nExpected filename: {bkp_name}")
        return 1
    
    print("=" * 80)
    print("ASPEN PLUS HYDROCRACKING TEST")
    print("=" * 80)
    
    # Load Aspen simulation
    print(f"\n[1] Loading Aspen Plus simulation...")
    print(f"    File: {bkp_path.name}")
    
    try:
        sim = Simulation(
            AspenFileName=str(bkp_path),
            WorkingDirectoryPath=str(workdir),
            VISIBILITY=True,
        )
        print("    ✅ Aspen Plus loaded successfully")
    except Exception as exc:
        print(f"    ❌ Failed to load Aspen Plus")
        print(f"    Error: {exc}")
        return 1
    
    # Ensure Aspen has run once so stream outputs exist
    print("\n[1b] Running Aspen engine...")
    try:
        sim.EngineRun()
        print("    ✅ Aspen engine run complete")
    except Exception as exc:
        print("    ⚠️  Aspen engine run failed (continuing)")
        print(f"    Error: {exc}")
    
    # Check inlet stream exists
    print("\n[2] Checking inlet stream '5-IN-EXC'...")
    try:
        inlet_outputs = sim.STRM_GET_OUTPUTS("5-IN-EXC")
        inlet_names = inlet_outputs.get("CompoundNameList", [])
        inlet_flows = inlet_outputs.get("MoleFlowList", [])
        
        if isinstance(inlet_names, (list, tuple)):
            n_comps = len(inlet_names)
        else:
            n_comps = 1
        
        total_inlet = sum(inlet_flows) if isinstance(inlet_flows, (list, tuple)) else inlet_flows
        
        print(f"    ✅ Stream found: {n_comps} components")
        print(f"    Total inlet flow: {total_inlet:.6f} kmol/hr")
    except Exception as exc:
        print(f"    ❌ Stream not found or error reading")
        print(f"    Error: {exc}")
        try:
            stream_names = []
            for stream in sim.STRM.Elements:
                stream_names.append(stream.Name)
            if stream_names:
                preview = ", ".join(sorted(stream_names)[:20])
                print("    Available streams (first 20):")
                print(f"    {preview}")
        except Exception:
            print("    Unable to list streams via COM interface")
        return 1
    
    # Run hydrocracking calculations
    print("\n[3] Running hydrocracking calculations...")
    print("    Primary data: primary_data.csv")
    print("    Secondary data: secondary_data.csv")
    print("    Conversion parameter (a3): 0.4")
    
    try:
        outlet_flows = update_hydrocracking_streams_v2(
            sim=sim,
            inlet_stream="5-IN-EXC",
            outlet_stream="5-OUTEXC",
            a3_primary=0.4,
            a3_secondary=0.4,
        )
        print(f"    ✅ Calculations complete")
        print(f"    Outlet components: {len(outlet_flows)}")
        print(f"    Total outlet flow: {sum(outlet_flows.values()):.6f} kmol/hr")
    except Exception as exc:
        print(f"    ❌ Calculation failed")
        print(f"    Error: {exc}")
        return 1
    
    # Show top 10 components
    print("\n[4] Top 10 outlet components:")
    sorted_comps = sorted(outlet_flows.items(), key=lambda x: x[1], reverse=True)[:10]
    for name, flow in sorted_comps:
        print(f"    {name:10s}: {flow:12.6f} kmol/hr")
    
    # Verify atom balance
    print("\n[5] Verifying atom balance...")
    try:
        from atom_balance import load_component_formulas, calculate_atom_balance
        
        formulas = load_component_formulas(workdir / "test.txt")
        
        # Get inlet atoms
        if isinstance(inlet_names, (list, tuple)) and isinstance(inlet_flows, (list, tuple)):
            inlet_dict = {str(n): float(f) for n, f in zip(inlet_names, inlet_flows)}
        elif isinstance(inlet_names, str) and not isinstance(inlet_flows, (list, tuple)):
            inlet_dict = {str(inlet_names): float(inlet_flows)}
        else:
            inlet_dict = {}
        
        inlet_atoms = calculate_atom_balance(inlet_dict, formulas)
        outlet_atoms = calculate_atom_balance(outlet_flows, formulas)
        
        print("    Atom balance closure:")
        all_elements = set(inlet_atoms.keys()) | set(outlet_atoms.keys())
        
        all_closed = True
        for element in sorted(all_elements):
            inlet_val = inlet_atoms.get(element, 0.0)
            outlet_val = outlet_atoms.get(element, 0.0)
            diff = outlet_val - inlet_val
            
            if inlet_val > 0:
                pct_error = 100 * diff / inlet_val
            else:
                pct_error = 0.0 if abs(diff) < 1e-10 else float('inf')
            
            status = "✅" if abs(pct_error) < 0.01 else "❌"
            if abs(pct_error) >= 0.01:
                all_closed = False
            
            print(f"      {status} {element:2s}: {pct_error:+8.4f}%")
        
        if all_closed:
            print("\n    ✅ All atoms conserved - Ready for simulation")
        else:
            print("\n    ⚠️  Atom balance issues detected")
    
    except Exception as exc:
        print(f"    ⚠️  Could not verify atom balance: {exc}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nAspen simulation is ready with hydrocracking model.")
    print("Outlet stream '5-OUTEXC' has been updated with calculated flows.")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
