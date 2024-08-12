# Fel Hammer Simulation Toolkit
This toolkit generates and runs SimulationCraft profiles for World of Warcraft character optimization.

## Scripts
- `generate_sims.py`: Generates and runs SimulationCraft profiles
- `combine.py`: Combines and compiles SimulationCraft APLs into a compiled file
- `compare_reports.py`: Compares simulation results and generates a web report
- `convert_TTM.py`: Converts Talent Tree Manager (TTM) talent strings to SimulationCraft profile templates
- `filter_items_enchants.py`: Fetches and filters data from Raidbots to generate a list of items and enchants for Demon Hunters
- `create_profiles.py`: Generates profile templates from item data (`filter_items_enchants.py`)
- `talenthasher.py`: Generates talent hashes from profile templates
- `download-simc.py`: Download the latest SimulationCraft CLI

## Usage
- Create a config.ini file in the root directory, specifying options
- (optional) Generate talent options with TTM
- (optional) Run `convert_TTM.py` to convert TTM talent strings to SimulationCraft profile templates
- Generate a list of profile templates or manual profilesets with talent strings and update `profile_templates.simc`
- Run `generate_sims.py` to generate and run SimulationCraft profiles

## Configuration File (config.ini)
```ini
[General]
spec_name = Vengeance ; Havoc, Vengeance
simc = ../simc/engine/simc ; (optional) Path to SimulationCraft CLI, will download latest version if not specified
apl_folder = vengeance ; Path to APL folder, will create if not specified
report_folder = reports_vengeance ; Path to report folder, will create if not specified
timestamp = false ; Add timestamp to report filenames
html_output = false ; Generate HTML reports
json_output = true ; Generate JSON reports
clear_cache = false ; Clear all caches (talents, items, etc.) before simulating
debug = false ; Enable debug output

[Simulations]
talents = CUkAEDLOxe3SEPP2R8Hw6bhoSAAGjZmZMMjMzMGDjZbmBjtZMjZMzYMz2MzsNzMMDGAAAAmlZWmlZmZW2mlppZwMzgF ; Specific talent string to use as default
single_sim = true ; Run a single simulation
multi_sim = 1,300 5,120 10,120 ; Run multiple simulations with different target,time pairs
iterations = 5000 ; Number of iterations to run for each simulation
target_error = 0.5 ; Target error for each simulation

[PostProcessing]
supplemental_profilesets = false ; Generate supplemental profile sets (trinkets, gems, etc.)
generate_combined_apl = true ; Generate a combined APL file
```