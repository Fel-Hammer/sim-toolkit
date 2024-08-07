const ABBREVIATIONS = {
    "AF": "Ascending Flame",
    "SpB": "Spirit Bomb",
    "NoSpB": "No Spirit Bomb",
    "BE": "Bulk Extraction",
    "BB": "Burning Blood",
    "SF": "Soul Furnace",
    "FC": "Focused Cleave",
    "CoA": "Chains of Anger",
    "VF": "Volatile Flameblood",
    "FD": "Fiery Demise",
    "StF": "Stoke the Flames",
    "CoB": "Cycle of Binding",
    "BA": "Burning Alive",
    "CF": "Charred Flesh",
    "DGB": "Darkglare Boon",
    "SC": "Soul Carver",
    "Crush": "Soulcrush",
    "IS": "Illuminated Sigils",
    "DiF": "Down in Flames",
    "Calc": "Calcified Spikes",
    "ES": "Extended Spikes",
    "FFF": "Fel Flame Fortification",
    "VR": "Void Reaver",
    "PB": "Painbringer",
    "FtD": "Feed the Demon",
    "LR": "Last Resort",
    "aldrachi": "Aldrachi Reaver",
    "felscarred_flamebound": "Felscarred Flamebound",
    "felscarred_student": "Felscarred Student",
    "hunt": "The Hunt",
    "CA": "Collective Anguish",
    "CoSp": "Sigil of Spite",
    "aldrachi_keen": "Aldrachi Keen",
    "aldrachi_preemptive": "Aldrachi Preemptive",
    "SoSp": "Sigil of Spite",
    "CS": "Imp. Chaos Strike",
    "AFI": "A Fire Inside",
    "AB": "Accelerated Blade",
    "Anni": "Annihilation",
    "AMN": "Any Means Necessary",
    "BD": "Blade Dance",
    "BF": "Blind Fury",
    "BH": "Burning Hatred",
    "BW": "Burning Wound",
    "CotG": "Champion of the Glaive",
    "CT": "Chaos Theory",
    "CD": "Chaotic Disposition",
    "CTr": "Chaotic Trans.",
    "CC": "Critical Chaos",
    "CoH": "Cycle of Hatred",
    "DWF": "Dancing with Fate",
    "DS": "Death Sweep",
    "DBlades": "Demon Blades",
    "DA": "Demonic Appetite",
    "DBite": "Demon's Bite",
    "EB": "Eye Beam",
    "FBarr": "Fel Barrage",
    "FE": "Fel Eruption",
    "FR": "Fel Rush",
    "FiB": "First Blood",
    "FG": "Furious Gaze",
    "FT": "Furious Throws",
    "GT": "Glaive Tempest",
    "GI": "Growing Inferno",
    "IA": "Immolation Aura",
    "Init": "Initiative",
    "ID": "Inner Demon",
    "IH": "Insatiable Hunger",
    "IP": "Isolated Prey",
    "KYE": "Know Your Enemy",
    "LCK": "Looks Can Kill",
    "RO": "Relentless Onslaught",
    "RH": "Restless Hunter",
    "ROC": "Rush of Chaos",
    "SG": "Serrated Glaive",
    "SD": "Shattered Destiny",
    "Souls": "Shattered Soul",
    "SR": "Soul Rending",
    "SSc": "Soulscar",
    "ToR": "Trail of Ruin",
    "UBC": "Unbound Chaos",
    "DD": "Deflecting Dance",
    "MD": "Mortal Dance",
    "DI": "Desperate Instincts",
    "NW": "Netherwalk"
};

// Global variables
let globalTopValues = {};
let globalPercentages = {};
let currentSortColumn = 1;
let currentSortDirection = 'asc';
let bestAldrachi = {};
let bestFelscarred = {};
const bestBuilds = {};
let filteredData = [];

// Constants for virtual scrolling
const ROW_HEIGHT = 100;
const BUFFER_SIZE = 15;

// Virtual scrolling variables
let visibleRowsCount;
let firstVisibleRowIndex;
let lastVisibleRowIndex;

function findBestBuilds(data, metric) {
    const aldrachiBuilds = data.filter(row => row.hero_talent.toLowerCase().includes('aldrachi'));
    const felscarredBuilds = data.filter(row =>
        row.hero_talent.toLowerCase().includes('felscarred') ||
        row.hero_talent.toLowerCase().includes('student') ||
        row.hero_talent.toLowerCase().includes('flamebound')
    );

    bestAldrachi = aldrachiBuilds.reduce((best, current) =>
        (current.metrics[metric] > best.metrics[metric]) ? current : best, aldrachiBuilds[0] || null);

    bestFelscarred = felscarredBuilds.reduce((best, current) =>
        (current.metrics[metric] > best.metrics[metric]) ? current : best, felscarredBuilds[0] || null);

    return { bestAldrachi, bestFelscarred };
}

function createComparisonViz(metric) {
    const { bestAldrachi, bestFelscarred } = bestBuilds[metric];

    if (!bestAldrachi || !bestFelscarred) {
        return '<div class="comparison-viz"><span>Insufficient data</span></div>';
    }

    const aldrachiValue = bestAldrachi.metrics[metric] || 0;
    const felscarredValue = bestFelscarred.metrics[metric] || 0;

    if (aldrachiValue === 0 && felscarredValue === 0) {
        return '<div class="comparison-viz"><span>No data</span></div>';
    }

    const [topBuild, bottomBuild, topValue, bottomValue] = aldrachiValue > felscarredValue
        ? ['Aldrachi', 'Felscarred', aldrachiValue, felscarredValue]
        : ['Felscarred', 'Aldrachi', felscarredValue, aldrachiValue];

    const percentageDiff = ((topValue - bottomValue) / bottomValue * 100).toFixed(1);

    return `
        <div class="comparison-viz" title="${topBuild}: ${topValue.toFixed(2)}, ${bottomBuild}: ${bottomValue.toFixed(2)}">
            <div class="viz-better ${topBuild.toLowerCase()}">${topBuild}</div>
            <div class="viz-diff">+${percentageDiff}%</div>
            <div class="viz-worse">vs ${bottomBuild}</div>
        </div>
    `;
}

function calculateGlobalValues(data) {
    reportTypes.forEach(type => {
        const values = data.filter(r => r && r.metrics && r.metrics[type]).map(r => r.metrics[type]);
        globalTopValues[type] = Math.max(...values);
    });

    data.forEach(row => {
        if (row && row.metrics) {
            row.percentages = {};
            reportTypes.forEach(type => {
                const value = row.metrics[type] || 0;
                row.percentages[type] = globalTopValues[type] > 0
                    ? ((globalTopValues[type] - value) / globalTopValues[type] * 100).toFixed(2)
                    : '0.00';
            });
        }
    });
}

function createCheckboxLabel(value, filterType, className) {
    const label = document.createElement('label');
    label.className = `mdc-checkbox ${className}`;

    // Replace abbreviation with full name for display, case-insensitively
    let displayValue = value;
    const lowercaseValue = value.toLowerCase();
    for (const [abbr, fullName] of Object.entries(ABBREVIATIONS)) {
        if (abbr.toLowerCase() === lowercaseValue) {
            displayValue = fullName;
            break;
        }
    }

    label.innerHTML = `
        <input type="checkbox" class="mdc-checkbox__native-control" data-filter="${filterType}" value="${value}"/>
        <div class="mdc-checkbox__background">
            <svg class="mdc-checkbox__checkmark" viewBox="0 0 24 24">
                <path class="mdc-checkbox__checkmark-path" fill="none" d="M1.73,12.91 8.1,19.28 22.79,4.59"/>
            </svg>
        </div>
        <span class="mdc-checkbox__label">${displayValue}</span>
    `;
    return label;
}

function generateFilterHTML() {
    const filterContainers = {
        heroTalent: document.getElementById('heroTalentFilters'),
        classTalents: document.getElementById('classTalentFilters'),
        offensiveTalents: document.getElementById('offensiveTalentFilters'),
        defensiveTalents: document.getElementById('defensiveTalentFilters')
    };

    for (const [filterType, container] of Object.entries(filterContainers)) {
        if (!container) {
            console.error(`Filter container for ${filterType} not found in the DOM`);
            continue;
        }

        if (Array.isArray(filteredTalents[filterType])) {
            // Sort the talents based on their order in ABBREVIATIONS
            const sortedTalents = filteredTalents[filterType].sort((a, b) => {
                const indexA = Object.keys(ABBREVIATIONS).indexOf(a);
                const indexB = Object.keys(ABBREVIATIONS).indexOf(b);
                return indexA - indexB;
            });

            sortedTalents.forEach(value => {
                if (value) {
                    const label = createCheckboxLabel(value, filterType, `${filterType.toLowerCase()}-talent`);
                    container.appendChild(label);
                }
            });
        } else {
            console.error(`filteredTalents[${filterType}] is not an array`);
        }
    }

    // Add event listeners for checkboxes
    document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectedFilters);
    });
}

function updateSelectedFilters() {
    applyFilters();
}

window.copyTalentHash = function(talentHash, buttonElement) {
    navigator.clipboard.writeText(talentHash).then(() => {
        const copyIcon = buttonElement.querySelector('.copy-icon');
        const successIcon = buttonElement.querySelector('.success-icon');

        copyIcon.style.display = 'none';
        successIcon.style.display = 'inline-block';
        successIcon.style.color = '#4CAF50'; // Green color

        setTimeout(() => {
            copyIcon.style.display = 'inline-block';
            successIcon.style.display = 'none';
        }, 2000); // Reset after 2 seconds
    }).catch(err => {
        console.error('Failed to copy talent hash: ', err);
    });
};

function applyFilters() {
    const selectedFilters = {
        heroTalent: new Set(),
        classTalents: new Set(),
        offensiveTalents: new Set(),
        defensiveTalents: new Set()
    };

    document.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
        const filterType = checkbox.getAttribute('data-filter');
        selectedFilters[filterType].add(checkbox.value);
    });

    filteredData = rawData.filter(row =>
        (selectedFilters.heroTalent.size === 0 || selectedFilters.heroTalent.has(row.hero_talent)) &&
        (selectedFilters.classTalents.size === 0 || Array.from(selectedFilters.classTalents).every(talent => row.class_talents.includes(talent))) &&
        (selectedFilters.offensiveTalents.size === 0 || Array.from(selectedFilters.offensiveTalents).every(talent => row.offensive_talents.includes(talent))) &&
        (selectedFilters.defensiveTalents.size === 0 || Array.from(selectedFilters.defensiveTalents).every(talent => row.defensive_talents.includes(talent)))
    );

    sortData();
    updateTable();
}

function updateTable() {
    const table = document.getElementById("dataTable");
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');

    // Clear existing header and body
    thead.innerHTML = '';
    tbody.innerHTML = '';

    // Create header row
    const headerRow = document.createElement('tr');
    headerRow.className = 'mdc-data-table__header-row';

    // Add Build and Rank headers
    headerRow.innerHTML = `
        <th class="mdc-data-table__header-cell build-name" role="columnheader" scope="col">Build</th>
        <th class="mdc-data-table__header-cell rank" role="columnheader" scope="col" onclick="sortTable(1)">
            Rank <i class="material-icons sort-icon">arrow_downward</i>
        </th>
    `;

    // Add metric headers with comparison viz
    reportTypes.forEach((type, index) => {
        const th = document.createElement('th');
        th.className = 'mdc-data-table__header-cell';
        th.setAttribute('role', 'columnheader');
        th.setAttribute('scope', 'col');
        th.setAttribute('onclick', `sortTable(${index + 2})`);
        th.setAttribute('data-metric', type);
        th.innerHTML = `
            ${type}
            <i class="material-icons sort-icon">arrow_downward</i>
            ${createComparisonViz(type)}
        `;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);

    // Create a container for virtual scrolling
    const virtualScrollContainer = document.createElement('div');
    virtualScrollContainer.id = 'virtualScrollContainer';
    virtualScrollContainer.style.height = `${filteredData.length * ROW_HEIGHT}px`;
    tbody.appendChild(virtualScrollContainer);

    // Initialize virtual scroll
    initializeVirtualScroll();

    // Update sort indicators
    updateSortIndicator(currentSortColumn, currentSortDirection);
}

function renderVisibleRows() {
    const tbody = document.getElementById("dataTable").querySelector('tbody');
    const virtualScrollContainer = document.getElementById('virtualScrollContainer');
    const scrollTop = tbody.scrollTop;
    firstVisibleRowIndex = Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_SIZE;
    lastVisibleRowIndex = firstVisibleRowIndex + visibleRowsCount + 2 * BUFFER_SIZE;

    firstVisibleRowIndex = Math.max(0, firstVisibleRowIndex);
    lastVisibleRowIndex = Math.min(filteredData.length - 1, lastVisibleRowIndex);

    // Remove rows that are no longer visible
    const existingRows = virtualScrollContainer.querySelectorAll('.mdc-data-table__row');
    existingRows.forEach(row => {
        const rowIndex = parseInt(row.getAttribute('data-index'));
        if (rowIndex < firstVisibleRowIndex || rowIndex > lastVisibleRowIndex) {
            virtualScrollContainer.removeChild(row);
        }
    });

    // Add new rows that have become visible
    for (let i = firstVisibleRowIndex; i <= lastVisibleRowIndex; i++) {
        if (!virtualScrollContainer.querySelector(`[data-index="${i}"]`)) {
            const row = filteredData[i];
            const tr = document.createElement('tr');
            tr.className = 'mdc-data-table__row';
            tr.setAttribute('data-index', i);
            tr.style.position = 'absolute';
            tr.style.top = `${i * ROW_HEIGHT}px`;
            tr.style.height = `${ROW_HEIGHT}px`;

            // Build name column
            const buildNameCell = document.createElement('td');
            buildNameCell.className = 'mdc-data-table__cell build-name';
            buildNameCell.innerHTML = formatBuildName(row);
            tr.appendChild(buildNameCell);

            // Rank column
            const rankCell = document.createElement('td');
            rankCell.className = 'mdc-data-table__cell rank';
            rankCell.setAttribute('data-value', row.overall_rank || '');
            rankCell.textContent = row.overall_rank || 'N/A';
            tr.appendChild(rankCell);

            // Metric columns
            reportTypes.forEach(type => {
                const value = row.metrics && row.metrics[type] ? row.metrics[type] : 0;
                const percentage = row.percentages[type];
                const barColor = getBarColor(parseFloat(percentage));

                const metricCell = document.createElement('td');
                metricCell.className = 'mdc-data-table__cell';
                metricCell.setAttribute('data-value', value);
                metricCell.innerHTML = `
                    <div class="metric-container">
                        <span class="metric-value">${formatNumber(value)}</span>
                        <span class="metric-diff">(-${percentage}%)</span>
                    </div>
                    <div class="linear-progress">
                        <div class="linear-progress-bar" style="width: ${100 - parseFloat(percentage)}%; background-color: ${barColor};"></div>
                    </div>
                `;
                tr.appendChild(metricCell);
            });

            virtualScrollContainer.appendChild(tr);
        }
    }
}

function initializeVirtualScroll() {
    const tbody = document.getElementById("dataTable").querySelector('tbody');
    const tableHeight = tbody.clientHeight;
    visibleRowsCount = Math.ceil(tableHeight / ROW_HEIGHT);

    tbody.addEventListener('scroll', () => {
        requestAnimationFrame(renderVisibleRows);
    });

    window.addEventListener('resize', () => {
        const newTableHeight = tbody.clientHeight;
        visibleRowsCount = Math.ceil(newTableHeight / ROW_HEIGHT);
        renderVisibleRows();
    });

    renderVisibleRows();
}

function formatBuildName(row) {
    if (!row) return '';

    function getFullTalentName(talent) {
        const lowercaseTalent = talent.toLowerCase();
        for (const [abbr, fullName] of Object.entries(ABBREVIATIONS)) {
            if (abbr.toLowerCase() === lowercaseTalent) {
                return fullName;
            }
        }
        return talent;
    }

    function sortTalents(talents) {
        return talents.sort((a, b) => {
            const indexA = Object.keys(ABBREVIATIONS).indexOf(a);
            const indexB = Object.keys(ABBREVIATIONS).indexOf(b);
            return indexA - indexB;
        });
    }

    const heroTalent = row.hero_talent ? `<span class="chip chip-hero ${row.hero_talent.toLowerCase().includes('aldrachi') ? 'aldrachi' : 'felscarred'}" title="Hero Talent: ${getFullTalentName(row.hero_talent)}">${getFullTalentName(row.hero_talent)}</span>` : '';

    const classTalents = row.class_talents && Array.isArray(row.class_talents) ? sortTalents(row.class_talents).map(talent =>
        `<span class="chip chip-class" title="Class Talent: ${getFullTalentName(talent)}">${talent}</span>`
    ).join('') : '';

    const offensiveTalents = row.offensive_talents && Array.isArray(row.offensive_talents) ? sortTalents(row.offensive_talents).map(talent =>
        `<span class="chip chip-spec chip-offensive" title="Offensive Talent: ${getFullTalentName(talent)}">${talent}</span>`
    ).join('') : '';

    const defensiveTalents = row.defensive_talents && Array.isArray(row.defensive_talents) ? sortTalents(row.defensive_talents).map(talent =>
        `<span class="chip chip-spec chip-defensive" title="Defensive Talent: ${getFullTalentName(talent)}">${talent}</span>`
    ).join('') : '';

    const copyButton = `
        <button class="copy-hash-btn" onclick="copyTalentHash('${row.talent_hash || 'No hash available'}', this)" title="Copy talent hash">
            <i class="material-icons copy-icon">content_copy</i>
            <i class="material-icons success-icon" style="display: none;">check_circle</i>
        </button>
    `;

    return `
        <div class="build-name-container">
            <div class="copy-button-container">
                ${copyButton}
            </div>
            <div class="talents-container">
                ${heroTalent}${classTalents}${offensiveTalents}${defensiveTalents}
            </div>
        </div>
    `;
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    }
return num.toFixed(2);
}

function getBarColor(percentage) {
    const colorStops = [
        { percent: 0, color: '#4CAF50' },   // Material Green 500
        { percent: 2, color: '#8BC34A' },   // Material Light Green 500
        { percent: 5, color: '#CDDC39' },   // Material Lime 500
        { percent: 10, color: '#FFEB3B' },  // Material Yellow 500
        { percent: 15, color: '#FFC107' },  // Material Amber 500
        { percent: 20, color: '#FF9800' },  // Material Orange 500
        { percent: 30, color: '#FF5722' },  // Material Deep Orange 500
        { percent: 100, color: '#F44336' }  // Material Red 500
    ];

    for (let i = 0; i < colorStops.length - 1; i++) {
        if (percentage <= colorStops[i + 1].percent) {
            const t = (percentage - colorStops[i].percent) / (colorStops[i + 1].percent - colorStops[i].percent);
            return interpolateColor(colorStops[i].color, colorStops[i + 1].color, t);
        }
    }

    return colorStops[colorStops.length - 1].color;
}

function interpolateColor(color1, color2, t) {
    const r1 = parseInt(color1.slice(1, 3), 16);
    const g1 = parseInt(color1.slice(3, 5), 16);
    const b1 = parseInt(color1.slice(5, 7), 16);

    const r2 = parseInt(color2.slice(1, 3), 16);
    const g2 = parseInt(color2.slice(3, 5), 16);
    const b2 = parseInt(color2.slice(5, 7), 16);

    const r = Math.round(r1 * (1 - t) + r2 * t);
    const g = Math.round(g1 * (1 - t) + g2 * t);
    const b = Math.round(b1 * (1 - t) + b2 * t);

    return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
}

function sortTable(n) {
    const table = document.getElementById("dataTable");
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const th = table.querySelectorAll('th')[n];
    const icon = th.querySelector('.sort-icon');

    const isAscending = icon.textContent === 'arrow_upward';
    currentSortDirection = isAscending ? 'desc' : 'asc';
    currentSortColumn = n;

    applyFilters();
    updateSortIndicator(n, currentSortDirection);
}

function sortData() {
    filteredData.sort((a, b) => {
        let aValue, bValue;
        if (currentSortColumn === 0) {
            aValue = a.full_name;
            bValue = b.full_name;
        } else if (currentSortColumn === 1) {
            aValue = a.overall_rank || Infinity;
            bValue = b.overall_rank || Infinity;
        } else {
            const metricType = reportTypes[currentSortColumn - 2];
            aValue = a.metrics[metricType] || 0;
            bValue = b.metrics[metricType] || 0;
        }

        if (aValue < bValue) return currentSortDirection === 'asc' ? -1 : 1;
        if (aValue > bValue) return currentSortDirection === 'asc' ? 1 : -1;
        return 0;
    });
}

function updateSortIndicator(columnIndex, direction) {
    const headers = document.querySelectorAll('.mdc-data-table__header-cell');
    headers.forEach((header, index) => {
        const icon = header.querySelector('.sort-icon');
        if (icon) {
            if (index === columnIndex) {
                icon.textContent = direction === 'asc' ? 'arrow_upward' : 'arrow_downward';
                icon.classList.add('active');
            } else {
                icon.textContent = 'arrow_downward';
                icon.classList.remove('active');
            }
        }
    });
}

function updateTalentTrees(bestBuilds) {
    const baseUrl = 'https://mimiron.raidbots.com/simbot/render/talents/';
    const commonParams = '?width=315&level=80&&hideHeader=1';

  if (bestBuilds['1T 300s'] && bestBuilds['1T 300s'].bestAldrachi) {
    document.getElementById('aldrachiSingleTarget').src =
      `${baseUrl}${bestBuilds['1T 300s'].bestAldrachi.talent_hash}${commonParams}`;
  }

  if (bestBuilds['Overall'] && bestBuilds['Overall'].bestAldrachi) {
    document.getElementById('aldrachiOverall').src =
      `${baseUrl}${bestBuilds['Overall'].bestAldrachi.talent_hash}${commonParams}`;
  }

  if (bestBuilds['1T 300s'] && bestBuilds['1T 300s'].bestFelscarred) {
    document.getElementById('felscarredSingleTarget').src =
      `${baseUrl}${bestBuilds['1T 300s'].bestFelscarred.talent_hash}${commonParams}`;
  }

  if (bestBuilds['Overall'] && bestBuilds['Overall'].bestFelscarred) {
    document.getElementById('felscarredOverall').src =
      `${baseUrl}${bestBuilds['Overall'].bestFelscarred.talent_hash}${commonParams}`;
  }
}

function initializeData(rawData) {
    if (!Array.isArray(rawData) || rawData.length === 0) {
        console.error("rawData is empty or not an array");
        return;
    }
    calculateGlobalValues(rawData);

    // Find best builds for each metric
    reportTypes.forEach(metric => {
        bestBuilds[metric] = findBestBuilds(rawData, metric);
    });

    bestBuilds['Overall'] = findBestBuilds(rawData, 'overall_rank');
    // Update talent trees
    updateTalentTrees(bestBuilds);

    // Initialize filteredData with all data, including talent_hash
    filteredData = rawData.map(row => ({
        ...row,
        talent_hash: row.talent_hash || ''  // Ensure talent_hash is included
    }));

    // Sort the data by 1T 300s descending
    currentSortColumn = reportTypes.indexOf('1T 300s') + 2;
    currentSortDirection = 'desc';
    sortData();

    updateTable();

    // Add change event listeners to checkboxes
    document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectedFilters);
    });

    // Update sort indicator for 1T 300s
    updateSortIndicator(reportTypes.indexOf('1T 300s') + 2, 'desc');
}

window.onload = function () {
    document.getElementById('toggleFilters').addEventListener('click', function() {
        var filters = document.getElementById('filters');
        filters.style.display = filters.style.display === 'none' ? 'flex' : 'none';
    });

    if (typeof rawData !== 'undefined' && Array.isArray(rawData) && typeof filteredTalents !== 'undefined' && typeof reportTypes !== 'undefined') {
        generateFilterHTML();
        initializeData(rawData);
    } else {
        console.error('rawData, filteredTalents, or reportTypes is not defined or rawData is not an array');
    }
};