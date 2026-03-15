// StaySweep — Frontend Logic

const form = document.getElementById('search-form');
const queryInput = document.getElementById('query');
const cityInput = document.getElementById('city');
const searchBtn = document.getElementById('search-btn');
const progressSection = document.getElementById('progress-section');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const resultsSection = document.getElementById('results-section');
const resultsTitle = document.getElementById('results-title');
const resultsGrid = document.getElementById('results-grid');
const emptyState = document.getElementById('empty-state');

// Progress step weights for the progress bar
const STEP_PROGRESS = {
    'init': 5,
    'parsing': 10,
    'parsed': 15,
    'crawling': 25,
    'crawled': 40,
    'persisting': 45,
    'enriching': 50,
    'analyzing': 55,
    'complete': 100,
};

let resultCount = 0;

// ── Example chip clicks ──────────────────────────────────

document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
        queryInput.value = chip.dataset.query;
        cityInput.value = chip.dataset.city;
        form.dispatchEvent(new Event('submit'));
    });
});

// ── Form submit ──────────────────────────────────────────

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const query = queryInput.value.trim();
    const city = cityInput.value.trim();
    if (!query || !city) return;

    // Reset UI
    searchBtn.disabled = true;
    searchBtn.textContent = 'Searching...';
    emptyState.classList.add('hidden');
    progressSection.classList.remove('hidden');
    resultsSection.classList.remove('hidden');
    resultsTitle.textContent = `Searching for "${query}" in ${city}...`;
    resultsGrid.innerHTML = '';
    resultCount = 0;
    setProgress(5, 'Starting search...');

    try {
        // Start the search
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, city }),
        });

        const { search_id } = await res.json();

        // Connect to SSE stream
        const evtSource = new EventSource(`/api/search/${search_id}/stream`);

        evtSource.addEventListener('status', (e) => {
            const data = JSON.parse(e.data);
            const pct = STEP_PROGRESS[data.step] || 50;
            setProgress(pct, data.message);
        });

        evtSource.addEventListener('hotel_result', (e) => {
            const result = JSON.parse(e.data);
            resultCount++;
            // Increment progress slightly with each result
            const analysisPct = 55 + Math.min(40, resultCount * 4);
            setProgress(analysisPct, `Analyzed ${resultCount} hotels...`);
            // Only show hotels with meaningful match during streaming
            if (result.final_score > 0.1) {
                addResultCard(result, resultCount);
            }
        });

        evtSource.addEventListener('complete', (e) => {
            const data = JSON.parse(e.data);
            setProgress(100, 'Search complete!');
            searchBtn.disabled = false;
            searchBtn.textContent = 'Search';
            evtSource.close();

            // Re-sort and re-render — only show hotels with meaningful match scores
            resultsGrid.innerHTML = '';
            const MATCH_THRESHOLD = 0.1;

            if (data.results && data.results.length > 0) {
                const matches = data.results.filter(r => r.final_score > MATCH_THRESHOLD);
                const totalSearched = data.results.length;

                if (matches.length > 0) {
                    // Show matching hotels
                    let rank = 1;
                    matches.forEach((r) => addResultCard(r, rank++));
                    resultsTitle.textContent = `${matches.length} match${matches.length === 1 ? '' : 'es'} found`;
                } else {
                    resultsTitle.textContent = 'No matching hotels found.';
                }

                // Add search summary below results
                addSearchSummary(totalSearched, matches.length, query, city, data.results);
            } else {
                resultsTitle.textContent = 'No hotels found — check that API keys are configured.';
            }

            // Fade out progress bar
            setTimeout(() => {
                progressSection.classList.add('hidden');
            }, 2000);
        });

        evtSource.addEventListener('error', (e) => {
            if (e.data) {
                const data = JSON.parse(e.data);
                setProgress(0, `Error: ${data.message}`);
            }
            searchBtn.disabled = false;
            searchBtn.textContent = 'Search';
            evtSource.close();
        });

        evtSource.onerror = () => {
            searchBtn.disabled = false;
            searchBtn.textContent = 'Search';
            evtSource.close();
        };

    } catch (err) {
        setProgress(0, `Error: ${err.message}`);
        searchBtn.disabled = false;
        searchBtn.textContent = 'Search';
    }
});

// ── Progress bar ─────────────────────────────────────────

function setProgress(pct, message) {
    progressBar.classList.remove('indeterminate');
    progressBar.style.width = pct + '%';
    progressText.textContent = message;
}

// ── Result cards ─────────────────────────────────────────

function addResultCard(result, rank) {
    const card = document.createElement('div');
    card.className = 'result-card';

    const scorePct = Math.round(result.final_score * 100);
    const scoreClass = scorePct >= 60 ? 'score-high' : scorePct >= 30 ? 'score-mid' : 'score-low';
    const textPct = Math.round(result.text_score * 100);
    const visionPct = Math.round(result.vision_score * 100);

    // Build evidence HTML
    let evidenceHTML = '';
    if (result.evidence_text && result.evidence_text.length > 0) {
        const snippet = result.evidence_text[0].length > 150
            ? result.evidence_text[0].substring(0, 150) + '...'
            : result.evidence_text[0];
        evidenceHTML += `
            <div class="evidence-item">
                <div class="evidence-label">Review Evidence</div>
                "${snippet}"
            </div>`;
    }
    if (result.evidence_images && result.evidence_images.length > 0) {
        evidenceHTML += `
            <div class="evidence-item">
                <div class="evidence-label">Photo Evidence</div>
                ${result.evidence_images[0].description}
            </div>`;
    }

    const ratingHTML = result.hotel_rating
        ? `<div class="card-rating">${'&#9733;'.repeat(Math.round(result.hotel_rating))} ${result.hotel_rating.toFixed(1)}</div>`
        : '';

    const hotelLink = result.hotel_url
        ? `<a href="${escapeHtml(result.hotel_url)}" target="_blank" rel="noopener">${escapeHtml(result.hotel_name)}</a>`
        : escapeHtml(result.hotel_name);

    card.innerHTML = `
        <div class="card-header">
            <div>
                <div class="card-rank">#${rank}</div>
                <div class="card-name">${hotelLink}</div>
                ${ratingHTML}
            </div>
            <div class="card-score">
                <div class="score-value ${scoreClass}">${scorePct}%</div>
                <div class="score-label">match</div>
            </div>
        </div>
        <div class="card-scores-bar">
            <div class="mini-score">Text: <span>${textPct}%</span></div>
            <div class="mini-score">Vision: <span>${visionPct}%</span></div>
        </div>
        <div class="card-summary">${escapeHtml(result.summary)}</div>
        ${evidenceHTML ? `<div class="card-evidence">${evidenceHTML}</div>` : ''}
    `;

    resultsGrid.appendChild(card);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Search summary ──────────────────────────────────────

function addSearchSummary(totalSearched, matchCount, query, city, allResults) {
    // Remove any existing summary
    const existing = document.getElementById('search-summary');
    if (existing) existing.remove();

    const summary = document.createElement('div');
    summary.id = 'search-summary';
    summary.className = 'search-summary';

    // Build list of all hotels searched (names only)
    const hotelNames = allResults.map(r => r.hotel_name);
    const sources = [...new Set(allResults.map(r => {
        const url = r.hotel_url || '';
        if (url.includes('tripadvisor')) return 'TripAdvisor';
        if (url.includes('google')) return 'Google';
        if (url.includes('booking')) return 'Booking.com';
        if (url.includes('yelp')) return 'Yelp';
        return 'Web';
    }))];

    summary.innerHTML = `
        <div class="summary-header">Search Summary</div>
        <div class="summary-stats">
            <span><strong>${totalSearched}</strong> hotels searched in ${escapeHtml(city)}</span>
            <span><strong>${matchCount}</strong> potential match${matchCount === 1 ? '' : 'es'}</span>
            <span>Sources: ${sources.join(', ')}</span>
        </div>
        <details class="summary-details">
            <summary>Hotels searched (${totalSearched})</summary>
            <ul class="searched-hotels-list">
                ${hotelNames.map(n => {
                    const result = allResults.find(r => r.hotel_name === n);
                    const score = result ? Math.round(result.final_score * 100) : 0;
                    const icon = score > 10 ? '&#9679;' : '&#9675;';
                    return `<li>${icon} ${escapeHtml(n)} <span class="mini-pct">${score}%</span></li>`;
                }).join('')}
            </ul>
        </details>
    `;

    resultsGrid.parentNode.appendChild(summary);
}
