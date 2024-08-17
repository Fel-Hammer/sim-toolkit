// Global variables
let globalTopValues = {};
let globalPercentages = {};
let currentSortColumn = 1;
let currentSortDirection = 'asc';
let bestAldrachi = {};
let bestFelscarred = {};
let bestBuilds = {};
let filteredData = [];

// Constants for virtual scrolling
const ROW_HEIGHT = 100;
const BUFFER_SIZE = 15;

// Virtual scrolling variables
let visibleRowsCount;
let firstVisibleRowIndex;
let lastVisibleRowIndex;

// Additional data variables
let activeDataSet = null;

function calculateAverageDPS(build) {
    const simTypes = Object.keys(build.dps);
    const totalDPS = simTypes.reduce((sum, simType) => sum + build.dps[simType], 0);
    return totalDPS / simTypes.length;
}

function findBestBuilds(builds, simType) {
    const aldrachiBuilds = builds.filter(build => build.hero.toLowerCase().includes('aldrachi'));
    const felscarredBuilds = builds.filter(build => build.hero.toLowerCase().includes('felscarred'));

    const bestAldrachi = aldrachiBuilds.reduce((best, current) =>
        (current.dps[simType] > best.dps[simType]) ? current : best, aldrachiBuilds[0] || null);

    const bestFelscarred = felscarredBuilds.reduce((best, current) =>
        (current.dps[simType] > best.dps[simType]) ? current : best, felscarredBuilds[0] || null);

    return { bestAldrachi, bestFelscarred };
}

function createComparisonViz(simType) {
    if (!bestBuilds[simType] || !bestBuilds[simType].bestAldrachi || !bestBuilds[simType].bestFelscarred) {
        return '<div class="comparison-viz"><span>Insufficient data</span></div>';
    }

    const bestAldrachi = bestBuilds[simType].bestAldrachi;
    const bestFelscarred = bestBuilds[simType].bestFelscarred;

    const aldrachiValue = bestAldrachi.dps[simType] || 0;
    const felscarredValue = bestFelscarred.dps[simType] || 0;

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

function calculateGlobalValues(builds) {
    rawData.sim_types.forEach(simType => {
        const values = builds.map(build => build.dps[simType]).filter(Boolean);
        globalTopValues[simType] = Math.max(...values);
    });

    builds.forEach(build => {
        build.percentages = {};
        rawData.sim_types.forEach(simType => {
            const value = build.dps[simType] || 0;
            build.percentages[simType] = globalTopValues[simType] > 0
                ? ((globalTopValues[simType] - value) / globalTopValues[simType] * 100).toFixed(2)
                : '0.00';
        });
    });
}

function createCheckboxLabel(value, filterType, className, fullName) {
    const label = document.createElement('label');
    label.className = `mdc-checkbox ${className}`;

    label.innerHTML = `
        <input type="checkbox" class="mdc-checkbox__native-control" data-filter="${filterType}" value="${value}"/>
        <div class="mdc-checkbox__background">
            <svg class="mdc-checkbox__checkmark" viewBox="0 0 24 24">
                <path class="mdc-checkbox__checkmark-path" fill="none" d="M1.73,12.91 8.1,19.28 22.79,4.59"/>
            </svg>
        </div>
        <span class="mdc-checkbox__label">${fullName}</span>
    `;
    return label;
}

// Create a reverse mapping for abbreviated codes to full codes
const talentCodeMapping = {};
for (const type in talentDictionary) {
    for (const fullCode in talentDictionary[type]) {
        const talentInfo = talentDictionary[type][fullCode];
        if (Array.isArray(talentInfo)) {
            talentCodeMapping[talentInfo[1]] = fullCode;
        }
    }
}

function getFullTalentName(talent, talentType) {
    if (talentType === 'hero') {
        // For hero talents, we need to check if the talent starts with any of the hero talent keys
        for (const heroTalent in talentDictionary.hero) {
            if (talent.toLowerCase().startsWith(heroTalent.split('_')[0])) {
                return talentDictionary.hero[heroTalent];
            }
        }
    } else {
        // Use the full code if available, otherwise use the original talent code
        const fullCode = talentCodeMapping[talent] || talent;

        if (talentDictionary[talentType] && talentDictionary[talentType][fullCode]) {
            const talentInfo = talentDictionary[talentType][fullCode];
            if (Array.isArray(talentInfo)) {
                return talentInfo[0]; // Return the full name (first element of the array)
            } else {
                return talentInfo; // For cases where it's just a string
            }
        }
    }

    console.log(`Falling back to original talent name: ${talent}`);
    return talent; // Fallback to the original talent name if not found
}

function generateFilterHTML() {
    const filterContainers = {
        hero: document.getElementById('heroTalentFilters'),
        class: document.getElementById('classTalentFilters'),
        offensive: document.getElementById('offensiveTalentFilters'),
        defensive: document.getElementById('defensiveTalentFilters')
    };

    for (const [filterType, container] of Object.entries(filterContainers)) {
        if (!container) {
            console.error(`Filter container for ${filterType} not found in the DOM`);
            continue;
        }

        const talents = new Set(rawData.builds.flatMap(build =>
            filterType === 'hero' ? [build.hero] : build[filterType] || []
        ));

        Array.from(talents).sort().forEach(talent => {
            if (talent) {
                let talentType = filterType;
                if (filterType === 'offensive' || filterType === 'defensive') {
                    talentType = 'spec';
                }
                const fullName = getFullTalentName(talent, talentType);
                const label = createCheckboxLabel(talent, filterType, `${filterType}-talent`, fullName);
                container.appendChild(label);
            }
        });
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
        hero: new Set(),
        class: new Set(),
        offensive: new Set(),
        defensive: new Set()
    };

    document.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
        const filterType = checkbox.getAttribute('data-filter');
        selectedFilters[filterType].add(checkbox.value);
    });

    filteredData = rawData.builds.filter(build =>
        (selectedFilters.hero.size === 0 || selectedFilters.hero.has(build.hero)) &&
        (selectedFilters.class.size === 0 || build.class.some(talent => selectedFilters.class.has(talent))) &&
        (selectedFilters.offensive.size === 0 || build.offensive.some(talent => selectedFilters.offensive.has(talent))) &&
        (selectedFilters.defensive.size === 0 || build.defensive.some(talent => selectedFilters.defensive.has(talent)))
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
    rawData.sim_types.forEach((simType, index) => {
        const th = document.createElement('th');
        th.className = 'mdc-data-table__header-cell';
        th.setAttribute('role', 'columnheader');
        th.setAttribute('scope', 'col');
        th.setAttribute('onclick', `sortTable(${index + 2})`);
        th.setAttribute('data-sim-type', simType);
        th.innerHTML = `
            ${simType.replace(/_/g, ' ')}
            <i class="material-icons sort-icon">arrow_downward</i>
            ${createComparisonViz(simType)}
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

            rawData.sim_types.forEach(simType => {
                const value = row.dps[simType] || 0;
                const percentage = row.percentages[simType];
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

function formatBuildName(build) {
    if (!build) return '';

    const heroTalent = build.hero ? `<span class="chip chip-hero ${build.hero.toLowerCase().includes('aldrachi') ? 'aldrachi' : 'felscarred'}" title="Hero Talent: ${getFullTalentName(build.hero, 'hero')}">${build.hero}</span>` : '';

    const classTalents = build.class ? build.class.map(talent =>
        `<span class="chip chip-class" title="Class Talent: ${getFullTalentName(talent, 'class')}">${talent}</span>`
    ).join('') : '';

    const offensiveTalents = build.offensive ? build.offensive.map(talent =>
        `<span class="chip chip-spec chip-offensive" title="Offensive Talent: ${getFullTalentName(talent, 'spec')}">${talent}</span>`
    ).join('') : '';

    const defensiveTalents = build.defensive ? build.defensive.map(talent =>
        `<span class="chip chip-spec chip-defensive" title="Defensive Talent: ${getFullTalentName(talent, 'spec')}">${talent}</span>`
    ).join('') : '';

    const copyButton = `
        <button class="copy-hash-btn" onclick="copyTalentHash('${build.talent_hash || 'No hash available'}', this)" title="Copy talent hash">
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
            aValue = a.hero + a.class.join('') + a.offensive.join('') + a.defensive.join('');
            bValue = b.hero + b.class.join('') + b.offensive.join('') + b.defensive.join('');
        } else if (currentSortColumn === 1) {
            aValue = a.overall_rank || Infinity;
            bValue = b.overall_rank || Infinity;
        } else {
            const simType = rawData.sim_types[currentSortColumn - 2];
            aValue = a.dps[simType] || 0;
            bValue = b.dps[simType] || 0;
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
    const commonParams = '?width=313&level=80&&hideHeader=1';

    // Use the first sim type as default
    const defaultSimType = rawData.sim_types[0];

    if (bestBuilds[defaultSimType] && bestBuilds[defaultSimType].bestAldrachi) {
        document.getElementById('aldrachiOverall').src =
            `${baseUrl}${bestBuilds[defaultSimType].bestAldrachi.talent_hash}${commonParams}`;
    }

    if (bestBuilds['1T_300s'] && bestBuilds['1T_300s'].bestAldrachi) {
        document.getElementById('aldrachiSingleTarget').src =
            `${baseUrl}${bestBuilds['1T_300s'].bestAldrachi.talent_hash}${commonParams}`;
    }

    if (bestBuilds[defaultSimType] && bestBuilds[defaultSimType].bestFelscarred) {
        document.getElementById('felscarredOverall').src =
            `${baseUrl}${bestBuilds[defaultSimType].bestFelscarred.talent_hash}${commonParams}`;
    }

    if (bestBuilds['1T_300s'] && bestBuilds['1T_300s'].bestFelscarred) {
        document.getElementById('felscarredSingleTarget').src =
            `${baseUrl}${bestBuilds['1T_300s'].bestFelscarred.talent_hash}${commonParams}`;
    }
}

function generateAdditionalDataButtons() {
    const buttonContainer = document.getElementById('additionalDataButtons');
    const buttonNames = {
        'gem_profilesets': 'Gems',
        'trinket_profilesets': 'Trinkets',
        'embellishment_profilesets': 'Embellishments',
        'food_profilesets': 'Food',
        'consumable_profilesets': 'Consumables',
        'enchant_profilesets_weapons': 'Weapon Enchants',
        'enchant_profilesets_rings': 'Ring Enchants',
        'enchant_profilesets_legs': 'Leg Enchants',
        'enchant_profilesets_chest': 'Chest Enchants',
    };

    for (const dataSetName in additionalData) {
        console.log(dataSetName);
        const button = document.createElement('button');
        button.className = 'mdc-button';
        button.onclick = () => toggleAdditionalData(dataSetName);

        const buttonText = buttonNames[dataSetName] || dataSetName.replace(/_/g, ' ');
        button.innerHTML = `<span class="mdc-button__label">${buttonText}</span>`;

        buttonContainer.appendChild(button);
    }
}

function toggleAdditionalData(dataSetName) {
    const contentDiv = document.getElementById('additionalDataContent');
    const buttons = document.querySelectorAll('#additionalDataButtons button');

    if (activeDataSet === dataSetName) {
        // Toggling off
        activeDataSet = null;
        contentDiv.style.display = 'none';
        buttons.forEach(btn => btn.classList.remove('mdc-button--raised'));
    } else {
        // Toggling on
        activeDataSet = dataSetName;
        displayAdditionalData(dataSetName);
        contentDiv.style.display = 'block';
        buttons.forEach(btn => {
            if (btn.textContent.trim() === dataSetName.replace(/_/g, ' ')) {
                btn.classList.add('mdc-button--raised');
            } else {
                btn.classList.remove('mdc-button--raised');
            }
        });
    }
}

function displayAdditionalData(dataSetName) {
    const contentDiv = document.getElementById('additionalDataContent');
    contentDiv.innerHTML = ''; // Clear existing content
    const data = additionalData[dataSetName];

    if (!data || Object.keys(data).length === 0) {
        const p = document.createElement('p');
        p.textContent = 'No data available for this section.';
        contentDiv.appendChild(p);
        return;
    }

    const sortedData = Object.values(data).sort((a, b) => b.dps - a.dps);
    const topDPS = sortedData[0].dps;

    const title = document.createElement('h3');
    title.className = 'additional-data-title';
    const buttonNames = {
        'gem profilesets': 'Gems',
        'trinket profilesets': 'Trinkets',
        'enchant profilesets weapons': 'Weapon Enchants',
        'enchant profilesets rings': 'Ring Enchants',
        'enchant profilesets legs': 'Leg Enchants',
        'enchant profilesets chest': 'Chest Enchants'
    };
    title.textContent = buttonNames[dataSetName] || dataSetName.replace(/_/g, ' ');
    contentDiv.appendChild(title);

    const dataList = document.createElement('div');
    dataList.className = 'data-list';

    sortedData.forEach(item => {
        const percentDiff = ((item.dps - topDPS) / topDPS * 100).toFixed(2);
        // Using a logarithmic scale to exaggerate small differences
        const barWidth = Math.max(0, 100 - Math.log((topDPS - item.dps) / topDPS * 100 + 1) * 20);

        const dataItem = document.createElement('div');
        dataItem.className = 'data-item';

        const dataBar = document.createElement('div');
        dataBar.className = 'data-bar';
        dataBar.style.width = `${barWidth}%`;

        const dataName = document.createElement('span');
        dataName.className = 'data-name';
        dataName.textContent = item.name.replace(/_/g, ' ');

        const dataDiff = document.createElement('span');
        dataDiff.className = 'data-diff';
        dataDiff.textContent = percentDiff === '0.00' ? '0.00%' : `${percentDiff}%`;

        dataItem.appendChild(dataBar);
        dataItem.appendChild(dataName);
        dataItem.appendChild(dataDiff);

        dataList.appendChild(dataItem);
    });

    contentDiv.appendChild(dataList);
}

function initializeData(data) {
    if (!Array.isArray(data.builds) || data.builds.length === 0) {
        console.error("data.builds is empty or not an array");
        return;
    }

    calculateGlobalValues(data.builds);

    // Calculate average DPS for each build
    data.builds.forEach(build => {
        build.averageDPS = calculateAverageDPS(build);
    });

    // Sort builds by average DPS and assign overall rank
    data.builds.sort((a, b) => b.averageDPS - a.averageDPS);
    data.builds.forEach((build, index) => {
        build.overall_rank = index + 1;
    });

    // Find best builds for each sim type
    data.sim_types.forEach(simType => {
        bestBuilds[simType] = findBestBuilds(data.builds, simType);
    });

    // Update talent trees
    updateTalentTrees(bestBuilds);

    // Initialize filteredData with all builds
    filteredData = data.builds.map(build => ({
        ...build,
        talent_hash: build.talent_hash || ''
    }));

    // Sort the data by average DPS descending
    currentSortColumn = 1; // Overall rank is the second column (index 1)
    currentSortDirection = 'asc';
    sortData();

    updateTable();

    // Add change event listeners to checkboxes
    document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectedFilters);
    });

    // Update sort indicator for overall rank
    updateSortIndicator(1, 'asc');
}

window.onload = function () {
    generateAdditionalDataButtons();
    document.getElementById('additionalDataContent').style.display = 'none';
    document.getElementById('toggleFilters').addEventListener('click', function () {
        var filters = document.getElementById('filters');
        filters.style.display = filters.style.display === 'none' ? 'flex' : 'none';
    });


    if (typeof rawData !== 'undefined' && rawData.builds && Array.isArray(rawData.builds) && rawData.sim_types) {
        generateFilterHTML();
        initializeData(rawData);
    } else {
        console.error('rawData is not defined correctly or rawData.builds is not an array');
    }
};