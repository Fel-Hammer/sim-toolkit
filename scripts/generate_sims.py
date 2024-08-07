import argparse
import configparser
import tempfile
import os
import pickle
import re
import subprocess
import sys
import time
import json
import threading
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import multiprocessing
from collections.abc import Iterable
from talenthasher import generate_talent_hash, initialize_talent_data
from tqdm import tqdm
from dataclasses import dataclass
import logging
from typing import List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Global constants
CACHE_FILE = os.path.join(os.path.dirname(__file__), "talent_hash_cache.pkl")

@dataclass
class SimulationParameters:
    iterations: int
    target_error: float
    targets: Optional[int] = None
    time: Optional[int] = None
    fight_style: Optional[str] = None

class Config:
    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.config_path = os.path.abspath(config_path)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)
        self.spec_name = self.get('General', 'spec_name', 'Vengeance')  # Default to Vengeance

    def get(self, section, key, fallback=None):
        value = self.config.get(section, key, fallback=fallback)
        if key in ['apl_folder', 'report_folder']:
            return os.path.join(self.project_root, value)
        return value

    def getboolean(self, section, key, fallback=False):
        return self.config.getboolean(section, key, fallback=fallback)

    def getint(self, section, key, fallback=None):
        return self.config.getint(section, key, fallback=fallback)

    def getfloat(self, section, key, fallback=None):
        return self.config.getfloat(section, key, fallback=fallback)

class TalentHashManager:
    def __init__(self, config):
        self.spec_name = config.spec_name.lower()
        self.clear_cache = config.getboolean('General', 'clear_cache', fallback=False)
        self.persistent_cache = self.load_cache()
        self.cache_lock = threading.Lock()

        # Preload talent data
        initialize_talent_data(force_new=self.clear_cache)

    @staticmethod
    def load_cache():
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except:
                logger.error("Error loading talent hash cache. Generating new cache.")
        return {}

    def save_cache(self):
        with self.cache_lock:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.persistent_cache, f)

    @lru_cache(maxsize=10000)
    def get_hash(self, hero_talent, class_talent, spec_talent):
        hash_key = f"{hero_talent}_{class_talent}_{spec_talent}"
        with self.cache_lock:
            if self.clear_cache or hash_key not in self.persistent_cache:
                talent_hash = generate_talent_hash(
                    hero_talent, class_talent, spec_talent, self.spec_name,
                    clear_cache=False, force_new=False
                )
                self.persistent_cache[hash_key] = talent_hash
        return self.persistent_cache[hash_key]

    def get_hashes_batch(self, talent_combinations):
        total_combinations = len(talent_combinations)
        with ThreadPoolExecutor() as executor:
            results = list(tqdm(
                executor.map(lambda x: self.get_hash(*x), talent_combinations),
                total=total_combinations,
                desc="Generating talent hashes",
                unit="hash"
            ))
        self.save_cache()  # Save the cache after all hashes have been generated
        return results

class ProgressTracker:
    def __init__(self, total_simulations, estimated_profiles_per_sim=None):
        self.total_simulations = total_simulations
        self.estimated_profiles_per_sim = estimated_profiles_per_sim
        self.current_simulation = 1
        self.total_profiles = 0
        self.completed_profiles = 0
        self.avg_profile_time = 0
        self.start_time = time.time()
        self.last_update_time = 0
        self.pbar = tqdm(total=100, bar_format='{l_bar}{bar}| {elapsed} {postfix}]')

    def update(self, line):
        current_time = time.time()
        if current_time - self.last_update_time < 0.25:  # Limit updates to 4 times per second
            return
        self.last_update_time = current_time

        if "Profilesets" in line:
            self._process_batch_sim(line)
        elif "Generating" in line:
            self._process_single_sim(line)

    def _process_batch_sim(self, line):
        match = re.search(r'Profilesets \((\d+\*\d+)\): (\d+)/(\d+) \[.*?\] avg=([\d.]+)ms', line)
        if match:
            _, current, total, avg_time = match.groups()
            self.total_profiles = int(total)
            self.completed_profiles = int(current)
            self.avg_profile_time = float(avg_time) / 1000  # Convert to seconds

            self._update_progress()

    def _process_single_sim(self, line):
        match = re.search(r'Generating .*?: .* (\d+)/(\d+) \[.*?\] (\d+)/(\d+) ([\d.]+)', line)
        if match:
            current, total, _, _, sim_time = match.groups()
            self.total_profiles = int(total)
            self.completed_profiles = int(current)
            self.avg_profile_time = float(sim_time)

            self._update_progress()

    def _update_progress(self):
        if self.estimated_profiles_per_sim:
            total_estimated_profiles = self.total_simulations * self.estimated_profiles_per_sim
            overall_completed = ((self.current_simulation - 1) * self.estimated_profiles_per_sim) + self.completed_profiles
            progress = (overall_completed / total_estimated_profiles) * 100
        else:
            progress = (self.completed_profiles / self.total_profiles) * 100 if self.total_profiles else 0

        self.pbar.n = progress
        self.pbar.refresh()

        elapsed_time = time.time() - self.start_time
        if progress > 0:
            estimated_total_time = elapsed_time / (progress / 100)
            remaining_time = estimated_total_time - elapsed_time
            remaining_time_str = self.format_time(remaining_time)
        else:
            remaining_time_str = "Unknown"

        self.pbar.set_postfix({
            'Sim': f"{self.current_simulation}/{self.total_simulations}",
            'Profiles': f"{self.completed_profiles}/{self.total_profiles or self.estimated_profiles_per_sim or '?'}",
            'Avg': f"{self.avg_profile_time:.2f}s",
            'ETA': remaining_time_str
        })

    def format_time(self, seconds):
        """Convert seconds to a human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"

    def start_new_simulation(self):
        self.current_simulation += 1
        self.completed_profiles = 0
        self.total_profiles = 0
        self.avg_profile_time = 0
        self.start_time = time.time()
        self.pbar.reset()

    def close(self):
        self.pbar.close()

class FileHandler:
    @staticmethod
    def ensure_directory(directory):
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                logger.info(f"Created output directory: {directory}")
            except OSError as e:
                logger.error(f"Error creating output directory {directory}: {e}")
                return False
        return True

    @staticmethod
    def read_file(file_path):
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except IOError as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None

    @staticmethod
    def write_file(file_path, content):
        try:
            with open(file_path, 'w') as f:
                f.write(content)
            return True
        except IOError as e:
            logger.error(f"Error writing to file {file_path}: {e}")
            return False

    @staticmethod
    def create_temp_file(content, prefix='temp_', suffix='.simc', dir=None):
        try:
            with tempfile.NamedTemporaryFile(mode='w', prefix=prefix, suffix=suffix, dir=dir, delete=False) as temp_file:
                temp_file.write(content)
                return temp_file.name
        except IOError as e:
            logger.error(f"Error creating temporary file: {e}")
            return None

    @staticmethod
    def delete_file(file_path):
        try:
            os.remove(file_path)
            logger.debug(f"File {file_path} deleted successfully.")
        except OSError as e:
            logger.error(f"Error deleting file {file_path}: {e}")

    @staticmethod
    def safe_delete(file_path):
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Temporary file {file_path} deleted successfully.")
            except OSError as e:
                logger.error(f"Error deleting temporary file {file_path}: {e}")

class SimulationRunner:
    def __init__(self, config, talent_hash_manager, talent_strings):
        self.config = config
        self.talent_hash_manager = talent_hash_manager
        self.talent_strings = talent_strings
        self.character_content = self.load_character_simc()
        self.profiles_content = self.load_profiles_simc()

        # Compile frequently used regex patterns
        self.targets_pattern = re.compile(r'desired_targets=\d+')
        self.time_pattern = re.compile(r'max_time=\d+')
        self.iterations_pattern = re.compile(r'iterations=\d+')
        self.target_error_pattern = re.compile(r'target_error=[\d.]+')
        self.json_pattern = re.compile(r'json2=.*')
        self.html_pattern = re.compile(r'html=.*')
        self.threads_pattern = re.compile(r'threads=\d+')
        self.profileset_work_threads_pattern = re.compile(r'profileset_work_threads=\d+')
        self.talents_pattern = re.compile(r'talents=.*')

    def load_character_simc(self) -> str:
        return FileHandler.read_file(os.path.join(self.config.get('General', 'apl_folder'), 'character.simc'))

    def load_profiles_simc(self) -> str:
        return FileHandler.read_file(os.path.join(self.config.get('General', 'apl_folder'), 'profile_templates.simc'))

    def run_simulation(self, sim_params, profiles: List[str], output_path: str, progress_tracker):
        single_sim = self.config.getboolean('Simulations', 'single_sim', fallback=False)
        temp_file_path = None
        try:
            temp_file_path = self.create_simc_file(sim_params, profiles, output_path, single_sim)
            if not temp_file_path:
                logger.error("Failed to create temporary SimC input file.")
                return None

            results = self.run_simc(temp_file_path, output_path, progress_tracker)

            if results and self.config.getboolean('General', 'json_output', fallback=False):
                json_path = output_path.replace('.html', '.json')
                if os.path.exists(json_path):
                    self.update_json_with_hashes(json_path)

            return results
        finally:
            FileHandler.safe_delete(temp_file_path)

    def create_simc_file(self, sim_params, profiles: List[str], output_path: str, single_sim: bool) -> str:
        talents = self.config.get('Simulations', 'single_sim_talents') if single_sim else None
        updated_content = self.update_simc_content(self.character_content, sim_params, talents)

        if single_sim:
            content = updated_content
        else:
            used_templates = set(re.findall(r'\$\(([\w_]+)\)', '\n'.join(profiles)))
            filtered_profiles_content = [line for line in self.profiles_content.split('\n') if any(f'$({template})' in line for template in used_templates)]
            content = f"{updated_content}\n\n" + "\n".join(filtered_profiles_content) + "\n\n" + "\n\n".join(profiles)

        return FileHandler.create_temp_file(content, prefix="temp_simc_input_", dir=self.config.get('General', 'apl_folder'))

    def update_simc_content(self, content: str, sim_params: SimulationParameters, talents: str = None) -> str:
        # Split the content into sections
        sections = re.split(r'\n\s*\n', content)

        # Find the SimC configuration section
        simc_config_index = next((i for i, section in enumerate(sections) if section.strip().startswith("# SimC configuration")), None)
        if simc_config_index is None:
            # If SimC configuration section doesn't exist, create it
            simc_config = "# SimC configuration\n"
            sections.insert(0, simc_config)
            simc_config_index = 0

        # Update SimC configuration
        simc_config = sections[simc_config_index]
        simc_config = self._update_property(simc_config, "iterations", str(sim_params.iterations))
        simc_config = self._update_property(simc_config, "target_error", str(sim_params.target_error))

        if sim_params.fight_style == 'DungeonSlice':
            simc_config = self._update_property(simc_config, "fight_style", "DungeonSlice")
            # Remove desired_targets and max_time for DungeonSlice
            simc_config = re.sub(r'desired_targets=\d+\n', '', simc_config)
            simc_config = re.sub(r'max_time=\d+\n', '', simc_config)
        else:
            simc_config = self._update_property(simc_config, "desired_targets", str(sim_params.targets))
            simc_config = self._update_property(simc_config, "max_time", str(sim_params.time))

        if sim_params.iterations is not None:
            simc_config = self._update_property(simc_config, "iterations", str(sim_params.iterations))

        if sim_params.target_error is not None:
            simc_config = self._update_property(simc_config, "target_error", str(sim_params.target_error))

        # Add threads and profileset_work_threads for non-single simulations
        if not self.config.getboolean('Simulations', 'single_sim', fallback=False):
            cpu_threads = multiprocessing.cpu_count()
            simc_config = self._update_property(simc_config, "threads", str(cpu_threads))
            simc_config = self._update_property(simc_config, "profileset_work_threads", str(max(1, cpu_threads // 4)))

        sections[simc_config_index] = simc_config

        # Update talents if provided
        if talents:
            character_config_index = next((i for i, section in enumerate(sections) if section.strip().startswith("# Character configuration")), None)
            if character_config_index is not None:
                character_config = sections[character_config_index]
                character_config = self._update_property(character_config, "talents", talents)
                sections[character_config_index] = character_config
            else:
                # If Character configuration section doesn't exist, create it
                character_config = f"# Character configuration\ntalents={talents}\n"
                sections.append(character_config)

        # Join the sections back together
        return "\n\n".join(sections)

    @staticmethod
    def _update_property(content: str, property_name: str, value: str) -> str:
        pattern = re.compile(f"^{property_name}=.*$", re.MULTILINE)
        replacement = f"{property_name}={value}"
        if pattern.search(content):
            return pattern.sub(replacement, content)
        else:
            return f"{content}\n{replacement}"

    def update_character_simc(self, content: str, sim_params, output_path: str, single_sim: bool) -> str:
        # Split the content into sections
        sections = re.split(r'\n\s*\n', content)

        # Find the SimC configuration section
        simc_config_index = next((i for i, section in enumerate(sections) if "SimC configuration" in section), None)

        if simc_config_index is not None:
            simc_config = sections[simc_config_index]

            # Update basic simulation parameters
            simc_config = self.targets_pattern.sub(f'desired_targets={sim_params.targets}', simc_config)
            simc_config = self.time_pattern.sub(f'max_time={sim_params.time}', simc_config)

            if sim_params.iterations is not None:
                simc_config = self.iterations_pattern.sub(f'iterations={sim_params.iterations}', simc_config)
                if 'iterations=' not in simc_config:
                    simc_config += f'\niterations={sim_params.iterations}'
            if sim_params.target_error is not None:
                simc_config = self.target_error_pattern.sub(f'target_error={sim_params.target_error}', simc_config)
                if 'target_error=' not in simc_config:
                    simc_config += f'\ntarget_error={sim_params.target_error}'

            if self.config.getboolean('General', 'json_output', fallback=False):
                json_file = output_path.replace('.html', '.json')
                simc_config = self.json_pattern.sub(f'json2={json_file}', simc_config)
            if self.config.getboolean('General', 'html_output', fallback=True):
                simc_config = self.html_pattern.sub(f'html={output_path}', simc_config)

            # Handle threads and profileset_work_threads
            if single_sim:
                # Remove threads and profileset_work_threads lines for single sim
                simc_config = self.threads_pattern.sub('', simc_config)
                simc_config = self.profileset_work_threads_pattern.sub('', simc_config)
            else:
                # Ensure threads and profileset_work_threads lines are present for non-single sim
                # Automatically determine the number of CPU threads
                cpu_threads = multiprocessing.cpu_count()
                if 'threads=' not in simc_config:
                    simc_config += f'\nthreads={cpu_threads}'
                if 'profileset_work_threads=' not in simc_config:
                    simc_config += f'\nprofileset_work_threads={max(1, cpu_threads // 4)}'

            # Update the section in the original content
            sections[simc_config_index] = simc_config
        else:
            # If SimC configuration section doesn't exist, create it
            simc_config = f"# SimC configuration\ndesired_targets={sim_params.targets}\nmax_time={sim_params.time}\n"
            if sim_params.iterations is not None:
                simc_config += f"iterations={sim_params.iterations}\n"
            if sim_params.target_error is not None:
                simc_config += f"target_error={sim_params.target_error}\n"
            if self.config.getboolean('General', 'json_output', fallback=False):
                json_file = output_path.replace('.html', '.json')
                simc_config += f"json2={json_file}\n"
            if self.config.getboolean('General', 'html_output', fallback=True):
                simc_config += f"html={output_path}\n"
            if not single_sim:
                simc_config += "threads=12\nprofileset_work_threads=3\n"
            sections.insert(0, simc_config)

        # Handle single_sim_talents
        if single_sim:
            single_sim_talents = self.config.get('Simulations', 'single_sim_talents')
            if single_sim_talents:
                for i, section in enumerate(sections):
                    if section.strip().startswith("talents="):
                        sections[i] = f"talents={single_sim_talents}"
                        break
                else:
                    # If no talents line found, add it to the end
                    sections.append(f"talents={single_sim_talents}")

        # Join the sections back together
        return "\n\n".join(sections)

    def run_simc(self, simc_file: str, output_path: str, progress_tracker) -> tuple[Optional[str], bool]:
        simc_path = self.config.get('General', 'simc')
        simc_path, simc_file = map(os.path.abspath, [simc_path, simc_file])
        output_path = os.path.abspath(output_path)
        output_dir = os.path.dirname(output_path)
        simc_dir = os.path.dirname(simc_file)
        original_dir = os.getcwd()
        os.chdir(simc_dir)

        if not os.access(output_dir, os.W_OK):
            logger.error(f"No write permission in the output directory: {output_dir}")
            return None, False

        if not os.path.exists(simc_path):
            logger.error(f"SimC executable not found at {simc_path}")
            return None, False

        command = [simc_path, os.path.basename(simc_file)]

        if self.config.getboolean('General', 'html_output', fallback=True):
            command.append(f'html={output_path}')
        if self.config.getboolean('General', 'json_output', fallback=False):
            json_file = output_path.replace('.html', '.json')
            command.append(f'json2={json_file}')

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)

        for line in iter(process.stdout.readline, ''):
            progress_tracker.update(line)

        stdout, stderr = process.communicate()

        rc = process.returncode
        if rc != 0:
            logger.error(f"SimC process exited with return code {rc}")
            logger.error(f"SimC stderr output: {stderr}")
            return None, False

        os.chdir(original_dir)
        return "SimC completed successfully", False

    def update_json_with_hashes(self, json_file: str):
        # logger.info(f"Updating JSON with hashes: {json_file}")
        with open(json_file, 'r') as f:
            data = json.load(f)

        def extract_names(profile_name: str) -> tuple:
            match = re.match(r'\[(.*?)\] \((.*?)\) - (.*)', profile_name)
            if match:
                return match.groups()
            parts = re.split(r'[\[\](),-]', profile_name)
            parts = [part.strip() for part in parts if part.strip()]
            if len(parts) >= 3:
                return parts[0], parts[1], parts[2]
            return None, None, None

        if 'sim' in data and 'profilesets' in data['sim']:
            for result in data['sim']['profilesets']['results']:
                profile_name = result['name']

                # Check if this is a supplemental profile
                if any(profile_name.startswith(prefix) for prefix in ['Trinket_', 'Gem_', 'Enchant_', 'Weapons_']):
                    # For supplemental profiles, skip hash generation
                    result['talent_hash'] = "N/A"
                    continue

                hero_name, class_name, spec_name = extract_names(profile_name)
                if hero_name and class_name and spec_name:
                    hero_talents = self.talent_strings['hero_talents'].get(hero_name, "")
                    class_talents = self.talent_strings['class_talents'].get(class_name, "")
                    spec_talents = self.talent_strings['spec_talents'].get(spec_name, "")
                    result['talent_hash'] = self.talent_hash_manager.get_hash(hero_talents, class_talents, spec_talents)
                else:
                    logger.warning(f"Could not parse profile name: {profile_name}")
                    result['talent_hash'] = "unknown_hash"

        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2)

def parse_profiles_simc(profiles_path, talent_hash_manager):
    content = FileHandler.read_file(profiles_path)
    if content is None:
        return None

    talents = {category: {} for category in ['hero_talents', 'class_talents', 'spec_talents']}
    talent_strings = {}  # New dictionary to store full talent strings
    sections = re.split(r'#\s*(Hero tree variants|Class tree variants|Spec tree variants)', content)

    if len(sections) != 7:
        raise ValueError(f"Unexpected number of sections in profile_templates.simc: {len(sections)}")

    for i, section_name in enumerate(['hero_talents', 'class_talents', 'spec_talents']):
        section_content = sections[i*2 + 2]
        talent_defs = re.findall(r'\$\(([\w_]+)\)="([^"]+)"', section_content)
        talents[section_name] = dict(talent_defs)
        talent_strings[section_name] = {name: string for name, string in talent_defs}

    combinations = [
        (hero_talent, class_talent, spec_talent)
        for hero_name, hero_talent in talents['hero_talents'].items()
        for class_name, class_talent in talents['class_talents'].items()
        for spec_name, spec_talent in talents['spec_talents'].items()
    ]

    print("Generating talent hashes...")
    talent_hash_manager.get_hashes_batch(combinations)
    print("Talent hash generation completed.")

    return talents, talent_strings

def filter_talents(talents_items, include_list, exclude_list, talent_type=''):
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

def generate_simc_profile(hero_name, class_name, spec_name, talent_strings):
    formatted_name = f"[{hero_name}] ({class_name}) - {spec_name}"
    # Fetch the talent strings directly from the stored data
    hero_talents = talent_strings['hero_talents'].get(hero_name, "")
    class_talents = talent_strings['class_talents'].get(class_name, "")
    spec_talents = talent_strings['spec_talents'].get(spec_name, "")
    return '\n'.join([
        f'profileset."{formatted_name}"="hero_talents={hero_talents}"',
        f'profileset."{formatted_name}"+="class_talents={class_talents}"',
        f'profileset."{formatted_name}"+="spec_talents={spec_talents}"'
    ])

def generate_output_filename(config, sim_params):
    if config.getboolean('Simulations', 'single_sim', fallback=False):
        if sim_params.fight_style == 'DungeonSlice':
            filename = "simc_single_dungeonslice"
        else:
            filename = f"simc_single_{sim_params.targets}T_{sim_params.time}sec"
    else:
        hero_talent = next(iter(config.get('TalentFilters', 'hero_talents').split())) if config.get('TalentFilters', 'hero_talents') != 'all' else 'all'
        if sim_params.fight_style == 'DungeonSlice':
            filename = f"simc_{hero_talent}_dungeonslice"
        else:
            filename = f"simc_{hero_talent}_{sim_params.targets}T_{sim_params.time}sec"

    if config.getboolean('General', 'timestamp', fallback=False):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{timestamp}"

    return f"{filename}.html"

def print_summary(talents, filtered_talents, profiles, config, simulations):
    print("\nSimulation Summary:")
    print("===================")

    print("\nSimulation Parameters:")
    if len(simulations) == 1:
        sim_params = simulations[0]
        print(f"  Targets: {sim_params.targets}")
        print(f"  Time: {sim_params.time} seconds")
    else:
        print("  Multiple simulations:")
        for i, sim_params in enumerate(simulations, 1):
            print(f"    Sim {i}: {sim_params.targets} target(s), {sim_params.time} seconds")

    iterations = config.get('Simulations', 'iterations')
    if iterations:
        print(f"  Iterations: {iterations}")

    target_error = config.get('Simulations', 'target_error')
    if target_error:
        print(f"  Target Error: {target_error}")

    if config.getboolean('Simulations', 'single_sim', fallback=False):
        print("\nSingle Sim Mode:")
        print(f"  Talent String: {config.get('Simulations', 'single_sim_talents')}")
    else:
        print("\nDetected Templates:")
        for category, talent_list in talents.items():
            print(f"  {category.capitalize()}: {len(talent_list)}")

        print("\nFilter Summary:")
        for category in ['hero_talents', 'class_talents', 'spec_talents']:
            selected_count = len(filtered_talents.get(category, []))
            total_count = len(talents.get(category, []))
            print(f"  {category.capitalize()} ({selected_count}/{total_count} selected):")

            include_terms = config.get('TalentFilters', category)
            exclude_terms = config.get('TalentFilters', f'{category}_exclude')

            if include_terms == 'all':
                print(f"    Include: All")
            else:
                print(f"    Include: {include_terms}")

            if exclude_terms:
                print(f"    Exclude: {exclude_terms}")

    print(f"\nTotal Profilesets Generated: {len(profiles)}")

def run_combine_script(config):
    logger.info("Running combine script logic...")
    apl_folder = config.get('General', 'apl_folder')
    main_file = os.path.join(apl_folder, 'character.simc')
    output_file = os.path.join(apl_folder, 'full_character.simc')
    simc_path = config.get('General', 'simc')
    base_dir = os.path.dirname(main_file)

    def process_file(file_path):
        content = []
        try:
            with open(file_path, 'r') as infile:
                for line in infile:
                    if line.startswith('input='):
                        filename = line.split('=')[1].strip()
                        full_path = os.path.join(base_dir, filename)
                        content.extend(['\n'] + process_file(full_path) + ['\n'])
                    elif line.lower().startswith('# imports'):
                        continue
                    else:
                        content.append(line)
        except IOError as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise
        return content

    try:
        combined_content = process_file(main_file)

        temp_file = os.path.join(apl_folder, 'temp_combined.simc')
        with open(temp_file, 'w') as outfile:
            outfile.writelines(combined_content)

        try:
            subprocess.run([simc_path, temp_file, f'save={output_file}'], check=True)
            logger.info(f"Successfully compiled and saved to {output_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running simc: {e}")
        except FileNotFoundError:
            logger.error(f"Error: simc executable not found at {simc_path}")
        finally:
            os.remove(temp_file)

    except Exception as e:
        logger.error(f"Error in combine script logic: {e}")
        raise

def run_compare_reports_script(config):
    logger.info("Running compare_reports.py script...")
    compare_reports_script_path = os.path.join(config.script_dir, 'compare_reports.py')
    try:
        subprocess.run([sys.executable, compare_reports_script_path, config.config_path], check=True)
        logger.info("compare_reports.py script completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running compare_reports.py script: {e}")

def run_supplemental_profilesets(config, simulation_runner, report_folder, progress_tracker):
    apl_folder = config.get('General', 'apl_folder')
    supplemental_files = [
        'trinket_profilesets.simc',
        'gem_profilesets.simc',
        'enchant_profilesets_chest.simc',
        'enchant_profilesets_legs.simc',
        'enchant_profilesets_rings.simc',
        'enchant_profilesets_weapons.simc'
    ]

    iterations = config.getint('Simulations', 'iterations', fallback=None)
    target_error = config.getfloat('Simulations', 'target_error', fallback=None)
    targets = config.getint('Simulations', 'targets', fallback=1)
    sim_time = config.getint('Simulations', 'time', fallback=300)

    supplemental_talents = config.get('PostProcessing', 'supplemental_talents', fallback='')
    if not supplemental_talents:
        logger.error("Supplemental talents not specified in config. Skipping supplemental profilesets.")
        return

    total_supplemental_sims = len(supplemental_files)
    supplemental_progress_tracker = ProgressTracker(total_supplemental_sims)

    for supplemental_file in supplemental_files:
        supplemental_path = os.path.join(apl_folder, supplemental_file)

        if not os.path.exists(supplemental_path):
            logger.warning(f"Supplemental file {supplemental_file} not found. Skipping.")
            continue

        # Read the supplemental profileset content
        supplemental_content = FileHandler.read_file(supplemental_path)
        if supplemental_content is None:
            logger.error(f"Failed to read supplemental file: {supplemental_path}")
            continue

        # Create SimulationParameters
        sim_params = SimulationParameters(
            iterations=iterations,
            target_error=target_error,
            targets=targets,
            time=sim_time
        )

        updated_content = simulation_runner.update_simc_content(
            simulation_runner.character_content,
            sim_params,
            supplemental_talents
        )

        combined_content = f"{updated_content}\n\n{supplemental_content}"

        if sim_params.iterations is not None:
            combined_content += f"iterations={sim_params.iterations}\n"
        if sim_params.target_error is not None:
            combined_content += f"target_error={sim_params.target_error}\n"

        combined_content += f"\n{supplemental_content}"

        output_filename = f"supplemental_{os.path.splitext(supplemental_file)[0]}_{targets}T_{sim_time}sec.json"
        output_path = os.path.join(report_folder, output_filename)

        # Create a temporary file with the combined content in the apl_folder
        temp_file_path = FileHandler.create_temp_file(
            combined_content,
            prefix="temp_supplemental_",
            suffix='.simc',
            dir=apl_folder
        )

        if temp_file_path is None:
            logger.error(f"Failed to create temporary file for {supplemental_file}")
            continue

        try:
            # Run the simulation with the temporary file
            simulation_runner.run_simc(temp_file_path, output_path, supplemental_progress_tracker)
        finally:
            # Clean up the temporary file
            FileHandler.safe_delete(temp_file_path)

        supplemental_progress_tracker.start_new_simulation()

    supplemental_progress_tracker.close()
    logger.info("Supplemental profilesets simulations completed.")

def run_create_profiles(config_path):
    logger.info("Running create_profiles.py script...")
    create_profiles_script_path = os.path.join(os.path.dirname(__file__), 'create_profiles.py')

    cmd = [sys.executable, create_profiles_script_path, config_path]

    try:
        subprocess.run(cmd, check=True)
        logger.info("create_profiles.py script completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running create_profiles.py script: {e}")
        raise

def run_post_processing(config, simulation_runner, profiles, report_folder, progress_tracker=None):
    if progress_tracker is None:
        progress_tracker = ProgressTracker(1)  # Create a new tracker if not provided

    if config.getboolean('PostProcessing', 'supplemental_profilesets', fallback=False):
        logger.info("\nRunning supplemental profilesets simulations...")
        run_supplemental_profilesets(config, simulation_runner, report_folder, progress_tracker)

    if config.getboolean('PostProcessing', 'generate_combined_apl', fallback=False):
        run_combine_script(config)

    if config.getboolean('PostProcessing', 'generate_website', fallback=False):
        run_compare_reports_script(config)

def parse_targettime(config):
    targettime = config.get('Simulations', 'targettime', '').strip()
    iterations = config.getint('Simulations', 'iterations')
    target_error = config.getfloat('Simulations', 'target_error')

    if not targettime:
        return [SimulationParameters(
            iterations=iterations,
            target_error=target_error,
            targets=config.getint('Simulations', 'targets', fallback=1),
            time=config.getint('Simulations', 'time', fallback=300)
        )]

    simulations = []
    for combo in targettime.split():
        if combo.lower() == 'dungeonslice':
            simulations.append(SimulationParameters(
                iterations=iterations,
                target_error=target_error,
                fight_style='DungeonSlice'
            ))
        else:
            targets, time = map(int, combo.split(','))
            simulations.append(SimulationParameters(
                iterations=iterations,
                target_error=target_error,
                targets=targets,
                time=time
            ))
    return simulations

def run_simulations(config, talent_hash_manager, talent_strings, simulations, profiles, report_folder):
    total_simulations = len(simulations)
    estimated_profiles_per_sim = len(profiles) if not config.getboolean('Simulations', 'single_sim', fallback=False) else 1
    progress_tracker = ProgressTracker(total_simulations, estimated_profiles_per_sim)

    # Pre-generate all talent hashes
    talent_combinations = [
        (hero_talent, class_talent, spec_talent)
        for hero_talent in talent_strings['hero_talents'].values()
        for class_talent in talent_strings['class_talents'].values()
        for spec_talent in talent_strings['spec_talents'].values()
    ]
    talent_hash_manager.get_hashes_batch(talent_combinations)

    simulation_runner = SimulationRunner(config, talent_hash_manager, talent_strings)

    for sim_params in simulations:
        output_filename = generate_output_filename(config, sim_params)
        output_path = os.path.join(report_folder, output_filename)

        simulation_runner.run_simulation(sim_params, profiles, output_path, progress_tracker)
        progress_tracker.start_new_simulation()

    progress_tracker.close()
    logger.info("\nMain simulations completed.")

def prepare_profiles(config, talent_hash_manager, single_sim):
    if single_sim:
        return ["Single Sim"], {}, {}, {}

    profiles_file = os.path.join(config.get('General', 'apl_folder'), 'profile_templates.simc')
    talents, talent_strings = parse_profiles_simc(profiles_file, talent_hash_manager)
    if talents is None:
        logger.error("Failed to parse profile templates. Exiting.")
        return None, None, None, None

    filtered_talents = {
        category: filter_talents(
            tuple(talents[category].items()),
            tuple(config.get('TalentFilters', category).split()),
            tuple(config.get('TalentFilters', f'{category}_exclude').split()),
            category
        ) for category in ['hero_talents', 'class_talents', 'spec_talents']
    }

    if not any(filtered_talents.values()):
        logger.error("No valid profiles generated. Please check your talent selections.")
        return None, None, None, None

    profiles = [
        generate_simc_profile(hero_name, class_name, spec_name, talent_strings)
        for hero_name, _ in filtered_talents['hero_talents']
        for class_name, _ in filtered_talents['class_talents']
        for spec_name, _ in filtered_talents['spec_talents']
    ]

    return profiles, talents, filtered_talents, talent_strings

def main(config_path):
    config = Config(config_path)

    if config.getboolean('General', 'clear_cache', fallback=False) or config.getboolean('PostProcessing', 'supplemental_profilesets', fallback=False):
        run_create_profiles(config_path)

    talent_hash_manager = TalentHashManager(config)

    report_folder = config.get('General', 'report_folder', os.path.join(config.project_root, 'reports'))
    if not FileHandler.ensure_directory(report_folder):
        logger.error("Unable to create or access the report folder. Exiting.")
        return

    single_sim = config.getboolean('Simulations', 'single_sim', fallback=False)
    profiles, talents, filtered_talents, talent_strings = prepare_profiles(config, talent_hash_manager, single_sim)
    if not profiles:
        logger.error("No profiles generated. Check your talent filters and configuration.")
        return

    simulations = parse_targettime(config)

    print_summary(talents, filtered_talents, profiles, config, simulations)

    total_simulations = len(simulations)
    estimated_profiles_per_sim = len(profiles) if not single_sim else 1
    progress_tracker = ProgressTracker(total_simulations, estimated_profiles_per_sim)
    simulation_runner = SimulationRunner(config, talent_hash_manager, talent_strings)

    try:
        for sim_params in simulations:
            output_filename = generate_output_filename(config, sim_params)
            output_path = os.path.join(report_folder, output_filename)

            simulation_runner.run_simulation(sim_params, profiles, output_path, progress_tracker)
            progress_tracker.start_new_simulation()

        logger.info("\nMain simulations completed.")

        # Run post-processing tasks
        run_post_processing(config, simulation_runner, profiles, report_folder, progress_tracker)

    finally:
        progress_tracker.close()

    logger.info("\nAll processes completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate and run SimulationCraft profiles')
    parser.add_argument('config', help='Path to configuration file')
    args = parser.parse_args()
    main(args.config)