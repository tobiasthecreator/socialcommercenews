# Social Commerce News Tracker

A powerful application for collecting, organizing, and analyzing news articles related to social commerce and creator economy topics. This tool is designed to help you stay on top of industry trends and generate insightful weekly newsletters.

## Features

### News Collection

- **Automated Article Collection**: Automatically gather relevant news articles using Google News for your specified keywords.
- **Full Content Storage**: Store complete article content and summaries in a PostgreSQL database for easy access.
- **Flexible Keyword Management**: Add, edit, or disable tracking keywords through an intuitive web interface.

### Strategic Trend Analysis

- **Interactive Dashboards**: Visualize article publication trends, keyword distribution, and top news sources.
- **Trending Keywords**: Identify which topics are gaining traction with percentage change metrics.
- **Hot Topics**: Highlight the most important recent articles for each keyword.

### Newsletter Creation Support

- **ChatGPT Integration**: Export filtered article data in a JSON format optimized for generating newsletters with ChatGPT.
- **CSV Export**: Download article data in CSV format for use in other tools.
- **Flexible Filtering**: Filter articles by keyword and date range to focus on specific topics or timeframes.

## Getting Started

### Setting Up the Application

1. Clone this repository to your local machine or Replit environment.
2. Make sure PostgreSQL is installed and running.
3. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Start the application:
   ```
   python main.py
   ```

### Adding Keywords to Track

1. Navigate to the "Manage Keywords" page from the dashboard.
2. Click "Add New Keyword" and provide:
   - **Name**: Internal identifier (no spaces, use underscores)
   - **Display Name**: The term that will be searched for in news sources

### Collecting Articles

1. From the dashboard, click the "Collect New Articles" button to start gathering news.
2. The application will search for articles related to each of your active keywords.
3. Full article content will be stored in the database for later reference.

### Analyzing Trends

1. Visit the "Trends Analysis" page to see visualizations of your collected data.
2. Filter by different time periods to analyze short or long-term trends.
3. Use the charts and trending keyword metrics to identify emerging topics.

### Creating Newsletters

1. From the "Articles" page, filter the articles by keyword and date range.
2. Use the "Export for ChatGPT" option to download a properly formatted JSON file.
3. Upload this file to ChatGPT to automatically generate newsletter content.

## Scheduled Collection

To automate article collection, you can set up a scheduled task:

### On Linux/Unix (using cron)

```bash
# Add this to your crontab to run daily at 8 AM
0 8 * * * cd /path/to/app && python main.py
```

### On Replit

Use the Replit Cron job feature by adding a secret with key `REPLIT_CRON` and a cron expression as the value:
```
0 8 * * * python main.py
```

## Technology Stack

- **Backend**: Python with Flask
- **Database**: PostgreSQL
- **Web Scraping**: BeautifulSoup and Feedparser
- **Frontend**: Bootstrap CSS with interactive charts using Chart.js
- **Data Visualization**: Chart.js for trends and analytics

## Customization

You can customize the initial keywords by editing the `topics.py` file before first run. After initial setup, use the web interface to manage keywords.