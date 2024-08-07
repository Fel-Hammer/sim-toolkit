import asyncio
import aiohttp
import json
import os
import re
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from tqdm import tqdm
import configparser
import tempfile
import shutil

class FileHandler:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def read_file(self, file_path: str) -> str:
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except FileNotFoundError as e:
            print(f"Error: File not found - {file_path}")
            raise e

    def write_file(self, file_path: str, content: str) -> None:
        try:
            with open(file_path, 'w') as f:
                f.write(content)
        except IOError as e:
            print(f"Error writing to file - {file_path}")
            raise e

    def combine_files(self, main_file: str, temp_file: str) -> str:
        try:
            combined_content = self.process_file(main_file)
            temp_combined_path = os.path.join(tempfile.gettempdir(), temp_file)
            self.write_file(temp_combined_path, combined_content)
            return temp_combined_path
        except Exception as e:
            print(f"An error occurred while combining files: {e}")
            raise e

    def process_file(self, file_path: str) -> str:
        try:
            lines = []
            content = self.read_file(file_path)
            for line in content.splitlines():
                if line.lower().startswith('# imports'):
                    continue
                if line.startswith('input='):
                    input_file = os.path.join(self.base_dir, line.split('=')[1].strip())
                    lines.append(self.process_file(input_file))
                    lines.append('\n')
                else:
                    lines.append(line)
            return '\n'.join(lines)
        except FileNotFoundError as e:
            print(f"Error: File not found - {file_path}")
            raise e

    def remove_temp_files(self, file_paths: List[str]) -> None:
        try:
            for file_path in file_paths:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"An error occurred while removing temp files: {e}")
            raise e

class Config:
    def __init__(self, config_path: str):
        self.parser = configparser.ConfigParser()
        self.parser.read(config_path)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        value = self.parser.get(section, key, fallback=fallback)
        if key in ['apl_folder', 'report_folder']:
            return os.path.join(self.project_root, value)
        return value

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        return self.parser.getboolean(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback: int = None) -> int:
        return self.parser.getint(section, key, fallback=fallback)

    def getfloat(self, section: str, key: str, fallback: float = None) -> float:
        return self.parser.getfloat(section, key, fallback=fallback)

class SimulationParameters:
    def __init__(self, iterations: int, time: int, fight_style: str, name: str, target_error: float, targets: int):
        self.iterations = iterations
        self.time = time
        self.fight_style = fight_style
        self.name = name
        self.target_error = target_error
        self.targets = targets

class RaidbotsSimulator:
    def __init__(self, config: Config, profiles: List[str], talent_strings: Dict[str, Dict[str, str]], report_folder: str, is_single_sim: bool):
        self.config = config
        self.profiles = profiles
        self.talent_strings = talent_strings
        self.report_folder = report_folder
        self.is_single_sim = is_single_sim
        self.api_key = config.get('General', 'raidbots_api_key')
        self.base_url = "https://www.raidbots.com"
        self.sim_url = f"{self.base_url}/sim"
        self.job_url = f"{self.base_url}/api/job"
        self.report_url = f"{self.base_url}/reports"

    async def compile_input(self, sim_params: SimulationParameters) -> str:
        # Read the base simulation content from the file
        with open(os.path.join(self.config.get('General', 'apl_folder'), 'full_character.simc'), 'r') as f:
            content = f.read()

        # Update or insert the simulation parameters in the content
        content = self._update_or_insert_param(content, 'iterations', sim_params.iterations)
        content = self._update_or_insert_param(content, 'max_time', sim_params.time)
        content = self._update_or_insert_param(content, 'fight_style', sim_params.fight_style)
        content = self._update_or_insert_param(content, 'target_error', sim_params.target_error)
        content = self._update_or_insert_param(content, 'desired_targets', sim_params.targets)

        # Update or insert talents if single simulation
        if self.is_single_sim:
            content = self._update_or_insert_param(content, 'talents', self.talent_strings['single_sim']['talents'])
        else:
            content += self._get_profilesets()
        return content

    def _update_or_insert_param(self, content: str, param: str, value: Any) -> str:
        pattern = re.compile(rf'^{param}=.*$', re.MULTILINE)
        replacement = f'{param}={value}'
        if pattern.search(content):
            content = pattern.sub(replacement, content)
        else:
            content = f'{replacement}\n' + content
        return content

    def _get_profilesets(self) -> str:
        profilesets = []
        for profile in self.profiles:
            hero_name, class_name, spec_name = [x.strip('$()') for x in profile.split('=')]
            profile_name = f"[{hero_name}] ({class_name}) - {spec_name}"
            profilesets.extend([
                f'profileset."{profile_name}"="hero_talents={self.talent_strings["hero_talents"].get(hero_name, "")}"',
                f'profileset."{profile_name}"+="class_talents={self.talent_strings["class_talents"].get(class_name, "")}"',
                f'profileset."{profile_name}"+="spec_talents={self.talent_strings["spec_talents"].get(spec_name, "")}"'
            ])
        return "\n".join(profilesets)

    async def submit_sim(self, session: aiohttp.ClientSession, input_content: str, sim_params: SimulationParameters) -> str:
        payload = {
            "type": "advanced",
            "apiKey": self.api_key,
            "advancedInput": input_content,
            "simcVersion": self.config.get('General', 'simc_version', fallback='nightly'),
            "reportName": f"{self.config.get('General', 'spec_name')} Simulation - {sim_params.name}",
            "smartHighPrecision": self.config.getboolean('Simulations', 'use_smart_mode', fallback=False),
            "operatingSystem": "macos",
            "origin": "api"
        }

        async with session.post(self.sim_url, json=payload, headers={"User-Agent": "FelhammerSims"}) as response:
            if response.status == 400:
                error_text = await response.text()
                raise ValueError(f"Raidbots API returned a 400 error. Response: {error_text[:100]}")
            response.raise_for_status()
            data = await response.json()
            return data['simId']

    async def check_sim_status(self, session: aiohttp.ClientSession, sim_id: str) -> Dict[str, Any]:
        async with session.get(f"{self.job_url}/{sim_id}", headers={"User-Agent": "FelhammerSims"}) as response:
            response.raise_for_status()
            data = await response.json()
            return {
                'state': data['job']['state'],
                'progress': data['job']['progress']
            }

    async def download_results(self, session: aiohttp.ClientSession, sim_id: str, output_path: str) -> None:
        async with session.get(f"{self.report_url}/{sim_id}/data.json", headers={"User-Agent": "FelhammerSims"}) as response:
            response.raise_for_status()
            data = await response.json()
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)

        full_output_path = output_path.replace('.json', '.full.json')
        async with session.get(f"{self.report_url}/{sim_id}/data.full.json", headers={"User-Agent": "FelhammerSims"}) as response:
            if response.status == 200:
                full_data = await response.json()
                with open(full_output_path, 'w') as f:
                    json.dump(full_data, f, indent=2)

    async def run_simulation(self, sim_params: SimulationParameters, output_path: str) -> None:
        async with aiohttp.ClientSession() as session:
            input_content = await self.compile_input(sim_params)

            sim_id = await self.submit_sim(session, input_content, sim_params)

            with tqdm(total=100, desc=f"Simulating {sim_params.name}", unit="%") as pbar:
                while True:
                    status = await self.check_sim_status(session, sim_id)
                    pbar.n = int(status['progress'])
                    pbar.refresh()

                    if status['state'] == 'complete':
                        break
                    elif status['state'] in ['failed', 'delayed']:
                        raise RuntimeError(f"Simulation failed: {status}")

                    await asyncio.sleep(5)

            await self.download_results(session, sim_id, output_path)
            print(f"Results downloaded: {output_path}")
            full_output_path = output_path.replace('.json', '.full.json')
            if os.path.exists(full_output_path):
                print(f"Full results downloaded: {full_output_path}")

def prepare_single_sim(config: Config) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    single_sim_talents = config.get('Simulations', 'single_sim_talents', fallback='')
    if not single_sim_talents:
        raise ValueError("Single sim talents not specified in config.")
    return ["Single Sim"], {"single_sim": {"talents": single_sim_talents}}

def prepare_multi_sim(config: Config) -> Tuple[List[str], Dict[str, Dict[str, str]], Dict[str, List[Tuple[str, str]]], Dict[str, Dict[str, str]]]:
    profiles_file = os.path.join(config.get('General', 'apl_folder'), 'profile_templates.simc')
    talents, talent_strings = parse_profiles_simc(profiles_file)

    filtered_talents = {
        category: filter_talents(
            list(talents[category].items()),
            config.get('TalentFilters', category, fallback='').split(),
            config.get('TalentFilters', f'{category}_exclude', fallback='').split(),
            category
        ) for category in ['hero_talents', 'class_talents', 'spec_talents']
    }

    if not any(filtered_talents.values()):
        raise ValueError("No valid profiles generated. Please check your talent selections.")

    profiles = [
        f"$({hero_name})=$({class_name})=$({spec_name})"
        for hero_name, _ in filtered_talents['hero_talents']
        for class_name, _ in filtered_talents['class_talents']
        for spec_name, _ in filtered_talents['spec_talents']
    ]

    return profiles, talents, filtered_talents, talent_strings

def create_full_character_simc(config: Config, file_handler: FileHandler):
    apl_folder = config.get('General', 'apl_folder')
    main_file = os.path.join(apl_folder, 'character.simc')
    output_file = os.path.join(apl_folder, 'full_character.simc')
    simc_path = config.get('General', 'simc')

    try:
        temp_combined_path = file_handler.combine_files(main_file, 'temp_combined.simc')

        # Read the combined content for printing
        combined_content = file_handler.read_file(temp_combined_path)

        command = [simc_path, temp_combined_path, f'save={output_file}']
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True)

        print(f"Successfully compiled and saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error running simc: {e}")
    except FileNotFoundError as e:
        print(f"Error: simc executable not found at {simc_path}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        file_handler.remove_temp_files([temp_combined_path])

def parse_profiles_simc(profiles_path: str) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    with open(profiles_path, 'r') as f:
        content = f.read()

    talents = {category: {} for category in ['hero_talents', 'class_talents', 'spec_talents']}
    talent_strings = {category: {} for category in ['hero_talents', 'class_talents', 'spec_talents']}

    sections = re.split(r'#\s*(Hero tree variants|Class tree variants|Spec tree variants)', content)

    if len(sections) != 7:
        raise ValueError(f"Unexpected number of sections in profile_templates.simc: {len(sections)}")

    for i, section_name in enumerate(['hero_talents', 'class_talents', 'spec_talents']):
        section_content = sections[i*2 + 2]
        talent_defs = re.findall(r'\$\(([\w_]+)\)="([^"]+)"', section_content)
        talents[section_name] = dict(talent_defs)
        talent_strings[section_name] = {name: string for name, string in talent_defs}

    return talents, talent_strings

def filter_talents(talents_items: List[Tuple[str, str]], include_list: List[str], exclude_list: List[str], talent_type: str = '') -> List[Tuple[str, str]]:
    talents = dict(talents_items)
    filtered_talents = []
    for talent_name, talent_content in talents.items():
        talent_abilities = set(ability.split(':')[0].lower() for ability in talent_content.split('/'))

        if 'all' in include_list:
            include = True
        elif talent_type == 'hero_talents':
            include = ('aldrachi' in include_list and 'art_of_the_glaive' in talent_content.lower()) or \
                      ('felscarred' in include_list and 'demonsurge' in talent_content.lower()) or \
                      any(term.lower() in ability for term in include_list for ability in talent_abilities)
        else:
            include = all(any(term.lower() in ability for ability in talent_abilities) for term in include_list)

        if include and exclude_list:
            include = not any(term.lower() in ability for term in exclude_list for ability in talent_abilities)

        if include:
            filtered_talents.append((talent_name, talent_content))

    return filtered_talents

def parse_simulations(config: Config, is_single_sim: bool) -> List[SimulationParameters]:
    iterations = config.getint('Simulations', 'iterations')
    target_error = config.getfloat('Simulations', 'target_error')
    default_targets = config.getint('Simulations', 'targets', fallback=1)
    default_time = config.getint('Simulations', 'time', fallback=300)

    def create_simulation_params(targets: int, time: int, fight_style: str, name: str) -> SimulationParameters:
        return SimulationParameters(
            iterations=iterations,
            target_error=target_error,
            time=time,
            fight_style=fight_style,
            name=name,
            targets=targets
        )

    default_simulation = create_simulation_params(default_targets, default_time, 'Patchwerk', f"{default_targets}T_{default_time}s")

    if is_single_sim:
        return [default_simulation]

    targettime = config.get('Simulations', 'targettime', '').strip()
    if not targettime:
        return [default_simulation]

    simulations = []
    for combo in targettime.split():
        if combo.lower() == 'dungeonslice':
            simulations.append(create_simulation_params(0, 0, 'DungeonSlice', 'DungeonSlice'))
        else:
            targets, time = map(int, combo.split(','))
            simulations.append(create_simulation_params(targets, time, 'Patchwerk', f"{targets}T_{time}s"))

    return simulations

async def run_simulations(config: Config, profiles: List[str], talent_strings: Dict[str, Dict[str, str]], report_folder: str, is_single_sim: bool, simulations: List[SimulationParameters]):
    simulator = RaidbotsSimulator(config=config, profiles=profiles, talent_strings=talent_strings, report_folder=report_folder, is_single_sim=is_single_sim)
    max_concurrent = config.getint('Simulations', 'max_concurrent', fallback=5)
    sem = asyncio.Semaphore(max_concurrent)

    async def run_sim_with_semaphore(sim_params: SimulationParameters) -> None:
        async with sem:
            output_filename = f"{sim_params.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            output_path = os.path.join(report_folder, output_filename)
            await simulator.run_simulation(sim_params, output_path)

    await asyncio.gather(*[run_sim_with_semaphore(sim) for sim in simulations])

async def main(config_path: str):
    config = Config(config_path)
    file_handler = FileHandler(base_dir=config.get('General', 'apl_folder'))
    report_folder = config.get('General', 'report_folder')
    is_single_sim = config.getboolean('Simulations', 'single_sim', fallback=False)

    try:
        os.makedirs(report_folder, exist_ok=True)
        create_full_character_simc(config, file_handler)

        if is_single_sim:
            profiles, talent_strings = prepare_single_sim(config)
            talents = {}
            filtered_talents = {}
        else:
            profiles, talents, filtered_talents, talent_strings = prepare_multi_sim(config)

        simulations = parse_simulations(config, is_single_sim)
        await run_simulations(config, profiles, talent_strings, report_folder, is_single_sim, simulations)

        if config.getboolean('PostProcessing', 'generate_website', fallback=False):
            # Implement website generation here
            pass

    except ValueError as e:
        print(f"Error: {e}")
        print("Please check your configuration file and ensure all required parameters are set correctly.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run SimulationCraft profiles using Raidbots API')
    parser.add_argument('config', help='Path to configuration file')
    args = parser.parse_args()
    asyncio.run(main(args.config))