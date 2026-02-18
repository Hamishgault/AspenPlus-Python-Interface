

# **Catalyst Analysis Ideas**

This workflow outlines a probabilistic, model‑based approach for evaluating catalyst performance using rate laws, Bayesian regression, and reactor simulations.

***

## **1. Experiment**

You begin by gathering experimental data (reaction rates, partial pressures, temperatures, etc.).  
These measurements form the evidence used later in the parameter‑estimation step.

***

## **2. Choose Rate Law**

Select an appropriate kinetic model to describe the reaction system.  
Common choices include Langmuir–Hinshelwood or power‑law expressions.

Example LH form:

$$
r = \frac{k \cdot P_{\mathrm{CO}}^m P_{\mathrm{H_2}}^n}{(1 + K_{CO} P_{CO} + K_{H_2} P_{H_2})}
$$

Or a simplified power‑law:

$$
r = k \cdot P_{\mathrm{CO}}^{a} P_{\mathrm{H_2}}^{b}
$$

***

## **3. Define Priors**

Specify prior distributions for all model parameters:

$$
\theta = \{k_0,\; E_a,\; K_{CO},\; K_{H_2},\; a,\; \alpha, \dots\}
$$



These priors encode initial engineering knowledge before fitting to data.

***

## **4. Bayesian Regression (MCMC)**

Perform Bayesian inference (e.g., Markov Chain Monte Carlo) to estimate parameter distributions for each catalyst.

This yields:

*   Parameter means
*   Uncertainties
*   Correlations between parameters

This step converts noisy experimental data into statistically robust kinetic parameters.

***

## **5. Posterior Distribution + Correlation Matrix**

Use the posterior results to understand parameter interactions and confidence levels.  
These distributions will propagate through to the reactor model, giving probabilistic predictions rather than single values.

***

## **6. Reactor Simulation**

Feed the posterior distributions into a reactor model to evaluate how uncertainties in kinetics affect reactor performance.

***

## **7. Probabilistic Catalyst Ranking**

Rank catalysts not just by best‑fit parameters, but by **probabilistic outcomes** (e.g., likelihood of meeting performance targets).

This is more robust than simple point‑estimate comparisons.

***

## **8. Performance Metrics**

Evaluate final performance distributions, such as:

*   **PFDs** (Product Formation Distributions):  
    – XCO₂  
    – C5+ yields
*   **Risk metrics**
*   Other KPIs depending on the process

This allows uncertainty‑aware, risk‑informed catalyst selection.


1️⃣ Organize your raw data
Continuous gas analyzer (CO, CO₂, O₂)

Export timestamped CSV for each run

Columns: Time [hr], CO [mol%], CO2 [mol%], O2 [mol%]

Optional: Temperature, Pressure if measured continuously

GC gas data (C₁–C₅, BTX)

Export timestamped CSV for each sample

Columns: Time [hr], C1 [mol%], …, C5 [mol%], BTX [mol%]

Include sampling uncertainties (instrument repeatability)

GC liquid data

Export manual samples as CSV

Columns: Time [hr], C5+ [wt%], C6+ [wt%], etc.

Treat as cumulative over sampling interval

2️⃣ Preprocess

Time alignment

Keep continuous gas analyzer as master time vector

Interpolate GC data to those times or use exact sample times in Bayesian likelihood

Unit consistency

Convert all measurements to same basis (mol fraction, molar flow, or g/s)

Error estimation

Gas analyzer: σ ~ 1–3% of reading

GC gas: σ ~ 5% of reading

GC liquid: σ ~ 5–10% of reading

3️⃣ Build a model-ready dataset

One Python dictionary or Pandas DataFrame per run, e.g.:

run1 = {
    "time": np.array([...]),          # hours
    "CO": np.array([...]),
    "CO2": np.array([...]),
    "C1": np.array([...]),
    "C2": np.array([...]),
    "C5plus": np.array([...]),
    "sigma": {"CO":0.01, "C1":0.05, "C5plus":0.1}
}

This can be passed directly into PyMC / NumPyro likelihood functions

4️⃣ Model setup

Define kinetic ODEs (PFR or CSTR approximation)

Include RWGS + FT reactions

Integrate ODEs over your time array

Compare model outputs to each measurement type with its σ

Bayesian regression uses all three data types simultaneously

5️⃣ Computational setup

Python stack:

pandas → data import & preprocessing

numpy → arrays & math

scipy.integrate.odeint or solve_ivp → reactor ODEs

pymc or numpyro → Bayesian inference

Optional: matplotlib or seaborn → plotting posterior distributions

6️⃣ Key points for heterogeneous data

No need to force uniform sampling — Bayesian framework handles irregular measurements

Assign measurement uncertainty per dataset to balance contributions

Sparse datasets (GC liquids) → posterior for those parameters will be wider (more uncertainty)