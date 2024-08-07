import os
import re
import json
import sys
import configparser
from collections import defaultdict
from typing import Dict, List, Union

# Get the path to the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
# Get the path to the root directory (one level up)
root_dir = os.path.dirname(script_dir)

def read_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'General' not in config:
        raise ValueError("Config file is missing the [General] section")

    if 'spec_name' not in config['General']:
        raise ValueError("Config file is missing the 'spec_name' setting in the [General] section")

    return config['General']

def extract_chart_data(file_path: str) -> Dict[str, Dict[str, Union[float, str]]]:
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    chart_data = {}
    profilesets = data.get('sim', {}).get('profilesets', {}).get('results', [])

    if not profilesets:
        print(f"Warning: No profilesets found in {file_path}")

    for profile in profilesets:
        name = profile.get('name', '')
        dps = profile.get('mean', 0)
        talent_hash = profile.get('talent_hash', '')  # Extract talent hash here

        if dps == 0:
            print(f"Warning: No DPS data found for profile {name} in {file_path}")

        chart_data[name] = {'dps': dps, 'talent_hash': talent_hash}
    return chart_data

def extract_filename_info(filename: str) -> str:
    if 'dungeonslice' in filename.lower():
        return "D. Slice"
    match = re.search(r'(\d+)T_(\d+)s', filename)
    return f"{match.group(1)}T {match.group(2)}s" if match else ""

def parse_build_name(build_name: str) -> Dict[str, str]:
    hero_match = re.search(r'\[(.*?)\]', build_name)
    class_match = re.search(r'\((.*?)\)', build_name)
    spec_match = build_name.split('-')[-1] if '-' in build_name else ''

    spec_talents = spec_match.split('__') if '__' in spec_match else [spec_match, '']
    offensive_talents = spec_talents[0].strip().split('_') if spec_talents[0] else []
    defensive_talents = spec_talents[1].split('_') if len(spec_talents) > 1 else []

    return {
        'hero_talent': hero_match.group(1) if hero_match else "",
        'class_talents': class_match.group(1).split('_') if class_match else [],
        'offensive_talents': offensive_talents,
        'defensive_talents': defensive_talents,
        'full_name': build_name
    }

def collect_data(spec_name, report_folder):
    data = defaultdict(lambda: defaultdict(dict))
    report_types = set()

    reports_dir = os.path.join(root_dir, report_folder)

    if not os.path.exists(reports_dir):
        print(f"Error: Reports directory not found at {reports_dir}")
        return dict(data), []

    json_files = [f for f in os.listdir(reports_dir) if f.endswith('.json') and ('all' in f.lower() or 'dungeonslice' in f.lower())]

    if not json_files:
        print(f"Error: No JSON files for ALL talents found in the reports directory at {reports_dir}")
        return dict(data), []

    for filename in json_files:
        file_path = os.path.join(reports_dir, filename)
        report_type = extract_filename_info(filename)
        if report_type:
            report_types.add(report_type)
            chart_data = extract_chart_data(file_path)
            for build_name, build_data in chart_data.items():
                build_info = parse_build_name(build_name)
                data[build_info['full_name']][report_type] = build_data['dps']
                data[build_info['full_name']]['talent_hash'] = build_data['talent_hash']
                data[build_info['full_name']].update(build_info)

    if not data:
        print(f"Warning: No valid data extracted from JSON files in {reports_dir}")

    def sort_key(x):
        if x == "D. Slice":
            return (float('inf'), float('inf'))  # Place D. Slice at the end
        return tuple(map(int, x.replace('T', ' ').replace('s', '').split()))

    return dict(data), sorted(report_types, key=sort_key)

def calculate_overall_rank(data: Dict[str, Dict[str, Dict]], report_types: List[str]) -> Dict[str, int]:
    overall_scores = {build: sum(build_data.get(rt, 0) for rt in report_types) / len(report_types)
                      for build, build_data in data.items()}
    sorted_builds = sorted(overall_scores.items(), key=lambda x: x[1], reverse=True)
    return {build: rank + 1 for rank, (build, _) in enumerate(sorted_builds)}

def format_build_name(build: str) -> str:
    parts = build.split('-')
    hero_talent = re.search(r'\[(.*?)\]', parts[0]).group(1)
    class_talents = re.search(r'\((.*?)\)', parts[0]).group(1).replace('_', '/')
    spec_talents = parts[1].split('__')
    offensive_talents = spec_talents[0].replace('_', '/')
    defensive_talents = spec_talents[1].replace('_', '/') if len(spec_talents) > 1 else ''
    return f"{hero_talent} | {class_talents} | {offensive_talents} | {defensive_talents}"

def generate_html(data: Dict[str, Dict[str, Dict]], report_types: List[str], spec_name: str) -> str:
    overall_ranks = calculate_overall_rank(data, report_types)

    # Count the frequency of each talent
    talent_counts = {
        'hero_talent': defaultdict(int),
        'class_talents': defaultdict(int),
        'offensive_talents': defaultdict(int),
        'defensive_talents': defaultdict(int)
    }
    total_profiles = len(data)

    for build_data in data.values():
        talent_counts['hero_talent'][build_data['hero_talent']] += 1
        for talent in build_data['class_talents']:
            talent_counts['class_talents'][talent] += 1
        for talent in build_data['offensive_talents']:
            talent_counts['offensive_talents'][talent] += 1
        for talent in build_data['defensive_talents']:
            talent_counts['defensive_talents'][talent] += 1

    # Filter out talents that appear in every profile
    filtered_talents = {
        'heroTalent': [talent for talent, count in talent_counts['hero_talent'].items() if count < total_profiles],
        'classTalents': [talent for talent, count in talent_counts['class_talents'].items() if count < total_profiles],
        'offensiveTalents': [talent for talent, count in talent_counts['offensive_talents'].items() if count < total_profiles],
        'defensiveTalents': [talent for talent, count in talent_counts['defensive_talents'].items() if count < total_profiles]
    }

    json_data = [{
        'build': format_build_name(build),
        'hero_talent': build_data['hero_talent'],
        'class_talents': build_data['class_talents'],
        'offensive_talents': build_data['offensive_talents'],
        'defensive_talents': build_data['defensive_talents'],
        'talent_hash': build_data['talent_hash'],
        'overall_rank': overall_ranks[build],
        'metrics': {rt: round(build_data.get(rt, 0), 2) for rt in report_types}
    } for build, build_data in data.items()]

    json_data.sort(key=lambda x: x['overall_rank'])

    st_report = min((rt for rt in report_types if rt != "D. Slice"), key=lambda x: int(x.split('T')[0]))
    aoe_report = max((rt for rt in report_types if rt != "D. Slice"), key=lambda x: int(x.split('T')[0]))
    top_st = max(json_data, key=lambda x: x['metrics'][st_report])
    top_aoe = max(json_data, key=lambda x: x['metrics'][aoe_report])


    table_headers = ''.join([f'<th class="mdc-data-table__header-cell" role="columnheader" scope="col" onclick="sortTable({i+2})">{rt} <i class="material-icons sort-icon">arrow_downward</i></th>' for i, rt in enumerate(report_types)])

    template_path = os.path.join(root_dir, 'template.html')
    styles_path = os.path.join(root_dir, 'styles.css')
    script_path = os.path.join(root_dir, 'script.js')

    with open(template_path, 'r', encoding='utf-8') as f:
        html_template = f.read()

    html_template = html_template.replace('$TITLE', f'{spec_name} Demon Hunter Simulations')

    with open(styles_path, 'r', encoding='utf-8') as f:
        css_content = f.read()

    with open(script_path, 'r', encoding='utf-8') as f:
        js_content = f.read()

    json_data_str = json.dumps(json_data)
    filtered_talents_str = json.dumps(filtered_talents)
    if not json_data_str or json_data_str == '[]':
        print("Warning: json_data is empty or invalid")

    js_with_data = f"""
    // Data injected by Python script
    const rawData = {json_data_str};
    const reportTypes = {json.dumps(report_types)};
    const filteredTalents = {filtered_talents_str};

    {js_content}
    """

    html = html_template.replace('$STYLES', css_content)
    html = html.replace('$SCRIPT', js_with_data)
    html = html.replace('$TABLE_HEADERS', table_headers)

    return html

def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_reports.py <config_file>")
        sys.exit(1)

    config_path = sys.argv[1]

    try:
        config = read_config(config_path)
        spec_name = config['spec_name']
        report_folder = config['report_folder']

        print(f"Generating report for {spec_name} spec")

        data, report_types = collect_data(spec_name, report_folder)
        if not data or not report_types:
            print(f"Error: No data or report types found for {spec_name}. Make sure the '{report_folder}' folder exists and contains valid JSON files.")
            return

        html = generate_html(data, report_types, spec_name)  # Pass spec_name here

        output_folder = os.path.join(root_dir, f'website_{spec_name.lower()}')
        os.makedirs(output_folder, exist_ok=True)

        output_path = os.path.join(output_folder, f'{spec_name.lower()}.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"Report generated for {spec_name} spec at {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please make sure the config file exists at the specified path.")
    except ValueError as e:
        print(f"Error in config file: {e}")
        print("Please check the contents of your config file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()