/**
 * Dashboard JavaScript for Doctor metrics visualization
 */

let actionChart = null;
let modelChart = null;

async function fetchDoctorStats() {
    try {
        const response = await fetch('/api/doctor-stats');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error('Error fetching Doctor stats:', error);
    }
}

function updateDashboard(data) {
    // Update metric cards
    document.getElementById('totalCalls').textContent = data.total_calls || 0;
    document.getElementById('cheapCalls').textContent = data.cheap_vs_strong?.cheap || 0;
    document.getElementById('strongCalls').textContent = data.cheap_vs_strong?.strong || 0;
    document.getElementById('escalationRate').textContent = 
        (data.escalation_frequency || 0).toFixed(1) + '%';
    
    // Update action distribution chart
    updateActionChart(data.action_distribution || {});
    
    // Update model usage chart
    updateModelChart(data.cheap_vs_strong || {});
}

function updateActionChart(actions) {
    const ctx = document.getElementById('actionChart').getContext('2d');
    
    if (actionChart) {
        actionChart.destroy();
    }
    
    const labels = Object.keys(actions);
    const values = Object.values(actions);
    
    actionChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#667eea',
                    '#764ba2',
                    '#f093fb',
                    '#4facfe',
                    '#43e97b'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true
        }
    });
}

function updateModelChart(modelData) {
    const ctx = document.getElementById('modelChart').getContext('2d');
    
    if (modelChart) {
        modelChart.destroy();
    }
    
    modelChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Cheap Models', 'Strong Models'],
            datasets: [{
                data: [modelData.cheap || 0, modelData.strong || 0],
                backgroundColor: ['#43e97b', '#667eea']
            }]
        }
    });
}

// Fetch stats on page load and refresh every 5 seconds
fetchDoctorStats();
setInterval(fetchDoctorStats, 5000);
