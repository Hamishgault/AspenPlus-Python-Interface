"""
Hydrocracking Calculator - Formula-Based Implementation

This module implements the complete hydrocracking reaction model using formulas
from the Excel model. Only requires simple CSV input files with component names
and carbon numbers.

Key Formulas:
- Conversion: 0 for n<8, exponential for 8≤n≤17, 1 for n≥18
- Production Factor: conversion / (n - 6)
- Stoichiometric Matrix: Outlet = stoich_matrix @ inlet_flows
  - Diagonal: (1 - conversion) for unreacted portion
  - Off-diagonal: production factors for cracking products
"""

import csv
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from CodeLibrary import Simulation


@dataclass
class ComponentData:
    """Data for a single hydrocarbon component."""
    name: str
    carbon_number: int
    index: int  # Position in component list


def compute_conversion(n: int, a3: float = 0.4) -> float:
    """
    Compute conversion fraction for component with carbon number n.
    
    Args:
        n: Carbon number
        a3: Exponential parameter (default 0.4)
        
    Returns:
        Conversion fraction (0 to 1)
    """
    if n < 8:
        return 0.0
    elif n >= 18:
        return 1.0
    else:
        # 8 ≤ n ≤ 17: exponential formula
        numerator = np.exp(a3 * (n - 7)) - 1
        denominator = np.exp(a3 * (18 - 7)) - 1
        return numerator / denominator


def build_stoichiometric_matrix(components: List[ComponentData], a3: float = 0.4) -> np.ndarray:
    """
    Build the stoichiometric matrix for hydrocracking reactions.
    
    Matrix structure:
    - stoich[i, j] = amount of component i produced from 1 unit of component j
    - Diagonal: (1 - conversion) = unreacted portion
    - Off-diagonal: production factors from cracking chemistry
    
    Heavy hydrocarbons (n ≥ 8) crack into lighter products:
    - Produce C3, C4, C5, ..., C(n-1) with specific stoichiometry
    - C3 coefficient: prod_factor
    - C4 through C(n-1): 2 × prod_factor each
    - Production factor = conversion / (n - 6)
    
    Args:
        components: List of component data with names and carbon numbers
        a3: Exponential parameter for conversion formula
        
    Returns:
        Stoichiometric matrix (n_components × n_components)
    """
    n_comp = len(components)
    stoich = np.zeros((n_comp, n_comp), dtype=np.float64)
    
    # Find H2 index (for H2 consumption)
    h2_idx = None
    for comp in components:
        if comp.name.strip() == "H2":
            h2_idx = comp.index
            break
    
    # Create mapping from carbon number to BASE component index only
    # Base components have names exactly "Cn" (e.g., "C3", "C4", not "C3-O", "C4-IP")
    carbon_to_base_idx: Dict[int, int] = {}
    for comp in components:
        name_clean = comp.name.strip()
        # Check if this is a base component (name is exactly "Cn")
        if name_clean == f"C{comp.carbon_number}":
            carbon_to_base_idx[comp.carbon_number] = comp.index
    
    for j, comp_j in enumerate(components):
        n_j = comp_j.carbon_number
        conv_j = compute_conversion(n_j, a3)
        
        # Diagonal: unreacted portion
        stoich[j, j] = 1.0 - conv_j
        
        # Off-diagonal: products from cracking comp_j
        if conv_j > 0 and n_j >= 8:
            # Production factor (before carbon balance normalization)
            prod_factor = conv_j / (n_j - 6)
            
            # Calculate total carbon in products using current formula
            # C3 gets 1×prod_factor, C4-C(n-1) get 2×prod_factor each
            carbon_in_products = 0.0
            carbon_in_products += 3 * prod_factor  # C3 contribution
            for n_p in range(4, n_j):
                carbon_in_products += n_p * (2.0 * prod_factor)  # C4 through C(n-1)
            
            # Carbon balance normalization factor
            # We need: carbon_in_products × norm_factor = n_j × conv_j
            carbon_from_reactant = n_j * conv_j
            norm_factor = carbon_from_reactant / carbon_in_products if carbon_in_products > 0 else 1.0
            
            # Apply normalized stoichiometry
            # C3 gets prod_factor × norm_factor
            if 3 in carbon_to_base_idx:
                i = carbon_to_base_idx[3]
                stoich[i, j] += prod_factor * norm_factor
            
            # C4 through C(n-1) get 2 × prod_factor × norm_factor each
            for n_product in range(4, n_j):
                if n_product in carbon_to_base_idx:
                    i = carbon_to_base_idx[n_product]
                    stoich[i, j] += 2.0 * prod_factor * norm_factor
            
            # H2 consumption for hydrocracking
            # Calculate H atoms needed: H_in_reactant - H_in_products = H2_consumed × 2
            # For saturated alkanes: CnH(2n+2)
            h_in_reactant = (2 * n_j + 2) * conv_j
            h_in_products = 0.0
            h_in_products += (2 * 3 + 2) * (prod_factor * norm_factor)  # C3
            for n_p in range(4, n_j):
                h_in_products += (2 * n_p + 2) * (2.0 * prod_factor * norm_factor)  # C4-C(n-1)
            
            # H2 consumption (negative if products need more H than reactant provides)
            h2_consumed = (h_in_reactant - h_in_products) / 2.0
            
            if h2_idx is not None:
                stoich[h2_idx, j] += h2_consumed
    
    return stoich


def load_component_data(csv_path: Path) -> Tuple[List[ComponentData], Dict[str, int]]:
    """
    Load component data from simple CSV file.
    
    Expected CSV format:
    name,carbon_number
    CH4,1
    MEOH,1
    C2,2
    ...
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        Tuple of (component list, name-to-index mapping)
    """
    components = []
    name_to_idx = {}
    
    with csv_path.open('r', newline='') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            name = row['name'].strip()
            carbon_number = int(row['carbon_number'])
            
            comp = ComponentData(name=name, carbon_number=carbon_number, index=idx)
            components.append(comp)
            name_to_idx[name] = idx
    
    return components, name_to_idx


def update_hydrocracking_streams_v2(
    sim: "Simulation",
    inlet_stream: str = "5-IN-EXC",
    outlet_stream: str = "5-OUTEXC",
    primary_data_csv: str | Path | None = None,
    secondary_data_csv: str | Path | None = None,
    a3_primary: float = 0.4,
    a3_secondary: float = 0.4,
) -> Dict[str, float]:
    """
    Compute outlet flows using formula-based hydrocracking model.
    
    This reads simple CSV files with component names and carbon numbers,
    then Python computes all conversions, production factors, and
    stoichiometric coefficients using the hydrocracking formulas.
    
    Args:
        sim: Aspen simulation instance
        inlet_stream: Name of inlet stream in Aspen
        outlet_stream: Name of outlet stream in Aspen
        primary_data_csv: Path to primary component data CSV
        secondary_data_csv: Path to secondary component data CSV
        a3_primary: Exponential parameter for primary reactions
        a3_secondary: Exponential parameter for secondary reactions
        
    Returns:
        Dictionary mapping component name to outlet flow (kmol/hr)
    """
    # Default paths
    base_dir = Path(__file__).resolve().parent
    if primary_data_csv is None:
        primary_data_csv = base_dir / "primary_data.csv"
    if secondary_data_csv is None:
        secondary_data_csv = base_dir / "secondary_data.csv"
    
    primary_data_csv = Path(primary_data_csv)
    secondary_data_csv = Path(secondary_data_csv)
    
    # Load component data
    primary_comps, primary_name_map = load_component_data(primary_data_csv)
    secondary_comps, secondary_name_map = load_component_data(secondary_data_csv)
    
    # Build stoichiometric matrices
    primary_stoich = build_stoichiometric_matrix(primary_comps, a3_primary)
    secondary_stoich = build_stoichiometric_matrix(secondary_comps, a3_secondary)
    
    # Get inlet flows from Aspen
    outputs = sim.STRM_GET_OUTPUTS(inlet_stream)
    names_raw = outputs.get("CompoundNameList", [])
    inlet_flows_raw = outputs.get("MoleFlowList", [])
    
    if not names_raw or not inlet_flows_raw:
        raise RuntimeError(
            f"No inlet flow data for stream '{inlet_stream}'. "
            "Check the stream name and run status."
        )
    
    # Convert to lists, handling various Aspen COM return types
    if isinstance(names_raw, (list, tuple)):
        names = list(names_raw)
    else:
        names = [str(names_raw)]
    
    if isinstance(inlet_flows_raw, (list, tuple)):
        inlet_flows_list = list(inlet_flows_raw)
    else:
        inlet_flows_list = [float(inlet_flows_raw)]
    
    if len(names) != len(inlet_flows_list):
        raise RuntimeError(f"Mismatch in component count: {len(names)} names vs {len(inlet_flows_list)} flows")
    
    inlet_flows: Dict[str, float] = {str(n): float(f) for n, f in zip(names, inlet_flows_list)}
    
    # Build inlet vectors for primary and secondary reactions
    primary_inlet = np.array([inlet_flows.get(comp.name, 0.0) for comp in primary_comps], dtype=np.float64)
    
    # Apply reactions in series: Primary → Secondary
    # Stage 1: Primary reactor
    primary_outlet = primary_stoich @ primary_inlet
    
    # Stage 2: Secondary reactor (acts on primary outlet)
    secondary_inlet = primary_outlet  # Series connection!
    secondary_outlet = secondary_stoich @ secondary_inlet
    
    # Final outlet is from the last stage (secondary)
    outlet_flows: Dict[str, float] = {}
    total_flow = 0.0
    
    for i, comp in enumerate(primary_comps):
        out_flow = float(secondary_outlet[i])
        outlet_flows[comp.name] = out_flow
        total_flow += out_flow
        sim.STRM_Set_ComponentFlowRate(outlet_stream, out_flow, comp.name)
    
    # Add pass-through components (not in reaction sheets)
    for name in inlet_flows:
        if name not in primary_name_map:
            flow = inlet_flows[name]
            outlet_flows[name] = flow
            total_flow += flow
            sim.STRM_Set_ComponentFlowRate(outlet_stream, flow, name)
    
    # Set total flow
    sim.STRM_Set_TotalFlowRate(outlet_stream, total_flow)
    
    return outlet_flows
