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

## Usage
- Create a config.ini file in the root directory, specifying options
- (optional) Generate talent options with TTM
- (optional) Run `convert_TTM.py` to convert TTM talent strings to SimulationCraft profile templates
- Generate a list of profile templates or manual profilesets with talent strings and update `profile_templates.simc`
- Run `generate_sims.py` to generate and run SimulationCraft profiles

## Configuration File (config.ini)
```ini
[General]
spec_name = Vengeance
simc = ../simc/engine/simc
apl_folder = vengeance
report_folder = reports_vengeance
timestamp = false
html_output = false
json_output = true
clear_cache = false
debug = false

[Simulations]
talents = CUkAEDLOxe3SEPP2R8Hw6bhoSAAGjZmZMMjMzMGDjZbmBjtZMjZMzYMz2MzsNzMMDGAAAAmlZWmlZmZW2mlppZwMzgF
single_sim = true
; multi_sim = 1,300 5,120 10,120
iterations = 5000
target_error = 0.5

[PostProcessing]
supplemental_profilesets = false
generate_combined_apl = true
generate_website = false
```