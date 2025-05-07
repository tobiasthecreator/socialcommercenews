// Global Chart.js instances
let trendsChart = null;
let latestValuesChart = null;

// Chart colors
const chartColors = [
    '#4285F4', // Google Blue
    '#EA4335', // Google Red
    '#FBBC05', // Google Yellow
    '#34A853', // Google Green
    '#8E24AA', // Purple
    '#00ACC1', // Cyan
    '#FB8C00', // Orange
    '#607D8B'  // Blue Grey
];

// Format the date to be more readable
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Show alert message
function showAlert(message, type = 'success') {
    const alertContainer = document.getElementById('alertContainer');
    const alertElement = document.createElement('div');
    alertElement.className = `alert alert-${type} alert-dismissible fade show`;
    alertElement.role = 'alert';
    alertElement.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    alertContainer.appendChild(alertElement);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertElement.classList.remove('show');
        setTimeout(() => {
            alertContainer.removeChild(alertElement);
        }, 150);
    }, 5000);
}

// Process data for chart display
function processChartData(rawData) {
    if (!rawData || rawData.length === 0) {
        return {
            dates: [],
            datasets: []
        };
    }

    // Get unique dates and topics
    const dates = [...new Set(rawData.map(item => item.Date))].sort();
    const topics = [...new Set(rawData.map(item => item.Topic))];
    
    // Prepare datasets for Chart.js
    const datasets = topics.map((topic, index) => {
        const topicData = rawData.filter(item => item.Topic === topic);
        const dataPoints = dates.map(date => {
            const point = topicData.find(item => item.Date === date);
            return point ? point.Interest : null;
        });
        
        return {
            label: topic.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()),
            data: dataPoints,
            backgroundColor: chartColors[index % chartColors.length],
            borderColor: chartColors[index % chartColors.length],
            fill: false,
            tension: 0.2
        };
    });
    
    return {
        dates,
        datasets
    };
}

// Initialize and render the main trends chart
function initTrendsChart(chartData) {
    const ctx = document.getElementById('trendsChart').getContext('2d');
    
    if (trendsChart) {
        trendsChart.destroy();
    }
    
    trendsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.dates,
            datasets: chartData.datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Social Commerce Interest Trends Over Time'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                legend: {
                    position: 'top'
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Interest (0-100)'
                    },
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

// Initialize and render the latest values bar chart
function initLatestValuesChart(chartData) {
    // Get the latest date
    const latestDate = chartData.dates[chartData.dates.length - 1];
    
    // Get data for the latest date
    const latestValues = chartData.datasets.map(dataset => {
        return {
            label: dataset.label,
            value: dataset.data[dataset.data.length - 1] || 0,
            color: dataset.backgroundColor
        };
    });
    
    const ctx = document.getElementById('latestValuesChart').getContext('2d');
    
    if (latestValuesChart) {
        latestValuesChart.destroy();
    }
    
    latestValuesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: latestValues.map(item => item.label),
            datasets: [{
                label: `Interest on ${formatDate(latestDate) || 'Latest Date'}`,
                data: latestValues.map(item => item.value),
                backgroundColor: latestValues.map(item => item.color),
                borderColor: latestValues.map(item => item.color),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Interest (0-100)'
                    }
                }
            }
        }
    });
}

// Update the recent data table
function updateRecentDataTable(data) {
    const tableBody = document.getElementById('recentDataTable');
    tableBody.innerHTML = '';
    
    // Sort data by date (newest first) and take the 10 most recent entries
    const sortedData = [...data].sort((a, b) => new Date(b.Date) - new Date(a.Date)).slice(0, 10);
    
    if (sortedData.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="3" class="text-center">No data available</td>';
        tableBody.appendChild(row);
        return;
    }
    
    sortedData.forEach(item => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatDate(item.Date)}</td>
            <td>${item.Topic.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</td>
            <td>${item.Interest}</td>
        `;
        tableBody.appendChild(row);
    });
}

// Filter chart data based on selected topics
function filterChartData(chartData, selectedTopics) {
    const filteredDatasets = chartData.datasets.filter(dataset => {
        const topicName = dataset.label.toLowerCase().replace(' ', '_');
        return selectedTopics.includes(topicName);
    });
    
    return {
        dates: chartData.dates,
        datasets: filteredDatasets
    };
}

// Update all visualizations with new data
function updateVisualizations(data) {
    const chartData = processChartData(data);
    
    // Get selected topics
    const checkboxes = document.querySelectorAll('.topic-check:checked');
    const selectedTopics = Array.from(checkboxes).map(cb => cb.value);
    
    // Filter data based on selected topics
    const filteredData = filterChartData(chartData, selectedTopics);
    
    // Update charts and table
    initTrendsChart(filteredData);
    initLatestValuesChart(chartData); // Always show all topics in latest values chart
    updateRecentDataTable(data);
}

// Fetch data from the API
async function fetchData() {
    try {
        const response = await fetch('/data');
        if (!response.ok) {
            throw new Error('Failed to fetch data');
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching data:', error);
        showAlert(`Error fetching data: ${error.message}`, 'danger');
        return [];
    }
}

// Update data via API
async function updateData() {
    const updateButton = document.getElementById('updateDataBtn');
    updateButton.classList.add('loading');
    updateButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...';
    
    try {
        const response = await fetch('/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to update data');
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showAlert('Data updated successfully!');
            // Reload data
            const data = await fetchData();
            updateVisualizations(data);
        } else {
            throw new Error(result.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Error updating data:', error);
        showAlert(`Error updating data: ${error.message}`, 'danger');
    } finally {
        updateButton.classList.remove('loading');
        updateButton.textContent = 'Update Data Now';
    }
}

// Initialize the dashboard
async function initDashboard() {
    // Add event listeners for topic checkboxes
    document.querySelectorAll('.topic-check').forEach(checkbox => {
        checkbox.addEventListener('change', async () => {
            const data = await fetchData();
            updateVisualizations(data);
        });
    });
    
    // Add event listener for update button
    document.getElementById('updateDataBtn').addEventListener('click', updateData);
    
    // Initial data load
    const data = await fetchData();
    updateVisualizations(data);
}

// Start the dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', initDashboard);