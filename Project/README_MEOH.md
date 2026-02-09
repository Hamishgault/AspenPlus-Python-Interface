# MEOH Aspen Setup

This folder contains the MEOH Aspen Plus model and helper scripts for running automated studies.

## Files
- `MEOH.bkp`: Aspen Plus backup file (main model)
- `Aspen_Test.py`: Example script to open the model and run temperature cases
- `plot_reactor_composition.py`: Plot outlet composition for baseline / +30 / -30 temperature profiles

## Prerequisites
- Aspen Plus installed locally
- Windows with COM access enabled
- Python 3.12+ in the project venv

## Setup
From the repo root:
1. Activate the venv.
2. Install dependencies:
   - `pip install -r requirements.txt`

## Run the example
From the repo root:
- `python Project/Aspen_Test.py`

## Plot outlet compositions
From the repo root:
- `python Project/plot_reactor_composition.py`

## Notes
- Ensure the reactor block name in the scripts matches your Aspen model (default: `PFR`).
- The scripts assume `MEOH.bkp` is in the `Project` folder.
