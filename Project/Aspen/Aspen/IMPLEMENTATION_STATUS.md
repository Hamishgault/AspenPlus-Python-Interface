# Hydrocracking Model - Clean Implementation Summary

## Status: IN PROGRESS - Formula Structure Identified

## What Was Built

### 1. Simple Input Files (✓ COMPLETE)
- **primary_data.csv**: Component names and carbon numbers (92 components)
- **secondary_data.csv**: Same structure as primary

Format:
```
name,carbon_number
CH4,1
MEOH,1
C2,2
...
C54,54
```

### 2. Formula-Based Calculator (✓ IMPLEMENTED)
- **hydrocracking_v2.py**: Calculates all conversions and reactions from formulas
- No pre-computed values needed from Excel
- Only requires: component names, carbon numbers, and parameter `a3=0.4`

### 3. Key Formulas Implemented

**Conversion Formula:**
```python
if n < 8: conversion = 0
elif n >= 18: conversion = 1  
else: conversion = (exp(a3*(n-7)) - 1) / (exp(a3*(18-7)) - 1)
```

**Production Pattern:**
- Heavy component Cn (n ≥ 8) cracks into:
  - C3: gets 1 × prod_factor
  - C4 through C(n-1): each gets 2 × prod_factor
- Where: `prod_factor = conversion / (n - 6)`

## Current Issue

Mass balance error (+49.58% when summing primary+secondary)

**Root cause identified:** 
- Excel's "Prod. Factor" column = `conversion / (n-6) * inlet_flow` (includes inlet amount)
- My implementation: `conversion / (n-6)` (coefficient only)
- Primary and Secondary sheets likely represent SAME reaction, not two separate reactions to sum

## Next Steps

1. **Clarify Primary vs Secondary relationship**  
   - Are they: parallel reactions, sequential stages, or different product fractions?
   - User to provide guidance on how Excel uses both sheets

2. **Fix stoichiometric matrix**
   - Currently: stoich[i,j] = coefficient (unitless)
   - Should be: stoich[i,j] = absolute amount OR keep as coefficient but don't sum primary+secondary

3. **Validate against Excel output**
   - Compare computed outlet flows with Primary.csv column 99 (Out)
   - Ensure mass balance matches expected value

## Files Created

| File | Purpose | Status |
|------|---------|--------|
| primary_data.csv | Simple component list | ✓ Ready |
| secondary_data.csv | Simple component list | ✓ Ready |
| hydrocracking_v2.py | Formula-based calculator | ✓ Implemented, needs fix |
| test_hydrocracking_v2.py | Test script | ✓ Working |
| debug_stoich.py | Debug stoich matrix | ✓ Identified issue |

## Comparison: Old vs New Approach

### Old Approach (hydrocracking_calc.py)
- Required Pre-computed CSV exports from Excel  
- Primary.csv, Secondary.csv with 92 rows × 103 columns
- Read conversion values from column 2
- Mass balance: -3.24% error

### New Approach (hydrocracking_v2.py)  
- Only needs simple component lists
- Python computes all conversions and reactions
- Formula-based, no pre-computation needed
- **Current status:** Mass balance calculation needs correction

## What User Requested

✓ "Only have two CSV files (primary_data and secondary_data)"  
✓ "Python does all the calculations"  
⏳ "Aspen integration" - same interface as before, needs testing
⏳ "Debug using hydrocracking.csv formulas" - in progress

## Correct Implementation Path Forward

Based on Excel formula analysis, the correct approach is likely:
1. Build ONE stoichiometric matrix (not sum primary+secondary)
2. Understand if Primary/Secondary represent different reactor stages or product splits
3. Match Excel's outlet calculation exactly
4. Validate H2 consumption (currently missing from model)
