"""Test the new formula-based hydrocracking implementation."""

import numpy as np
from pathlib import Path
from hydrocracking_v2 import (
    load_component_data,
    build_stoichiometric_matrix,
    compute_conversion,
)


def create_test_inlet_flows() -> dict[str, float]:
    """Create synthetic inlet flows for testing."""
    # Representative inlet composition for testing
    inlet_flows = {
        'CH4': 0.000711, 'MEOH': 0.001159157, 'C2': 0.00257012,
        'C3': 0.023793871, 'C4': 0.022656469, 'C4-IP': 0.0000657,
        'C5': 0.012431194, 'C5-IP': 0.00079740295, 'C5-N': 0.0000778,
        'C6-IP': 0.0029408237, 'C6': 0.0047346595, 'C6-N': 0.00020961098,
        'C7': 0.0011693698, 'C7-IP': 0.0014479783,
        'C8': 0.00078531895, 'C9': 0.000134, 'C10': 0.0000531,
        'C11': 0.00000637, 'C12': 0.00000551, 'C13': 0.00000456,
        'C14': 0.00000447, 'C15': 0.00103, 'C16': 0.00102,
        'C17': 0.0525, 'C18': 0.03806703, 'C19': 0.031509677,
        'C20': 0.024954337, 'C21': 0.022686981, 'C22': 0.020418276,
        'C23': 0.018149588, 'C24': 0.017015208, 'C25': 0.014746546,
        'C26': 0.012477808, 'C27': 0.010209162,
        'H2': 5.8299313, 'CO2': 0.086674792, 'CO': 0.0000574, 'H2O': 0.00518735,
    }
    return inlet_flows


def test_hydrocracking_v2():
    """Test the new formula-based hydrocracking model."""
    base_dir = Path(__file__).resolve().parent
    
    primary_csv = base_dir / "primary_data.csv"
    secondary_csv = base_dir / "secondary_data.csv"

    print("=" * 80)
    print("HYDROCRACKING V2 - FORMULA-BASED MODEL TEST")
    print("=" * 80)

    # Create test inlet flows
    print("\n[1] Creating test inlet flows...")
    inlet_flows = create_test_inlet_flows()
    print(f"    Created {len(inlet_flows)} components")
    print(f"    Total inlet flow: {sum(inlet_flows.values()):.6f} kmol/hr")

    # Load component data
    print("\n[2] Loading component data...")
    primary_comps, primary_map = load_component_data(primary_csv)
    secondary_comps, secondary_map = load_component_data(secondary_csv)
    print(f"    Primary components: {len(primary_comps)}")
    print(f"    Secondary components: {len(secondary_comps)}")
    
    # Test conversion formula
    print("\n[3] Testing conversion formula (a3=0.4)...")
    test_carbons = [1, 5, 8, 10, 15, 18, 25, 40]
    for n in test_carbons:
        conv = compute_conversion(n, 0.4)
        print(f"    C{n:2d}: conversion = {conv:.6f}")
    
    # Build stoichiometric matrices
    print("\n[4] Building stoichiometric matrices...")
    primary_stoich = build_stoichiometric_matrix(primary_comps, 0.4)
    secondary_stoich = build_stoichiometric_matrix(secondary_comps, 0.4)
    print(f"    Primary matrix shape: {primary_stoich.shape}")
    print(f"    Secondary matrix shape: {secondary_stoich.shape}")
    
    # Check matrix properties
    print("\n[5] Matrix properties...")
    print(f"    Primary diagonal range: [{np.diag(primary_stoich).min():.6f}, {np.diag(primary_stoich).max():.6f}]")
    print(f"    Primary off-diagonal range: [{primary_stoich[~np.eye(len(primary_comps), dtype=bool)].min():.6f}, {primary_stoich[~np.eye(len(primary_comps), dtype=bool)].max():.6f}]")
    
    # Build inlet vectors
    print("\n[6] Building inlet vectors...")
    primary_inlet = np.array([inlet_flows.get(comp.name, 0.0) for comp in primary_comps], dtype=np.float64)
    secondary_inlet = np.array([inlet_flows.get(comp.name, 0.0) for comp in secondary_comps], dtype=np.float64)
    print(f"    Primary inlet total: {primary_inlet.sum():.6f} kmol/hr")
    print(f"    Secondary inlet total: {secondary_inlet.sum():.6f} kmol/hr")
    
    # Check which inlet components are not in the reaction sheets
    inlet_set = set(inlet_flows.keys())
    primary_set = set(comp.name for comp in primary_comps)
    missing_in_primary = inlet_set - primary_set
    if missing_in_primary:
        missing_flow = sum(inlet_flows[name] for name in missing_in_primary)
        print(f"\n    ⚠️  {len(missing_in_primary)} inlet components not in Primary sheet:")
        print(f"    Missing flow: {missing_flow:.6f} kmol/hr ({100*missing_flow/sum(inlet_flows.values()):.1f}%)")
        print(f"    Missing: {sorted(missing_in_primary)}")
        print(f"    Note: These components will pass through unchanged (CO2, CO, H2O)")
    
    # Apply stoichiometric matrices in SERIES
    print("\n[7] Computing reactions in series: Primary → Secondary...")
    primary_outlet = primary_stoich @ primary_inlet
    print(f"    Primary outlet total: {primary_outlet.sum():.6f} kmol/hr")
    
    # Secondary acts on primary outlet (series connection)
    secondary_inlet = primary_outlet
    secondary_outlet = secondary_stoich @ secondary_inlet
    print(f"    Secondary outlet total: {secondary_outlet.sum():.6f} kmol/hr")
    
    # Final outlet
    print("\n[8] Building final outlet (from secondary stage)...")
    outlet_flows = {}
    for i, comp in enumerate(primary_comps):
        outlet_flows[comp.name] = float(secondary_outlet[i])
    
    # Add pass-through components
    for name in missing_in_primary:
        outlet_flows[name] = inlet_flows[name]
    
    hydrocarbon_outlet = sum(outlet_flows[comp.name] for comp in primary_comps)
    passthrough_outlet = sum(outlet_flows.get(name, 0.0) for name in missing_in_primary)
    total_out = sum(outlet_flows.values())
    
    print(f"    Hydrocarbon outlet: {hydrocarbon_outlet:.6f} kmol/hr")
    print(f"    Pass-through outlet: {passthrough_outlet:.6f} kmol/hr")
    print(f"    Total outlet flow: {total_out:.6f} kmol/hr")
    
    # Show top 10 components
    print("\n[9] Top 10 outlet components:")
    sorted_comps = sorted(outlet_flows.items(), key=lambda x: x[1], reverse=True)[:10]
    for name, flow in sorted_comps:
        inlet_val = inlet_flows.get(name, 0.0)
        delta = flow - inlet_val
        print(f"    {name:10s}  In: {inlet_val:12.6e}  Out: {flow:12.6e}  Δ: {delta:+12.6e}")
    
    # Show heavy hydrocarbon behavior (C18-C27)
    print("\n[10] Heavy hydrocarbon behavior (C18-C27):")
    heavy_comps = [(comp.name, inlet_flows.get(comp.name, 0.0), outlet_flows.get(comp.name, 0.0))
                   for comp in primary_comps 
                   if comp.carbon_number >= 18 and comp.carbon_number <= 27]
    for name, inlet_val, outlet_val in heavy_comps:
        delta = outlet_val - inlet_val
        pct = 100 * delta / inlet_val if inlet_val > 0 else 0
        print(f"    {name:10s}  In: {inlet_val:12.6e}  Out: {outlet_val:12.6e}  Δ: {delta:+12.6e} ({pct:+6.1f}%)")
    
    # Mass balance check
    print("\n[11] Mass balance:")
    total_in = sum(inlet_flows.values())
    print(f"    Total in:  {total_in:.6f} kmol/hr")
    print(f"    Total out: {total_out:.6f} kmol/hr")
    print(f"    Difference: {total_out - total_in:+.6f} kmol/hr ({100*(total_out - total_in)/total_in:+.2f}%)")
    
    # Check for negatives
    negatives = [(n, v) for n, v in outlet_flows.items() if v < 0]
    if negatives:
        print(f"\n⚠️  WARNING: {len(negatives)} components have negative outlet flows:")
        for name, val in negatives[:5]:
            print(f"    {name}: {val:.6e}")
    else:
        print("\n✅ All outlet flows are non-negative")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_hydrocracking_v2()
