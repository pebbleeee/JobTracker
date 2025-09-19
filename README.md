# Job Application Tracker

## Overview
As a computer science student, applying to hundreds of internships and jobs can quickly become overwhelming. Keeping track of which applications you’ve submitted, which companies have responded, and what stage each application is at is frustrating and time-consuming.

This project automates the process by connecting to your Gmail account, scanning for application-related emails, and compiling them into structured CSV and Excel files. It helps you quickly see confirmations and track your progress.

## Features
- Connects to Gmail via OAuth 2.0
- Fetches emails related to job applications
- Extracts key information: company, job title, date, status, and email preview
- Generates CSV and Excel files for easy tracking
- Filters emails by keywords and date range

## Requirements
- Python 3.x
- Packages: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`, `beautifulsoup4`, `python-dateutil`, `pandas`

## Setup & Commands

Open a terminal in the project folder and run these commands:

```bash
# 1. Clone the repository
git clone https://github.com/pebbleeee/JobTracker.git
cd JobTracker

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the virtual environment
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat

# macOS/Linux
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
# or manually
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib beautifulsoup4 python-dateutil pandas

# 5. Place your credentials.json file in the project folder
