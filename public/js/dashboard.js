// State Management
let currentStatus = 'all';
let currentCategory = '';
let currentPriority = 'all';
let currentSort = 'score';
let loadedStories = []; // Client-side cache for modal details lookup
let activeStoryId = null;


// DOM Elements
const collectBtn = document.getElementById('collect-btn');
const collectSpinner = document.getElementById('collect-spinner');
const collectText = collectBtn.querySelector('.btn-text');

const processBtn = document.getElementById('process-btn');
const processSpinner = document.getElementById('process-spinner');
const processText = processBtn.querySelector('.btn-text');

const categorySelect = document.getElementById('category-select');
const sortSelect = document.getElementById('sort-select');
const statusTabs = document.querySelectorAll('.filter-tab');
const priorityTabs = document.querySelectorAll('.priority-tab');

const storiesGrid = document.getElementById('stories-grid');
const feedCount = document.getElementById('feed-count');
const feedLoader = document.getElementById('feed-loader');
const emptyState = document.getElementById('empty-state');

// Stats Elements
const statTotalArticles = document.getElementById('stat-total-articles');
const statUniqueEvents = document.getElementById('stat-unique-events');
const statHighPriority = document.getElementById('stat-high-priority');
const statMediumPriority = document.getElementById('stat-medium-priority');
const statRejected = document.getElementById('stat-rejected');

// Sidebar Research Elements
const sidebarResearchQueue = document.getElementById('sidebar-research-queue');
const processResearchBtn = document.getElementById('process-research-btn');
const researchQueueSpinner = document.getElementById('research-queue-spinner');

// Modal Elements
const detailModal = document.getElementById('detail-modal');
const modalClose = document.getElementById('modal-close');
const modalTitle = document.getElementById('modal-title');
const modalFinalScore = document.getElementById('modal-final-score');
const modalImportance = document.getElementById('modal-importance');
const modalPostability = document.getElementById('modal-postability');
const modalConfidence = document.getElementById('modal-confidence');
const modalCategory = document.getElementById('modal-category');
const modalEventType = document.getElementById('modal-event-type');
const modalCompany = document.getElementById('modal-company');
const modalSummary = document.getElementById('modal-summary');
const modalSourceCount = document.getElementById('modal-source-count');

const modalEntitiesCompanies = document.getElementById('modal-entities-companies');
const modalEntitiesSectors = document.getElementById('modal-entities-sectors');
const modalEntitiesCountries = document.getElementById('modal-entities-countries');
const modalEntitiesPeople = document.getElementById('modal-entities-people');
const modalEntitiesPeopleRow = document.getElementById('modal-entities-people-row');
const modalSourcesList = document.getElementById('modal-sources-list');

// Table Breakdown Elements
const tableMarketImpact = document.getElementById('table-market-impact');
const tableFinancialSig = document.getElementById('table-financial-sig');
const tableNovelty = document.getElementById('table-novelty');
const tableAudienceInterest = document.getElementById('table-audience-interest');
const tableDiscussionPotential = document.getElementById('table-discussion-potential');
const tableSourceConfidence = document.getElementById('table-source-confidence');
const tableWeightedImportance = document.getElementById('table-weighted-importance');
const tableTotalImportance = document.getElementById('table-total-importance');
const weightedImportanceFinal = document.getElementById('weighted-importance-final');
const tablePostability = document.getElementById('table-postability');
const weightedPostabilityFinal = document.getElementById('weighted-postability-final');
const tableConfidence = document.getElementById('table-confidence');
const weightedConfidenceFinal = document.getElementById('weighted-confidence-final');
const tableGrandTotal = document.getElementById('table-grand-total');

// Modal Research Panel Elements
const modalResearchBtn = document.getElementById('modal-research-btn');
const modalResearchSpinner = document.getElementById('modal-research-spinner');
const modalResearchAgainBtn = document.getElementById('modal-research-again-btn');
const modalResearchAgainSpinner = document.getElementById('modal-research-again-spinner');
const modalResearchStatus = document.getElementById('modal-research-status');
const modalResearchReportContent = document.getElementById('modal-research-report-content');
const modalMarkReviewedBtn = document.getElementById('modal-mark-reviewed-btn');
const modalMarkNeedsReviewBtn = document.getElementById('modal-mark-needs-review-btn');

// Initial Setup
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    refreshDashboard();
});

// Event Listeners Registration
function initEventListeners() {
    // Collect News trigger
    collectBtn.addEventListener('click', handleCollectNews);

    // Process Stories trigger
    processBtn.addEventListener('click', handleProcessStories);

    // Process Research Queue trigger
    processResearchBtn.addEventListener('click', handleProcessResearchQueue);

    // Category Filter Change
    categorySelect.addEventListener('change', (e) => {
        currentCategory = e.target.value;
        fetchStories();
    });

    // Sorting select Change
    sortSelect.addEventListener('change', (e) => {
        currentSort = e.target.value;
        fetchStories();
    });

    // Status Filter Tabs
    statusTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            statusTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentStatus = tab.getAttribute('data-status');
            fetchStories();
        });
    });

    // Priority Filter Tabs
    priorityTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            priorityTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentPriority = tab.getAttribute('data-priority');
            fetchStories();
        });
    });

    // Modal Close
    modalClose.addEventListener('click', () => {
        detailModal.classList.add('hidden');
        activeStoryId = null;
    });

    // Click outside modal content closes it
    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) {
            detailModal.classList.add('hidden');
            activeStoryId = null;
        }
    });

    // Modal Research Button Click
    modalResearchBtn.addEventListener('click', () => handleRunResearch(false));
    modalResearchAgainBtn.addEventListener('click', () => handleRunResearch(true));

    // Mark reviewed / needs review buttons
    modalMarkReviewedBtn.addEventListener('click', () => updateResearchStatus('COMPLETED'));
    modalMarkNeedsReviewBtn.addEventListener('click', () => updateResearchStatus('NEEDS_REVIEW'));

    // Event delegation on story cards
    storiesGrid.addEventListener('click', async (e) => {
        const target = e.target.closest('button');
        if (!target) return;

        const action = target.getAttribute('data-action');
        // Story IDs are opaque strings (Firestore uses random alphanumeric
        // document IDs in production; SQLite uses integers locally) — never
        // coerce with parseInt, or every Firestore-backed story ID becomes NaN.
        const storyId = target.getAttribute('data-id');

        if (action === 'approve') {
            await handleApprove(storyId);
        } else if (action === 'reject') {
            await handleReject(storyId);
        } else if (action === 'details') {
            handleDetails(storyId);
        }
    });
}

// Refresh statistics, story feed list, and research queue
function refreshDashboard() {
    fetchStats();
    fetchStories();
    fetchResearchQueue();
}

// Fetch stats counts
async function fetchStats() {
    try {
        const response = await fetch('/api/stats', { cache: 'no-store' });
        if (!response.ok) throw new Error('Stats fetch failed');
        const stats = await response.json();
        
        statTotalArticles.textContent = stats.total_articles;
        statUniqueEvents.textContent = stats.unique_events;
        statHighPriority.textContent = stats.high_priority;
        statMediumPriority.textContent = stats.medium_priority;
        statRejected.textContent = stats.rejected;
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
}

// Fetch stories list
async function fetchStories() {
    try {
        showFeedLoader(true);
        let url = `/api/stories?status=${currentStatus}&priority=${currentPriority}&sort_by=${currentSort}`;
        if (currentCategory) {
            url += `&category=${currentCategory}`;
        }

        const response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) throw new Error('Stories fetch failed');
        loadedStories = await response.json();

        renderStories(loadedStories);
    } catch (err) {
        console.error('Error fetching stories:', err);
        showToast('Failed to load stories feed', 'error');
    } finally {
        showFeedLoader(false);
    }
}

// Fetch research queue
async function fetchResearchQueue() {
    try {
        const response = await fetch('/api/research/queue?min_importance=70&min_postability=75&limit=8', { cache: 'no-store' });
        if (!response.ok) throw new Error('Research queue fetch failed');
        const queue = await response.json();
        
        renderResearchQueue(queue);
    } catch (err) {
        console.error('Error fetching research queue:', err);
    }
}

// Render the Sidebar Research Queue items
function renderResearchQueue(queue) {
    sidebarResearchQueue.innerHTML = '';
    
    if (queue.length === 0) {
        sidebarResearchQueue.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 0.5rem 0;">No eligible stories in queue</div>`;
        return;
    }

    queue.forEach(story => {
        const item = document.createElement('div');
        item.style.display = 'flex';
        item.style.justifyContent = 'space-between';
        item.style.alignItems = 'center';
        item.style.padding = '0.4rem';
        item.style.background = 'rgba(255, 255, 255, 0.02)';
        item.style.borderRadius = '4px';
        item.style.border = '1px solid rgba(255, 255, 255, 0.05)';
        
        item.innerHTML = `
            <div style="flex: 1; min-width: 0; padding-right: 0.5rem;">
                <div style="font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${story.title}</div>
                <div style="font-size: 0.7rem; color: var(--text-muted);">Rank: ${story.final_score} | Imp: ${story.importance_score}</div>
            </div>
            <button class="btn btn-primary" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;" onclick="handleSidebarResearch('${story.id}')">Research</button>
        `;
        sidebarResearchQueue.appendChild(item);
    });
}

// Handle Sidebar inline research click
async function handleSidebarResearch(storyId) {
    try {
        showToast('Initiating research crawler...', 'info');
        const response = await fetch(`/api/stories/${storyId}/research`, { method: 'POST' });
        if (!response.ok) throw new Error('Research trigger failed');
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast(`Research completed with status: ${result.research_status}`, 'success');
            refreshDashboard();
        } else {
            showToast('Research pipeline run failed.', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Error executing story research', 'error');
    }
}

// Render dynamic card items
function renderStories(stories) {
    storiesGrid.innerHTML = '';
    feedCount.textContent = `${stories.length} event${stories.length === 1 ? '' : 's'}`;

    if (stories.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }
    emptyState.classList.add('hidden');

    stories.forEach(story => {
        const card = document.createElement('article');
        card.className = 'story-card';
        
        // Formulate score badges
        let scoreBadgeClass = 'importance-low';
        let finalScore = story.final_score || 0;
        if (finalScore >= 75) {
            scoreBadgeClass = 'importance-high';
        } else if (finalScore >= 40) {
            scoreBadgeClass = 'importance-med';
        }

        // Status tags
        let statusClass = 'status-new';
        if (story.status === 'APPROVED') statusClass = 'status-approved';
        if (story.status === 'REJECTED') statusClass = 'status-rejected';
        if (story.status === 'FILTERED') statusClass = 'status-filtered';

        // Format Date
        const pubDate = new Date(story.published_at);
        const formattedDate = pubDate.toLocaleDateString(undefined, { 
            month: 'short', 
            day: 'numeric', 
            hour: '2-digit', 
            minute: '2-digit' 
        });

        // Source article links
        const sourcesCount = story.sources ? story.sources.length : 1;

        // Check if report status exists
        let researchBadge = '';
        if (story.research_report) {
            const rStatus = story.research_report.status;
            let badgeColor = 'rgba(255,255,255,0.05)';
            if (rStatus === 'COMPLETED') badgeColor = 'rgba(0, 230, 118, 0.15)';
            if (rStatus === 'NEEDS_REVIEW') badgeColor = 'rgba(255, 82, 82, 0.15)';
            if (rStatus === 'RESEARCHING') badgeColor = 'rgba(124, 77, 255, 0.15)';
            
            researchBadge = `<span style="font-size:0.7rem; background:${badgeColor}; padding:0.1rem 0.4rem; border-radius:4px; margin-left:0.5rem; text-transform:uppercase; font-weight:600;">🔬 ${rStatus}</span>`;
        }

        card.innerHTML = `
            <div class="card-header">
                <div class="card-meta">
                    <span class="category-tag">${story.category}</span>
                    ${story.event_type ? `<span class="event-tag">${story.event_type}</span>` : ''}
                    <span class="pub-time">${formattedDate}</span>
                    ${researchBadge}
                </div>
                <span class="status-badge ${statusClass}">${story.status}</span>
            </div>
            
            <h3 class="story-title">${story.title}</h3>
            <p class="story-summary">${story.summary || 'No summary description available for this story.'}</p>
            
            <!-- Scores Block -->
            <div class="card-scores-row">
                <div class="card-score-item">
                    <span class="card-score-lbl">Weighted Rank</span>
                    <span class="card-score-val ${scoreBadgeClass}">${finalScore}</span>
                </div>
                <div class="card-score-item">
                    <span class="card-score-lbl">Importance</span>
                    <span class="card-score-val">${story.importance_score || 0}</span>
                </div>
                <div class="card-score-item">
                    <span class="card-score-lbl">Postability</span>
                    <span class="card-score-val">${story.postability_score || 0}</span>
                </div>
                <div class="card-score-item">
                    <span class="card-score-lbl">Confidence</span>
                    <span class="card-score-val">${story.confidence_score || 0}</span>
                </div>
            </div>

            <div class="card-sources">
                Primary Company: <strong>${story.company || 'Generic'}</strong> | Sources count: <strong>${sourcesCount}</strong>
            </div>
            
            <div class="card-actions">
                <button class="btn btn-secondary" data-action="details" data-id="${story.id}">View Details</button>
                ${story.status !== 'APPROVED' ? `
                    <button class="btn btn-secondary" data-action="approve" data-id="${story.id}">Approve</button>
                ` : ''}
                ${story.status !== 'REJECTED' ? `
                    <button class="btn btn-danger" data-action="reject" data-id="${story.id}">Reject</button>
                ` : ''}
            </div>
        `;
        storiesGrid.appendChild(card);
    });
}

// Trigger Manual collection crawl
async function handleCollectNews() {
    try {
        setCollectLoading(true);
        showToast('Initiating news collector sync...', 'info');

        const response = await fetch('/api/collect', { method: 'POST' });
        if (!response.ok) throw new Error('Collection failed');
        const result = await response.json();

        if (result.status === 'success') {
            showToast(`Sync completed! Found ${result.new_stories} new articles.`, 'success');
            refreshDashboard();
        } else {
            showToast('Sync completed with errors.', 'error');
        }
    } catch (err) {
        console.error('Error in sync:', err);
        showToast('Error crawling news sources', 'error');
    } finally {
        setCollectLoading(false);
    }
}

// Trigger Manual Pipeline Processing
async function handleProcessStories() {
    try {
        setProcessLoading(true);
        showToast('Running classifier and scoring calculations...', 'info');

        const response = await fetch('/api/process', { method: 'POST' });
        if (!response.ok) throw new Error('Processing failed');
        const result = await response.json();

        if (result.status === 'success') {
            showToast(`Story processing completed! Evaluated ${result.processed_count} stories.`, 'success');
            refreshDashboard();
        } else {
            showToast('Processing completed with errors.', 'error');
        }
    } catch (err) {
        console.error('Error in processing:', err);
        showToast('Error processing story pipeline', 'error');
    } finally {
        setProcessLoading(false);
    }
}

// Trigger Batch Research Queue Process
async function handleProcessResearchQueue() {
    try {
        setResearchQueueLoading(true);
        showToast('Running research queue calculations (stateless concurrency)...', 'info');
        
        const response = await fetch('/api/research/process?concurrency=3', { method: 'POST' });
        if (!response.ok) throw new Error('Queue processing failed');
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast(`Research queue run complete! Researched ${result.processed_count} stories.`, 'success');
            refreshDashboard();
            
            // If details modal is open on the same story, refresh it
            if (activeStoryId) {
                handleDetails(activeStoryId);
            }
        } else {
            showToast('Failed to process research queue.', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Error processing research queue', 'error');
    } finally {
        setResearchQueueLoading(false);
    }
}

// Execute Research on Single Story (via details modal)
async function handleRunResearch(isRerun = false) {
    if (!activeStoryId) return;
    try {
        setModalResearchLoading(true, isRerun);
        showToast(isRerun ? 'Rerunning complete research...' : 'Crawling and extracting facts...', 'info');
        
        const url = isRerun ? `/api/stories/${activeStoryId}/research-again` : `/api/stories/${activeStoryId}/research`;
        const response = await fetch(url, { method: 'POST' });
        if (!response.ok) throw new Error('Research request failed');
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast(`Research completed (Status: ${result.research_status})`, 'success');
            refreshDashboard();
            
            // Reload details to display report
            handleDetails(activeStoryId);
        } else {
            showToast('Research run failed.', 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Error executing automated research', 'error');
    } finally {
        setModalResearchLoading(false, isRerun);
    }
}

// Mock updates for reviewer flags (mark reviewed or needs review)
async function updateResearchStatus(newStatus) {
    showToast(`Story research flagged as ${newStatus}`, 'success');
    modalResearchStatus.textContent = newStatus;
    
    // Auto toggle controls
    if (newStatus === 'COMPLETED') {
        modalMarkReviewedBtn.classList.add('hidden');
        modalMarkNeedsReviewBtn.classList.remove('hidden');
    } else {
        modalMarkReviewedBtn.classList.remove('hidden');
        modalMarkNeedsReviewBtn.classList.add('hidden');
    }
}

// Actions approval / rejections
async function handleApprove(storyId) {
    try {
        const response = await fetch(`/api/stories/${storyId}/approve`, { method: 'POST' });
        if (!response.ok) throw new Error('Approval request failed');
        showToast('Story Approved', 'success');
        refreshDashboard();
    } catch (err) {
        console.error(err);
        showToast('Failed to approve story', 'error');
    }
}

async function handleReject(storyId) {
    try {
        const response = await fetch(`/api/stories/${storyId}/reject`, { method: 'POST' });
        if (!response.ok) throw new Error('Rejection request failed');
        showToast('Story Rejected', 'success');
        refreshDashboard();
    } catch (err) {
        console.error(err);
        showToast('Failed to reject story', 'error');
    }
}

// Simple Markdown parser
function parseMarkdown(md) {
    if (!md) return '';
    let html = md;
    
    // Headers
    html = html.replace(/^# (.*$)/gim, '<h2 style="font-size:1.35rem; margin-top:1.25rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:0.25rem; font-weight:700;">$1</h2>');
    html = html.replace(/^## (.*$)/gim, '<h3 style="font-size:1.1rem; margin-top:1.25rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:0.2rem; color:var(--text-primary); font-weight:600;">$1</h3>');
    html = html.replace(/^### (.*$)/gim, '<h4 style="font-size:0.95rem; margin-top:1rem; color:var(--text-secondary); font-weight:600;">$1</h4>');
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Alerts (GitHub style warnings/notes)
    html = html.replace(/>\s*\[!WARNING\]/gi, '<div style="background:rgba(255, 82, 82, 0.08); border-left:4px solid var(--color-danger); padding:0.75rem 1rem; border-radius:6px; margin:0.75rem 0;"><strong>WARNING:</strong>');
    html = html.replace(/>\s*\[!NOTE\]/gi, '<div style="background:rgba(124, 77, 255, 0.08); border-left:4px solid var(--color-accent); padding:0.75rem 1rem; border-radius:6px; margin:0.75rem 0;"><strong>NOTE:</strong>');
    html = html.replace(/>\s*(.*$)/gim, '$1</div>');
    
    // Inline code
    html = html.replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.08); padding:0.1rem 0.3rem; border-radius:4px; font-family:monospace; color:var(--color-accent-hover);">$1</code>');
    
    // Bullet Lists (basic wrap)
    html = html.replace(/^\-\s+(.*$)/gim, '<li style="margin-left:1.25rem; margin-bottom:0.25rem; list-style-type:disc;">$1</li>');
    
    return html;
}

// Detail View Modal Handler
function handleDetails(storyId) {
    // Compare as strings: the API returns a numeric id under SQLite but a
    // string id under Firestore, while data-id attributes are always strings.
    const story = loadedStories.find(s => String(s.id) === String(storyId));
    if (!story) return;

    activeStoryId = storyId;

    // Set simple details
    modalTitle.textContent = story.title;
    modalFinalScore.textContent = story.final_score || 0;
    modalImportance.textContent = story.importance_score || 0;
    modalPostability.textContent = story.postability_score || 0;
    modalConfidence.textContent = story.confidence_score || 0;
    modalCategory.textContent = story.category;
    modalEventType.textContent = story.event_type || 'OTHER';
    modalCompany.textContent = story.company || 'Generic/None';
    modalSummary.textContent = story.summary || 'No summary description available.';
    
    // Extracted Entities
    modalEntitiesCompanies.innerHTML = '';
    modalEntitiesSectors.innerHTML = '';
    modalEntitiesCountries.innerHTML = '';
    modalEntitiesPeople.innerHTML = '';

    const entities = story.entities || {};
    
    // Companies
    const companies = entities.Companies || [];
    if (companies.length > 0) {
        companies.forEach(c => {
            const pill = document.createElement('span');
            pill.className = 'entity-pill';
            pill.textContent = c;
            modalEntitiesCompanies.appendChild(pill);
        });
    } else {
        modalEntitiesCompanies.innerHTML = '<em>None</em>';
    }

    // Sectors
    const sectors = entities.Sectors || [];
    if (sectors.length > 0) {
        sectors.forEach(s => {
            const pill = document.createElement('span');
            pill.className = 'entity-pill';
            pill.textContent = s;
            modalEntitiesSectors.appendChild(pill);
        });
    } else {
        modalEntitiesSectors.innerHTML = '<em>None</em>';
    }

    // Countries
    const countries = entities.Countries || [];
    if (countries.length > 0) {
        countries.forEach(c => {
            const pill = document.createElement('span');
            pill.className = 'entity-pill';
            pill.textContent = c;
            modalEntitiesCountries.appendChild(pill);
        });
    } else {
        modalEntitiesCountries.innerHTML = '<em>None</em>';
    }

    // People
    const people = entities.People || [];
    if (people.length > 0) {
        modalEntitiesPeopleRow.style.display = 'flex';
        people.forEach(p => {
            const pill = document.createElement('span');
            pill.className = 'entity-pill';
            pill.textContent = p;
            modalEntitiesPeople.appendChild(pill);
        });
    } else {
        modalEntitiesPeopleRow.style.display = 'none';
    }

    // Ranking table calculations
    const breakdown = story.scoring_breakdown || {};
    const imp = story.importance_score || 0;
    const post = story.postability_score || 0;
    const conf = story.confidence_score || 0;

    tableMarketImpact.textContent = breakdown.market_impact || 0;
    tableFinancialSig.textContent = breakdown.financial_significance || 0;
    tableNovelty.textContent = breakdown.novelty || 0;
    tableAudienceInterest.textContent = breakdown.audience_interest || 0;
    tableDiscussionPotential.textContent = breakdown.discussion_potential || 0;
    tableSourceConfidence.textContent = breakdown.source_confidence_sub || 0;
    
    tableTotalImportance.textContent = `${imp} / 100`;
    tableWeightedImportance.textContent = `${(imp * 0.5).toFixed(1)} / 50.0`;
    weightedImportanceFinal.textContent = (imp * 0.5).toFixed(1);

    tablePostability.textContent = `${post} / 100`;
    weightedPostabilityFinal.textContent = (post * 0.35).toFixed(1);

    tableConfidence.textContent = `${conf} / 100`;
    weightedConfidenceFinal.textContent = (conf * 0.15).toFixed(1);

    tableGrandTotal.textContent = `${story.final_score.toFixed(1)} / 100`;

    // Populate Linked Source Lists
    modalSourcesList.innerHTML = '';
    const sources = story.sources || [];
    modalSourceCount.textContent = sources.length;
    
    if (sources.length > 0) {
        sources.forEach((src, idx) => {
            const li = document.createElement('li');
            const formattedDate = new Date(src.published_at).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            li.innerHTML = `${idx + 1}. <strong>[${src.source_name}]</strong>: <a href="${src.url}" target="_blank">${src.title}</a> <span class="pub-time">(${formattedDate})</span>`;
            modalSourcesList.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.innerHTML = `1. <strong>[${story.source_name}]</strong>: <a href="${story.article_url}" target="_blank">${story.title}</a>`;
        modalSourcesList.appendChild(li);
    }

    // --- Research Section Configuration (Milestone 3) ---
    const report = story.research_report;
    if (report) {
        modalResearchStatus.textContent = report.status;
        
        // Style status colors
        if (report.status === 'COMPLETED') {
            modalResearchStatus.className = 'text-success';
        } else if (report.status === 'NEEDS_REVIEW') {
            modalResearchStatus.className = 'text-danger';
        } else if (report.status === 'RESEARCHING') {
            modalResearchStatus.className = 'text-accent';
        } else {
            modalResearchStatus.className = 'text-muted';
        }

        // Render Report body
        if (report.what_happened) {
            modalResearchReportContent.innerHTML = parseMarkdown(report.what_happened);
            modalResearchReportContent.classList.remove('hidden');
        } else {
            modalResearchReportContent.innerHTML = '<em>Research finished but report body was empty.</em>';
            modalResearchReportContent.classList.remove('hidden');
        }

        // Hide run button, show rerun button
        modalResearchBtn.classList.add('hidden');
        modalResearchAgainBtn.classList.remove('hidden');

        // Reviewer controls
        if (report.status === 'NEEDS_REVIEW') {
            modalMarkReviewedBtn.classList.remove('hidden');
            modalMarkNeedsReviewBtn.classList.add('hidden');
        } else if (report.status === 'COMPLETED') {
            modalMarkReviewedBtn.classList.add('hidden');
            modalMarkNeedsReviewBtn.classList.remove('hidden');
        } else {
            modalMarkReviewedBtn.classList.add('hidden');
            modalMarkNeedsReviewBtn.classList.add('hidden');
        }
    } else {
        modalResearchStatus.textContent = 'NOT_RESEARCHED';
        modalResearchStatus.className = 'text-muted';
        modalResearchReportContent.classList.add('hidden');
        
        modalResearchBtn.classList.remove('hidden');
        modalResearchAgainBtn.classList.add('hidden');
        modalMarkReviewedBtn.classList.add('hidden');
        modalMarkNeedsReviewBtn.classList.add('hidden');
    }

    // Display modal
    detailModal.classList.remove('hidden');
}

// UI Helpers
function showFeedLoader(show) {
    if (show) {
        feedLoader.classList.remove('hidden');
    } else {
        feedLoader.classList.add('hidden');
    }
}

function setCollectLoading(loading) {
    if (loading) {
        collectBtn.disabled = true;
        collectSpinner.style.display = 'inline-block';
        collectText.textContent = 'Syncing...';
    } else {
        collectBtn.disabled = false;
        collectSpinner.style.display = 'none';
        collectText.textContent = 'Collect News';
    }
}

function setProcessLoading(loading) {
    if (loading) {
        processBtn.disabled = true;
        processSpinner.style.display = 'inline-block';
        processText.textContent = 'Processing...';
    } else {
        processBtn.disabled = false;
        processSpinner.style.display = 'none';
        processText.textContent = 'Process Stories';
    }
}

function setResearchQueueLoading(loading) {
    if (loading) {
        processResearchBtn.disabled = true;
        researchQueueSpinner.style.display = 'inline-block';
    } else {
        processResearchBtn.disabled = false;
        researchQueueSpinner.style.display = 'none';
    }
}

function setModalResearchLoading(loading, isRerun = false) {
    if (loading) {
        if (isRerun) {
            modalResearchAgainBtn.disabled = true;
            modalResearchAgainSpinner.style.display = 'inline-block';
        } else {
            modalResearchBtn.disabled = true;
            modalResearchSpinner.style.display = 'inline-block';
        }
    } else {
        modalResearchBtn.disabled = false;
        modalResearchSpinner.style.display = 'none';
        modalResearchAgainBtn.disabled = false;
        modalResearchAgainSpinner.style.display = 'none';
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        toast.addEventListener('animationend', () => {
            toast.remove();
        });
    }, 3500);
}
