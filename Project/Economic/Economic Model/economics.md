# Economics Model Overview

This folder contains a small toolkit that reads inputs from the Excel file, runs a techno-economic calculation, and saves results in easy-to-use files. Below is a plain-language description of what each file does and how they fit together.

## Files in this folder

### Economics_eSAF.py
This is the main runner. It:
- reads inputs from "Economics eSAF.xlsx",
- calls the electrolyzer helper (WE) to compute energy and cost pieces,
- calculates yearly costs, revenues, and cash flow,
- computes key summary outputs (like IRR, BEP, VAN),
- saves results (tables, arrays, and plots) into an output folder,
- prints a short summary for quick review.

It also produces a stacked bar chart that shows how the price is built up for each product (kerosene, naphtha, diesel).

### we_function.py
This file contains the WE() function. Think of it as the electrolyzer calculator. It uses the technical inputs to compute:
- annual energy use,
- hydrogen production rate,
- capital and operating cost pieces,
- a full cost per kg of hydrogen.

These numbers are then used by Economics_eSAF.py.

### WE_sens.py
This is a simple sensitivity study. It sweeps two inputs (electricity price and operating hours) and plots how the hydrogen cost changes across the grid. It is helpful for intuition and quick checks.

### results_viewer.py
This is a lightweight viewer. It reads saved results from the output folder and prints them, without re-running the full model. It can also show the saved plot if you want.

### outputs/
This folder is created automatically. It stores:
- results_table.csv and results_table.xlsx (full yearly table),
- arrays.npz (compact numerical results),
- summary.json (short, readable summary),
- market_price.png (the stacked bar chart).

## How the workflow fits together

1) Economics_eSAF.py reads the Excel inputs.
2) It calls WE() for electrolyzer costs and output.
3) It builds yearly costs and revenues.
4) It computes cash flows and summary metrics.
5) It saves outputs and prints a short report.
6) results_viewer.py can be run later to inspect results without recalculating.

## How to add a Monte Carlo simulation (intuitive overview)

A Monte Carlo simulation is just the same model run many times with slightly different inputs. The goal is to see a range of possible outcomes instead of a single number.

A simple way to add it here:

1) Pick a few uncertain inputs
   - electricity price (EE)
   - fuel price (BRENT)
   - carbon price (ETS1/ETS2)
   - capital cost (CAPEX)

2) Decide reasonable ranges
   - example: EE between 0.05 and 0.15
   - example: CAPEX between 0.8x and 1.2x the base value

3) Generate many random samples
   - for each run, draw a random value for each uncertain input
   - keep everything else fixed

4) Run the model for each sample
   - call val() with the sampled inputs
   - store outputs like IRR, BEP, and VAN

5) Summarize the results
   - show histograms (how often each outcome happens)
   - show percentiles (best, typical, worst cases)
   - check which inputs drive the biggest changes

This approach gives a more realistic picture: not a single "answer", but a distribution of outcomes. It is also easy to add without changing the core logic, because you can treat the model as a black box and just repeat it with different inputs.

If you want, I can add a small Monte Carlo driver script that does this and saves the results into outputs/.

## Inputs: what they represent

Below is a plain-language description of the key inputs used in the TEA and Monte Carlo runs. Names follow the code and Excel columns.

### Economic inputs (econ)
- d_e: Debt fraction of CAPEX (how much is financed by debt vs equity).
- dr: Debt interest rate.
- dp: Debt repayment period (years).
- DeP_n: Depreciation period (years).
- infl: Inflation rate.
- tax: Corporate tax rate.
- Py: Start year of the plant. Plant lifetime is computed as 2050 - Py.
- WACC: Weighted Average Cost of Capital, used as the discount rate.

### Real/market inputs (real)
- EE: Electricity price (EUR/MWh). Drives electrolyzer operating cost.
- cambio: Exchange rate factor used in cost conversions.
- conv: Unit conversion factor used for product price calculations.
- BRENT: Crude oil reference price (USD/bbl or EUR/bbl depending on data setup).
- DIFF_LPG, DIFF_NAPTHA, DIFF_KERO, DIFF_DIESEL, DIFF_WAX: Product price differentials vs BRENT.
- Met: Methanol or heat fuel price used in process energy cost.
- ETS1, ETS2: Carbon price levels used for different emissions categories.
- CC: CO2 capture cost (EUR/ton CO2).
- ReFuel: ReFuel credit or premium (EUR/ton product) used to close the BEP.

### Plant inputs (plant)
- CAPEX: Total capital expenditure.
- CO2_feed, CO2_compr: CO2 feed and compression energy/cost factors.
- H2_feed, H2_compr: Hydrogen feed and compression energy/cost factors.
- Pwr, Heat: Process power and heat demand factors.
- Operatori: Labor cost component.
- Overhead: Overhead cost component.
- Manutenzione: Maintenance cost factor.
- CO2_out: CO2 emissions factor.
- Naptha_mass, Kero_mass, Diesel_mass: Product yields per unit H2.
- Naptha_CO2, Kero_CO2, Diesel_CO2: CO2 factors per product.
- Naptha_GJ, Kero_GJ, Diesel_GJ: Energy factors per product.

### Electrolyzer inputs (we / we_matrix)
- we[0] (PP): Installed electrolyzer power (MW).
- we[1] (WH): Operating hours per year.
- we[2] (Use): Utilization factor (average load / nameplate).
- we_matrix[:, 1]: Electrolyzer technical and cost parameters used by WE().
   The key ones sampled in Monte Carlo are:
   - Electrolyzer_eff: Efficiency term used in H2 production calculation.
   - Stack_life: Stack lifetime used for replacement schedule.

## Results: what they mean

### Core TEA metrics
- VAN: Net present value of discounted cash flows (EUR). Positive is good, negative means value destruction.
- IRR: Internal rate of return. If cash flows never cross from negative to positive, IRR is undefined.
- BEP: Break-even ReFuel premium (EUR/ton) that makes VAN ~ 0.
- LCOH: Levelized cost of hydrogen (EUR/kg) broken into CAPEX, EE, stack, and OPEX components.
- COP: Cost of production per product (EUR/ton), broken into cost components.

### Monte Carlo summaries
- Percentiles (p10, p50, p90): Distribution summary of outputs across samples.
   - p10 is a low case, p50 is the median, p90 is a high case.
- Correlation sensitivity: Simple correlation between an input and an output.
   - Useful for ranking, but it does not isolate the effect of each input.
- Regression sensitivity (standardized beta, beta):
   - beta is the standardized regression coefficient.
   - It tells you how many standard deviations VAN changes when that variable changes by one standard deviation,
      holding all other variables constant.
   - This is more rigorous than correlation because it isolates the effect of each input.

### Plots
- Tornado plots: Ranked horizontal bars showing the strongest drivers (correlation or regression).
- Scatter plots: Show shape and non-linearities for the top drivers.
- Histograms: Show the full distribution of outputs (IRR, VAN, BEP, or LCOH).
