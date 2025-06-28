// Main JavaScript file for Learning Observer Flask App

// Global variables
let currentUser = null;
let currentRole = null;

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
});

function initializeApp() {
    // Check if user is logged in
    const userElement = document.querySelector('[data-user-id]');
    if (userElement) {
        currentUser = userElement.dataset.userId;
        currentRole = userElement.dataset.userRole;
    }

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize file upload areas
    initializeFileUploads();

    // Initialize modals
    initializeModals();
}

function setupEventListeners() {
    // File upload handling
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', handleFileSelect);
    });

    // Form submissions
    const forms = document.querySelectorAll('form[data-async]');
    forms.forEach(form => {
        form.addEventListener('submit', handleAsyncFormSubmit);
    });

    // Auto-refresh for messages
    if (currentRole === 'Parent' || currentRole === 'Observer') {
        setInterval(refreshMessages, 30000); // Refresh every 30 seconds
    }

    // Auto-refresh for dashboard if on observer dashboard
    if (currentRole === 'Observer' && window.location.pathname.includes('/dashboard')) {
        setInterval(refreshScheduleStatus, 300000); // Refresh every 5 minutes
    }
}

function initializeFileUploads() {
    const uploadAreas = document.querySelectorAll('.file-upload-area');

    uploadAreas.forEach(area => {
        area.addEventListener('dragover', handleDragOver);
        area.addEventListener('dragleave', handleDragLeave);
        area.addEventListener('drop', handleFileDrop);
        area.addEventListener('click', () => {
            const fileInput = area.querySelector('input[type="file"]');
            if (fileInput) fileInput.click();
        });
    });
}

function initializeModals() {
    // Initialize email modal if it exists
    const emailModal = document.getElementById('emailModal');
    if (emailModal) {
        window.emailModalInstance = new bootstrap.Modal(emailModal);
    }

    // Initialize schedule modal if it exists
    const scheduleModal = document.getElementById('scheduleModal');
    if (scheduleModal) {
        window.scheduleModalInstance = new bootstrap.Modal(scheduleModal);
    }
}

function handleDragOver(e) {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
}

function handleFileDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');

    const files = e.dataTransfer.files;
    const fileInput = e.currentTarget.querySelector('input[type="file"]');

    if (fileInput && files.length > 0) {
        fileInput.files = files;
        handleFileSelect({ target: fileInput });
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const uploadArea = e.target.closest('.file-upload-area');
    const preview = uploadArea ? uploadArea.querySelector('.file-preview') : null;

    if (preview) {
        preview.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-file me-2"></i>
                Selected: ${file.name} (${formatFileSize(file.size)})
            </div>
        `;
    }

    // Validate file type
    const allowedTypes = e.target.dataset.allowedTypes;
    if (allowedTypes) {
        const types = allowedTypes.split(',');
        const fileType = file.type.split('/')[1];

        if (!types.includes(fileType)) {
            showAlert('Invalid file type. Please select a valid file.', 'danger');
            e.target.value = '';
            return;
        }
    }

    // Validate file size (10MB limit)
    if (file.size > 25 * 1024 * 1024) {
        showAlert('File size too large. Please select a file smaller than 25MB.', 'danger');
        e.target.value = '';
        return;
    }
}

function handleAsyncFormSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const formData = new FormData(form);
    const url = form.action;
    const method = form.method || 'POST';

    showSpinner();

    fetch(url, {
        method: method,
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();

        if (data.success) {
            showAlert(data.message || 'Operation completed successfully!', 'success');

            // Handle specific responses
            if (data.redirect) {
                window.location.href = data.redirect;
            } else if (data.reload) {
                window.location.reload();
            }
        } else {
            showAlert(data.error || 'An error occurred', 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showAlert('Network error occurred', 'danger');
        console.error('Error:', error);
    });
}

// UPDATED: Enhanced custom report generation with improved formatting
function generateCustomReport() {
    const childId = document.getElementById('custom-child-select').value;
    const prompt = document.getElementById('custom-prompt').value;

    if (!childId || !prompt.trim()) {
        showAlert('Please select a child and enter a prompt', 'warning');
        return;
    }

    // Show loading state
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Generating...';
    button.disabled = true;

    showSpinner();

    const formData = new FormData();
    formData.append('child_id', childId);
    formData.append('prompt', prompt);

    fetch('/observer/custom_report', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();

        if (data.success) {
            // Parse JSON response - Enhanced parsing
            let reportData;
            try {
                let reportText = data.report;

                // Extract JSON from code blocks - improved regex
                const jsonMatch = reportText.match(/``````/);
                if (jsonMatch) {
                    reportData = JSON.parse(jsonMatch[1].trim());
                } else {
                    // Try to find JSON object directly
                    const jsonStart = reportText.indexOf('{');
                    const jsonEnd = reportText.lastIndexOf('}');
                    if (jsonStart !== -1 && jsonEnd !== -1) {
                        const jsonString = reportText.substring(jsonStart, jsonEnd + 1);
                        reportData = JSON.parse(jsonString);
                    } else {
                        throw new Error('No JSON found');
                    }
                }
            } catch (e) {
                console.log('Failed to parse JSON, treating as plain text:', e);
                reportData = { observations: data.report };
            }

            // Display the custom report with improved formatting
            const reportSection = document.getElementById('custom-report-section');
            const reportContent = document.getElementById('custom-report-content');

            let reportHtml = '';

            if (typeof reportData === 'object' && reportData.studentName) {
                reportHtml = `
                    <div class="card mb-4">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fas fa-user me-2"></i>Student Information</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <p><strong>Name:</strong> ${reportData.studentName}</p>
                                    <p><strong>Date:</strong> ${reportData.date}</p>
                                </div>
                                <div class="col-md-6">
                                    <p><strong>Report Type:</strong> ${reportData.className}</p>
                                    <p><strong>Student ID:</strong> ${reportData.studentId}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card mb-4">
                        <div class="card-header bg-success text-white">
                            <h5 class="mb-0"><i class="fas fa-eye me-2"></i>Observations</h5>
                        </div>
                        <div class="card-body">
                            <div class="p-3 bg-light rounded" style="line-height: 1.6; text-align: justify;">
                                ${reportData.observations || 'No observations available'}
                            </div>
                        </div>
                    </div>

                    <div class="row mb-4">
                        <div class="col-md-6">
                            <div class="card h-100">
                                <div class="card-header bg-warning text-white">
                                    <h6 class="mb-0"><i class="fas fa-star me-2"></i>Strengths</h6>
                                </div>
                                <div class="card-body">
                                    ${reportData.strengths && reportData.strengths.length > 0 ? `
                                        <div class="strengths-list">
                                            ${reportData.strengths.map(strength => `
                                                <div class="d-flex align-items-start mb-3">
                                                    <i class="fas fa-check-circle text-success me-3 mt-1"></i>
                                                    <span>${strength}</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    ` : '<p class="text-muted"><i class="fas fa-info-circle me-2"></i>No specific strengths data available</p>'}
                                </div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="card h-100">
                                <div class="card-header bg-danger text-white">
                                    <h6 class="mb-0"><i class="fas fa-arrow-up me-2"></i>Areas for Development</h6>
                                </div>
                                <div class="card-body">
                                    ${reportData.areasOfDevelopment && reportData.areasOfDevelopment.length > 0 ? `
                                        <div class="development-list">
                                            ${reportData.areasOfDevelopment.map(area => `
                                                <div class="d-flex align-items-start mb-3">
                                                    <i class="fas fa-arrow-circle-up text-warning me-3 mt-1"></i>
                                                    <span>${area}</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    ` : '<p class="text-muted"><i class="fas fa-info-circle me-2"></i>No specific development areas identified</p>'}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header bg-info text-white">
                            <h5 class="mb-0"><i class="fas fa-lightbulb me-2"></i>Recommendations</h5>
                        </div>
                        <div class="card-body">
                            ${reportData.recommendations && reportData.recommendations.length > 0 ? `
                                <div class="recommendations-list">
                                    ${reportData.recommendations.map((rec, index) => `
                                        <div class="d-flex align-items-start mb-3">
                                            <span class="badge bg-info me-3 mt-1">${index + 1}</span>
                                            <span>${rec}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : '<p class="text-muted">No specific recommendations available</p>'}
                        </div>
                    </div>
                `;
            } else {
                // Fallback for plain text - Clean up the display
                const cleanedText = data.report
                    .replace(/``````/g, '')
                    .replace(/``````/g, '')
                    .trim();

                reportHtml = `
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fas fa-file-alt me-2"></i>Custom Report</h5>
                        </div>
                        <div class="card-body">
                            <div class="formatted-report p-3 bg-light rounded" style="line-height: 1.6; text-align: justify;">
                                ${cleanedText.replace(/\n/g, '<br>')}
                            </div>
                        </div>
                    </div>
                `;
            }

            reportContent.innerHTML = reportHtml;
            reportSection.style.display = 'block';
            reportSection.classList.add('fade-in');

            // Scroll to the report
            reportSection.scrollIntoView({ behavior: 'smooth' });
            showAlert('Custom report generated successfully!', 'success');
        } else {
            showAlert(data.error || 'Failed to generate report', 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showAlert('Error generating report', 'danger');
        console.error('Error:', error);
    })
    .finally(() => {
        button.innerHTML = originalText;
        button.disabled = false;
    });
}

// NEW: Download custom reports
function downloadCustomReport(type) {
    const url = type === 'word' ? '/observer/download_custom_report' : '/observer/download_custom_pdf';
    window.open(url, '_blank');
}

// NEW: Email custom report
function emailCustomReport() {
    showEmailModal('custom');
}

function loadMessages(parentId) {
    fetch(`/observer/get_messages/${parentId}`)
    .then(response => response.json())
    .then(messages => {
        const container = document.getElementById('messages-container');
        if (!container) return;

        container.innerHTML = '';

        messages.forEach(message => {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message-item ${message.sender_id === currentUser ? 'message-sent' : 'message-received'}`;

            messageDiv.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>${message.sender_id === currentUser ? 'You' : 'Parent'}:</strong>
                        <p class="mb-1">${message.content}</p>
                    </div>
                    <small class="text-muted">${formatDateTime(message.timestamp)}</small>
                </div>
            `;

            container.appendChild(messageDiv);
        });

        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    })
    .catch(error => {
        console.error('Error loading messages:', error);
    });
}

function refreshMessages() {
    const messagesContainer = document.getElementById('messages-container');
    if (messagesContainer) {
        const parentSelect = document.getElementById('parent-select');
        if (parentSelect && parentSelect.value) {
            loadMessages(parentSelect.value);
        }
    }
}

// FIXED: Enhanced monthly report generation with proper JSON parsing and display
function generateMonthlyReport() {
    const childId = document.getElementById('monthly-child-select').value;
    const year = document.getElementById('monthly-year').value;
    const month = document.getElementById('monthly-month').value;

    if (!childId || !year || !month) {
        showAlert('Please select all required fields', 'warning');
        return;
    }

    // Show loading state
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Generating...';
    button.disabled = true;

    showSpinner();

    const formData = new FormData();
    formData.append('child_id', childId);
    formData.append('year', year);
    formData.append('month', month);

    fetch('/observer/generate_monthly_report', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();

        if (data.success || data.summary) {
            // Parse JSON summary - Enhanced parsing
            let summaryData;
            try {
                let summaryText = data.summary;

                // Remove "Monthly Summary" prefix if present
                summaryText = summaryText.replace(/^Monthly Summary\s*/i, '');

                // Extract JSON from code blocks
                const jsonMatch = summaryText.match(/``````/);
                if (jsonMatch) {
                    summaryData = JSON.parse(jsonMatch[1].trim());
                } else {
                    // Try to find JSON object directly
                    const jsonStart = summaryText.indexOf('{');
                    const jsonEnd = summaryText.lastIndexOf('}');
                    if (jsonStart !== -1 && jsonEnd !== -1) {
                        const jsonString = summaryText.substring(jsonStart, jsonEnd + 1);
                        summaryData = JSON.parse(jsonString);
                    } else {
                        throw new Error('No JSON found');
                    }
                }
            } catch (e) {
                console.log('Failed to parse JSON, treating as plain text:', e);
                summaryData = { observations: data.summary };
            }

            // Display the monthly report with structured format
            const reportSection = document.getElementById('monthly-report-section');
            const reportContent = document.getElementById('monthly-report-content');

            let reportHtml = '';

            if (typeof summaryData === 'object' && summaryData.studentName) {
                reportHtml = `
                    <div class="card mb-4">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fas fa-user me-2"></i>Student Information</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <p><strong>Name:</strong> ${summaryData.studentName}</p>
                                    <p><strong>Period:</strong> ${summaryData.date}</p>
                                </div>
                                <div class="col-md-6">
                                    <p><strong>Report Type:</strong> ${summaryData.className}</p>
                                    <p><strong>Report ID:</strong> ${summaryData.studentId}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    ${summaryData.monthlyMetrics ? `
                        <div class="card mb-4">
                            <div class="card-header bg-info text-white">
                                <h5 class="mb-0"><i class="fas fa-chart-bar me-2"></i>Monthly Metrics</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-3">
                                        <div class="text-center">
                                            <h4 class="text-primary">${summaryData.monthlyMetrics.totalObservations}</h4>
                                            <small>Total Observations</small>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="text-center">
                                            <h4 class="text-success">${summaryData.monthlyMetrics.completedGoals}</h4>
                                            <small>Completed Goals</small>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="text-center">
                                            <h4 class="text-warning">${summaryData.monthlyMetrics.activeGoals}</h4>
                                            <small>Active Goals</small>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="text-center">
                                            <h4 class="text-info">${summaryData.monthlyMetrics.goalCompletionRate?.toFixed(1) || 0}%</h4>
                                            <small>Completion Rate</small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ` : ''}

                    <div class="card mb-4">
                        <div class="card-header bg-success text-white">
                            <h5 class="mb-0"><i class="fas fa-eye me-2"></i>Monthly Learning Summary</h5>
                        </div>
                        <div class="card-body">
                            <div class="p-3 bg-light rounded" style="max-height: 400px; overflow-y: auto; line-height: 1.6;">
                                ${summaryData.observations || 'No observations summary available'}
                            </div>
                        </div>
                    </div>

                    <div class="row mb-4">
                        <div class="col-md-6">
                            <div class="card h-100">
                                <div class="card-header bg-warning text-white">
                                    <h6 class="mb-0"><i class="fas fa-star me-2"></i>Strengths Observed</h6>
                                </div>
                                <div class="card-body">
                                    ${summaryData.strengths && summaryData.strengths.length > 0 ? `
                                        <ul class="list-unstyled">
                                            ${summaryData.strengths.map(strength => `
                                                <li class="mb-2">
                                                    <i class="fas fa-check-circle text-success me-2"></i>${strength}
                                                </li>
                                            `).join('')}
                                        </ul>
                                    ` : '<p class="text-muted"><i class="fas fa-info-circle me-2"></i>No specific strengths data available for this period</p>'}
                                </div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="card h-100">
                                <div class="card-header bg-danger text-white">
                                    <h6 class="mb-0"><i class="fas fa-arrow-up me-2"></i>Areas for Development</h6>
                                </div>
                                <div class="card-body">
                                    ${summaryData.areasOfDevelopment && summaryData.areasOfDevelopment.length > 0 ? `
                                        <ul class="list-unstyled">
                                            ${summaryData.areasOfDevelopment.map(area => `
                                                <li class="mb-2">
                                                    <i class="fas fa-arrow-circle-up text-warning me-2"></i>${area}
                                                </li>
                                            `).join('')}
                                        </ul>
                                    ` : '<p class="text-muted"><i class="fas fa-info-circle me-2"></i>No specific development areas identified for this period</p>'}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card mb-4">
                        <div class="card-header bg-secondary text-white">
                            <h5 class="mb-0"><i class="fas fa-lightbulb me-2"></i>Recommendations for Next Month</h5>
                        </div>
                        <div class="card-body">
                            ${summaryData.recommendations && summaryData.recommendations.length > 0 ? `
                                <ul>
                                    ${summaryData.recommendations.map(rec => `
                                        <li class="mb-2">${rec}</li>
                                    `).join('')}
                                </ul>
                            ` : '<p class="text-muted">No specific recommendations available</p>'}
                        </div>
                    </div>

                    ${summaryData.learningAnalytics ? `
                        <div class="card mb-4">
                            <div class="card-header bg-dark text-white">
                                <h5 class="mb-0"><i class="fas fa-brain me-2"></i>Learning Analytics</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <p><strong>Engagement Level:</strong> 
                                            <span class="badge bg-${summaryData.learningAnalytics.engagementLevel === 'High' ? 'success' : summaryData.learningAnalytics.engagementLevel === 'Medium' ? 'warning' : 'secondary'} ms-2">
                                                ${summaryData.learningAnalytics.engagementLevel}
                                            </span>
                                        </p>
                                        <p><strong>Learning Velocity:</strong><br>
                                            <small class="text-muted">${summaryData.learningAnalytics.learningVelocity}</small>
                                        </p>
                                        <p><strong>Independence Level:</strong> 
                                            <span class="badge bg-primary ms-2">${summaryData.learningAnalytics.independenceLevel}</span>
                                        </p>
                                    </div>
                                    <div class="col-md-6">
                                        <p><strong>Social Development:</strong><br>
                                            <small class="text-muted">${summaryData.learningAnalytics.socialDevelopment}</small>
                                        </p>
                                        <p><strong>Cognitive Growth:</strong><br>
                                            <small class="text-muted">${summaryData.learningAnalytics.cognitiveGrowth}</small>
                                        </p>
                                        <p><strong>Creativity Index:</strong><br>
                                            <small class="text-muted">${summaryData.learningAnalytics.creativityIndex}</small>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ` : ''}

                    ${summaryData.progressInsights ? `
                        <div class="card mb-4">
                            <div class="card-header bg-info text-white">
                                <h5 class="mb-0"><i class="fas fa-lightbulb me-2"></i>Progress Insights</h5>
                            </div>
                            <div class="card-body">
                                <ul>
                                    ${summaryData.progressInsights.map(insight => `
                                        <li class="mb-2">${insight}</li>
                                    `).join('')}
                                </ul>
                            </div>
                        </div>
                    ` : ''}

                    ${summaryData.suggestedGraphs ? `
                        <div class="card">
                            <div class="card-header bg-purple text-white" style="background-color: #6f42c1 !important;">
                                <h5 class="mb-0"><i class="fas fa-chart-pie me-2"></i>Suggested Visual Analytics</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    ${summaryData.suggestedGraphs.map(graph => `
                                        <div class="col-md-6 mb-3">
                                            <div class="card border-primary">
                                                <div class="card-body">
                                                    <h6 class="card-title text-primary">${graph.title}</h6>
                                                    <p class="card-text small">${graph.description}</p>
                                                    <span class="badge bg-info">${graph.type.replace('_', ' ').toUpperCase()}</span>
                                                    ${graph.insights ? `<br><small class="text-muted mt-2 d-block"><i class="fas fa-info-circle me-1"></i>${graph.insights}</small>` : ''}
                                                </div>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        </div>
                    ` : ''}
                `;
            } else {
                // Fallback display
                const cleanedSummary = data.summary ? data.summary.replace(/``````/g, '').replace(/^Monthly Summary\s*/i, '').trim() : 'Report generated successfully';
                reportHtml = `
                    <div class="card">
                        <div class="card-header">
                            <h5>Monthly Summary</h5>
                        </div>
                        <div class="card-body">
                            <div class="p-3 bg-light rounded">
                                ${cleanedSummary}
                            </div>
                        </div>
                    </div>
                `;
            }

            reportContent.innerHTML = reportHtml;
            reportSection.style.display = 'block';
            reportSection.classList.add('fade-in');

            // Show charts section
            const chartsSection = document.getElementById('monthly-report-display');
            if (chartsSection) {
                chartsSection.style.display = 'block';
            }

            // Update statistics cards if they exist
            if (data.data) {
                const totalObs = document.getElementById('total-observations');
                const activeGoals = document.getElementById('active-goals');
                const strengthAreas = document.getElementById('strength-areas');
                const developmentAreas = document.getElementById('development-areas');

                if (totalObs) totalObs.textContent = data.data.observations_count;
                if (activeGoals) activeGoals.textContent = data.data.goals_count;
                if (strengthAreas) strengthAreas.textContent = Object.keys(data.data.strengths || {}).length;
                if (developmentAreas) developmentAreas.textContent = Object.keys(data.data.development || {}).length;
            }

            // Render charts if available
            if (data.charts && typeof Plotly !== 'undefined') {
                Object.keys(data.charts).forEach(chartType => {
                    if (data.charts[chartType]) {
                        try {
                            const chartData = JSON.parse(data.charts[chartType]);
                            const chartElement = document.getElementById(`${chartType}-chart`);
                            if (chartElement) {
                                Plotly.newPlot(chartElement, chartData.data, chartData.layout, {responsive: true});
                            }
                        } catch (e) {
                            console.error('Error rendering chart:', e);
                        }
                    }
                });
            }

            // Scroll to the report
            reportSection.scrollIntoView({ behavior: 'smooth' });
            showAlert('Monthly report generated successfully!', 'success');
        } else {
            showAlert(data.error || 'Error generating monthly report', 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showAlert('Error generating monthly report', 'danger');
        console.error('Error:', error);
    })
    .finally(() => {
        button.innerHTML = originalText;
        button.disabled = false;
    });
}

// NEW: Download monthly reports
function downloadMonthlyReport(type) {
    const url = type === 'word' ? '/observer/download_monthly_report' : '/observer/download_monthly_pdf';
    window.open(url, '_blank');
}

// NEW: Email monthly report
function emailMonthlyReport() {
    showEmailModal('monthly');
}

// NEW: Enhanced email modal handling for different report types
function showEmailModal(reportType = 'regular') {
    const modal = document.getElementById('emailModal');
    if (modal) {
        // Store report type for use in sendEmail
        modal.setAttribute('data-report-type', reportType);

        // Update modal title based on report type
        const modalTitle = modal.querySelector('.modal-title');
        if (modalTitle) {
            switch(reportType) {
                case 'custom':
                    modalTitle.textContent = 'Email Custom Report';
                    break;
                case 'monthly':
                    modalTitle.textContent = 'Email Monthly Report';
                    break;
                default:
                    modalTitle.textContent = 'Email Report';
            }
        }

        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    }
}

// NEW: Enhanced email sending for different report types
function sendEmail() {
    const email = document.getElementById('recipient-email').value;
    const modal = document.getElementById('emailModal');
    const reportType = modal ? modal.getAttribute('data-report-type') || 'regular' : 'regular';

    if (!email) {
        showAlert('Please enter an email address', 'danger');
        return;
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        showAlert('Please enter a valid email address', 'danger');
        return;
    }

    const formData = new FormData();
    formData.append('recipient_email', email);

    let endpoint = '/observer/email_report';
    if (reportType === 'custom') {
        endpoint = '/observer/email_custom_report';
    } else if (reportType === 'monthly') {
        endpoint = '/observer/email_monthly_report';
    }

    showSpinner();

    fetch(endpoint, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();

        if (data.success) {
            showAlert('Email sent successfully!', 'success');
            if (modal) {
                bootstrap.Modal.getInstance(modal).hide();
            }
            // Clear the email input
            document.getElementById('recipient-email').value = '';
        } else {
            showAlert('Error sending email: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showAlert('Error sending email', 'danger');
        console.error('Error:', error);
    });
}

// NEW: Toast notification system
function showToast(type, message) {
    const toastId = type === 'success' ? 'successToast' : 'errorToast';
    const messageId = type === 'success' ? 'successMessage' : 'errorMessage';

    const messageElement = document.getElementById(messageId);
    const toastElement = document.getElementById(toastId);

    if (messageElement && toastElement) {
        messageElement.textContent = message;
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
    } else {
        // Fallback to alert if toast elements don't exist
        showAlert(message, type === 'success' ? 'success' : 'danger');
    }
}

// NEW: Schedule management functions
function refreshScheduleStatus() {
    fetch('/observer/get_schedule_status')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateScheduleDisplay(data.data);
        }
    })
    .catch(error => {
        console.error('Error refreshing schedule status:', error);
    });
}

function updateScheduleDisplay(scheduleData) {
    // Update summary counts
    const dueCount = scheduleData.filter(s => s.is_due).length;
    const processedCount = scheduleData.filter(s => s.processed_today).length;
    const scheduledCount = scheduleData.filter(s => s.next_scheduled_time).length;

    const dueElement = document.getElementById('due-reports-count');
    const processedElement = document.getElementById('processed-today-count');
    const scheduledElement = document.getElementById('scheduled-count');

    if (dueElement) dueElement.textContent = dueCount;
    if (processedElement) processedElement.textContent = processedCount;
    if (scheduledElement) scheduledElement.textContent = scheduledCount;

    // Update individual cards
    scheduleData.forEach(status => {
        const card = document.querySelector(`[data-child-id="${status.child.id}"]`);
        if (card) {
            updateChildCard(card, status);
        }
    });
}

function updateChildCard(card, status) {
    // Update time display
    const timeElement = card.querySelector('.next-time');
    if (timeElement && status.next_scheduled_time) {
        const time = new Date(status.next_scheduled_time);
        timeElement.textContent = time.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }

    // Update status badge
    const badge = card.querySelector('.badge');
    if (badge) {
        badge.className = 'badge';
        if (status.processed_today) {
            badge.className += ' bg-success';
            badge.innerHTML = '<i class="fas fa-check me-1"></i>Completed Today';
        } else if (status.is_due) {
            badge.className += ' bg-warning text-dark';
            badge.innerHTML = '<i class="fas fa-clock me-1"></i>Due Now';
        } else if (status.next_scheduled_time) {
            badge.className += ' bg-secondary';
            badge.innerHTML = '<i class="fas fa-calendar me-1"></i>Scheduled';
        } else {
            badge.className += ' bg-light text-dark';
            badge.innerHTML = '<i class="fas fa-question me-1"></i>No Schedule';
        }
    }

    // Update card border
    card.className = card.className.replace(/border-(warning|success|secondary)/g, '');
    if (status.is_due) {
        card.classList.add('border-warning');
    } else if (status.processed_today) {
        card.classList.add('border-success');
    } else {
        card.classList.add('border-secondary');
    }

    // Update process button
    const processBtn = card.querySelector('.process-report-btn');
    if (processBtn) {
        processBtn.style.display = status.can_process ? 'inline-block' : 'none';
    }
}

// NEW: Schedule modal functions
function showScheduleModal(childId, childName, currentTime) {
    const modal = document.getElementById('scheduleModal');
    if (modal) {
        document.getElementById('schedule-child-id').value = childId;
        document.getElementById('schedule-child-name').value = childName;
        document.getElementById('scheduled-time').value = currentTime || '';

        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    }
}

function saveSchedule() {
    const childId = document.getElementById('schedule-child-id').value;
    const scheduledTime = document.getElementById('scheduled-time').value;

    if (!scheduledTime) {
        showAlert('Please select a time', 'danger');
        return;
    }

    const formData = new FormData();
    formData.append('child_id', childId);
    formData.append('scheduled_time', scheduledTime);

    fetch('/observer/set_schedule', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const modal = document.getElementById('scheduleModal');
            if (modal) {
                bootstrap.Modal.getInstance(modal).hide();
            }
            refreshScheduleStatus();
            showAlert('Schedule updated successfully', 'success');
        } else {
            showAlert('Error updating schedule: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        showAlert('Error updating schedule', 'danger');
        console.error('Error:', error);
    });
}

// Utility functions
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-triangle' : type === 'warning' ? 'exclamation-circle' : 'info-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    const container = document.querySelector('.container-fluid') || document.body;
    container.insertBefore(alertDiv, container.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function showSpinner() {
    // Remove existing spinner if any
    hideSpinner();

    const spinner = document.createElement('div');
    spinner.className = 'spinner-overlay';
    spinner.innerHTML = `
        <div class="d-flex justify-content-center align-items-center h-100">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;
    spinner.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        z-index: 9999;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    document.body.appendChild(spinner);
}

function hideSpinner() {
    const spinner = document.querySelector('.spinner-overlay');
    if (spinner) {
        spinner.remove();
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// UPDATED: Enhanced download report function
function downloadReport(format = 'docx') {
    const url = format === 'pdf' ? '/observer/download_pdf' : '/observer/download_report';
    window.open(url, '_blank');
}

// Export functions for global use
window.generateCustomReport = generateCustomReport;
window.downloadCustomReport = downloadCustomReport;
window.emailCustomReport = emailCustomReport;
window.loadMessages = loadMessages;
window.generateMonthlyReport = generateMonthlyReport;
window.downloadMonthlyReport = downloadMonthlyReport;
window.emailMonthlyReport = emailMonthlyReport;
window.downloadReport = downloadReport;
window.showEmailModal = showEmailModal;
window.sendEmail = sendEmail;
window.showToast = showToast;
window.refreshScheduleStatus = refreshScheduleStatus;
window.showScheduleModal = showScheduleModal;
window.saveSchedule = saveSchedule;
