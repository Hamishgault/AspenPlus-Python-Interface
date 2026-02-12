"""Calculate atom balance for hydrocracking reactions."""

import re
from pathlib import Path
from typing import Dict, Tuple


def parse_formula(formula: str) -> Dict[str, int]:
    """
    Parse molecular formula to get atom counts.
    
    Examples:
        "C18H38" -> {'C': 18, 'H': 38}
        "CH4O" -> {'C': 1, 'H': 4, 'O': 1}
        "CO2" -> {'C': 1, 'O': 2}
        "H2" -> {'H': 2}
    """
    atoms = {}
    # Match element symbol followed by optional number
    pattern = r'([A-Z][a-z]?)(\d*)'
    matches = re.findall(pattern, formula)
    
    for element, count in matches:
        if element:  # Skip empty matches
            count = int(count) if count else 1
            atoms[element] = atoms.get(element, 0) + count
    
    return atoms


def load_component_formulas(txt_path: Path) -> Dict[str, Dict[str, int]]:
    """Load component formulas from test.txt (Aspen property table)."""
    # Component formulas from Aspen property table
    formula_strings = {
        'CO2': 'CO2', 'H2O': 'H2O', 'H2': 'H2', 'CO': 'CO', 'CH4': 'CH4',
        'MEOH': 'CH4O', 'C2': 'C2H6', 'C2-O': 'C2H4', 'C3': 'C3H8', 'C3-O': 'C3H6',
        'C4': 'C4H10', 'C4-IP': 'C4H10', 'C4-O': 'C4H8', 'C5': 'C5H12', 'C5-IP': 'C5H12',
        'C5-O': 'C5H10', 'C5-N': 'C5H10', 'C6-IP': 'C6H14', 'C6': 'C6H14', 'C6-O': 'C6H12',
        'C6-A': 'C6H6', 'C6-N': 'C6H12', 'C7': 'C7H16', 'C7-IP': 'C7H16', 'C7-O': 'C7H14',
        'C7-A': 'C7H8', 'C7-N': 'C7H14', 'C8': 'C8H18', 'C8-IP': 'C8H18', 'C8-O': 'C8H16',
        'C8-N': 'C8H16', 'C8-A': 'C8H10', 'C9': 'C9H20', 'C9-IP': 'C9H20', 'C9-O': 'C9H18',
        'C9-N': 'C9H18', 'C9-A': 'C9H10', 'C10': 'C10H22', 'C10-IP': 'C10H22', 'C10-O': 'C10H20',
        'C10-N': 'C10H20', 'C10-A': 'C10H14', 'C11': 'C11H24', 'C11-IP': 'C11H24',
        'C11-A': 'C11H16', 'C11-O': 'C11H22', 'C12-IP': 'C12H26', 'C12': 'C12H26',
        'C12-O': 'C12H24', 'C12-A': 'C12H18', 'C12-N': 'C12H24', 'C13-IP': 'C13H28',
        'C13-O': 'C13H26', 'C13': 'C13H28', 'C14-IP': 'C14H30', 'C14': 'C14H30',
        'C15-IP': 'C15H32', 'C15': 'C15H32', 'C16-IP': 'C16H34', 'C16': 'C16H34',
        'C17-IP': 'C17H36', 'C17': 'C17H36', 'C18': 'C18H38', 'C19': 'C19H40',
        'C20': 'C20H42', 'C21': 'C21H44', 'C22': 'C22H46', 'C23': 'C23H48',
        'C24': 'C24H50', 'C25': 'C25H52', 'C26': 'C26H54', 'C27': 'C27H56',
    }
    
    formulas = {}
    for name, formula_str in formula_strings.items():
        formulas[name] = parse_formula(formula_str)
    
    return formulas


def calculate_atom_balance(
    flows: Dict[str, float],
    formulas: Dict[str, Dict[str, int]]
) -> Dict[str, float]:
    """Calculate total atoms from component flows."""
    atom_totals = {}
    
    for comp_name, flow in flows.items():
        if comp_name in formulas:
            for element, count in formulas[comp_name].items():
                atom_totals[element] = atom_totals.get(element, 0.0) + flow * count
    
    return atom_totals


def test_atom_balance():
    """Test atom balance for the hydrocracking system."""
    base_dir = Path(__file__).resolve().parent
    
    # Import after defining path
    import sys
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    
    from test_hydrocracking_v2 import create_test_inlet_flows
    from hydrocracking_v2 import (
        load_component_data,
        build_stoichiometric_matrix,
    )
    import numpy as np
    
    txt_path = base_dir / "test.txt"
    primary_csv = base_dir / "primary_data.csv"
    secondary_csv = base_dir / "secondary_data.csv"
    
    print("=" * 80)
    print("ATOM BALANCE TEST - HYDROCRACKING V2")
    print("=" * 80)
    
    # Load component formulas
    print("\n[1] Loading component formulas from test.txt...")
    formulas = load_component_formulas(txt_path)
    print(f"    Loaded formulas for {len(formulas)} components")
    
    # Test formula parsing
    print("\n[2] Sample formulas:")
    test_comps = ['H2', 'CO2', 'CH4', 'MEOH', 'C3', 'C18']
    for comp in test_comps:
        if comp in formulas:
            print(f"    {comp:6s}: {formulas[comp]}")
    
    # Create inlet flows
    print("\n[3] Creating test inlet flows...")
    inlet_flows = create_test_inlet_flows()
    print(f"    Total components: {len(inlet_flows)}")
    
    # Load component data
    print("\n[4] Loading component data and building matrices...")
    primary_comps, primary_map = load_component_data(primary_csv)
    secondary_comps, secondary_map = load_component_data(secondary_csv)
    
    primary_stoich = build_stoichiometric_matrix(primary_comps, a3=0.4)
    secondary_stoich = build_stoichiometric_matrix(secondary_comps, a3=0.4)
    
    # Build inlet vectors
    primary_inlet = np.zeros(len(primary_comps))
    missing_in_primary = set()
    
    for name, flow in inlet_flows.items():
        if name in primary_map:
            idx = primary_map[name]
            primary_inlet[idx] = flow
        else:
            missing_in_primary.add(name)
    
    # Run reactions in series
    print("\n[5] Computing reactions: Primary → Secondary...")
    primary_outlet_vec = primary_stoich @ primary_inlet
    secondary_inlet_vec = primary_outlet_vec
    secondary_outlet_vec = secondary_stoich @ secondary_inlet_vec
    
    # Build outlet flows dictionary
    outlet_flows = {}
    for i, comp in enumerate(primary_comps):
        outlet_flows[comp.name] = float(secondary_outlet_vec[i])
    
    # Add pass-through components (H2, CO2, CO, H2O)
    for name in missing_in_primary:
        outlet_flows[name] = inlet_flows[name]
    
    print(f"    Inlet total: {sum(inlet_flows.values()):.6f} kmol/hr")
    print(f"    Outlet total: {sum(outlet_flows.values()):.6f} kmol/hr")
    
    # Calculate atom balances
    print("\n[6] Calculating atom balances...")
    inlet_atoms = calculate_atom_balance(inlet_flows, formulas)
    outlet_atoms = calculate_atom_balance(outlet_flows, formulas)
    
    print("\n    INLET ATOMS (kmol/hr):")
    for element in sorted(inlet_atoms.keys()):
        print(f"      {element:2s}: {inlet_atoms[element]:12.6f}")
    
    print("\n    OUTLET ATOMS (kmol/hr):")
    for element in sorted(outlet_atoms.keys()):
        print(f"      {element:2s}: {outlet_atoms[element]:12.6f}")
    
    # Calculate atom balance errors
    print("\n[7] ATOM BALANCE CLOSURE:")
    all_elements = set(inlet_atoms.keys()) | set(outlet_atoms.keys())
    
    total_error = 0.0
    max_error = 0.0
    max_error_element = None
    
    for element in sorted(all_elements):
        inlet_val = inlet_atoms.get(element, 0.0)
        outlet_val = outlet_atoms.get(element, 0.0)
        diff = outlet_val - inlet_val
        
        if inlet_val > 0:
            pct_error = 100 * diff / inlet_val
        else:
            pct_error = 0.0 if abs(diff) < 1e-10 else float('inf')
        
        status = "✅" if abs(pct_error) < 0.01 else "❌"
        print(f"    {status} {element:2s}: {diff:+12.6f} ({pct_error:+8.4f}%)")
        
        total_error += abs(diff)
        if abs(pct_error) > abs(max_error):
            max_error = pct_error
            max_error_element = element
    
    print(f"\n    Total atom imbalance: {total_error:.6f} kmol/hr")
    print(f"    Maximum error: {max_error:+.4f}% ({max_error_element})")
    
    # Conclusion
    print("\n" + "=" * 80)
    if abs(max_error) < 0.01:
        print("✅ ATOM BALANCE CLOSED - System is physically consistent")
        print("   Ready for Aspen simulation")
    elif abs(max_error) < 1.0:
        print("⚠️  ATOM BALANCE WARNING - Small numerical errors present")
        print("   May work in Aspen but check convergence")
    else:
        print("❌ ATOM BALANCE FAILED - System violates conservation laws")
        print("   WILL FAIL in Aspen simulation")
        print("\n   Diagnosis:")
        print("   - Hydrocarbons are being created without consuming H2")
        print("   - Need to model H2 consumption in hydrocracking reactions")
        print("   - Stoichiometric matrix needs H2 as reactant")
    print("=" * 80)


if __name__ == "__main__":
    test_atom_balance()
