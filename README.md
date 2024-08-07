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
- Create a config.ini file in the root directory
- Generate a list of profile templates or manual profilesets with talent strings and update `profile_templates.simc`
- (optional) Generate talent options with TTM
- (optional) Run `convert_TTM.py` to convert TTM talent strings to SimulationCraft profile templates
- (optional) Run `create_profiles.py` to generate profile templates for trinkets, enchants, gems, and consumables
- Run `generate_sims.py` to generate and run SimulationCraft profiles
- (optional) Run additional scripts by adding options to your `config.ini` file

## Configuration File (config.ini)
```ini
[General]
spec_name = Vengeance
simc = ../simc/engine/simc
apl_folder = vengeance
report_folder = reports
timestamp = false
html_output = false
json_output = true
clear_cache = false

[Simulations]
single_sim = false
targettime = 1,300 5,60 5,120 10,60 10,120
target_error = 0.3
iterations=10000
; targets = 1
; time = 300

[PostProcessing]
supplemental_profilesets = true
generate_combined_apl = true
generate_website = true

[TalentFilters]
hero_talents = all
hero_talents_exclude =
class_talents = all
class_talents_exclude =
spec_talents = all
spec_talents_exclude =
```