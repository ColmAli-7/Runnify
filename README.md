# Runnify

Analyse how music impacts your running performance.

Runnify is a web application that combines Garmin activity data with Spotify listening history to reveal how different songs influence your pace, heart rate, and overall effort.

## Features

- **Garmin integration** — sync and store running activities automatically
- **Spotify data matching** — match songs to runs using timestamp overlap
- **Performance analysis** — evaluate how each song affects pace and effort
- **Interactive insights** — visualise trends with dynamic charts
- **Leaderboard** — compare total distance with friends

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python) |
| Database | PostgreSQL + SQLAlchemy |
| Frontend | HTML, CSS (Bootstrap), JavaScript |
| Visualisation | Chart.js, Bootstrap |
| APIs | Garmin Connect, Spotify |

## Setup
```bash
git clone https://github.com/yourusername/runnify.git
cd runnify
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```env
SECRET_KEY=your_secret_key
DATABASE_URL=your_postgres_url

FERNET_KEY=your_fernet_key

MAIL_SERVER=your_mail_server
MAIL_PORT=your_mail_port
MAIL_USE_TLS=True/False
MAIL_USERNAME=your_email
MAIL_PASSWORD=your_mail_password
MAIL_DEFAULT_SENDER=your_email
```

Then run:
```bash
flask run
```

## How it works

1. Connect your Garmin account
2. Upload your Spotify extended streaming history
3. Runs and songs are matched by timestamp
4. A performance score is calculated per song
5. Insights are displayed through graphs and statistics

## Notes

> Garmin requests may be rate limited if made too frequently. Spotify extended streaming history must be requested manually via your Spotify account settings.

## Author

Colm Ali
