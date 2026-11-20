# Job Matchmaker Agent

The agent reads a CV and ranks live job listings by how close they are to that CV. Keyword overlap is only part of the score. A local language model compares the meaning of the résumé with each posting.

Practice listings ship with the project for offline demos. Remotive, Jobicy, Remote OK, Himalayas, and Working Nomads are the live feeds, and they are on by default.

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Open http://127.0.0.1:7860

Upload a PDF or DOCX résumé and click **Match jobs to this CV**. The form fills with the name, roles, skills, and location read from the file, and the shortlist appears beside it. Edit any field and click **Find matching jobs** to search again. The example buttons still load three practice profiles.

## Check the matcher

```powershell
.\.venv\Scripts\python -m job_matchmaker.demo
.\.venv\Scripts\python -m unittest discover -s tests -v
```

## Email and WhatsApp

```powershell
copy .env.example .env
```

Email uses `smtplib`. For Gmail, use an app password with `SMTP_HOST=smtp.gmail.com` and `SMTP_PORT=587`.

WhatsApp uses a Twilio sandbox number. The recipient has to join that sandbox, and `TWILIO_WHATSAPP_FROM` looks like `whatsapp:+14155238886`.

If those values are empty, the shortlist is still saved under `notifications/`.

## Run it every day

Turn on **Save this search for the daily run** and search once. Then:

```powershell
.\.venv\Scripts\python run_saved.py
.\.venv\Scripts\python run_saved.py --loop
```

`--loop` uses the `schedule` package and repeats at `RUN_AT` (09:00 by default) while the window stays open. Windows Task Scheduler, cron, or cron-job.org can call `run_saved.py` instead.

## What it includes

- A CV reader for PDF, DOCX, and TXT résumés. It pulls the name, contact details, headline roles, skills, and experience level.
- A profile form for name, email, WhatsApp number, location, roles, skills, and experience.
- A fetcher for the sample board, a local HTML board read with BeautifulSoup, and the live Remotive, Jobicy, Remote OK, Himalayas, and Working Nomads feeds.
- A matcher that compares the CV's meaning with each posting, then also scores skills, title, and location. The percentage is how close the listing is to the CV. A high number still needs a human look, because the live boards contain few exact research roles.
- A notification draft, a saved text file, SMTP email, and Twilio WhatsApp.

## Job boards

LinkedIn, Indeed, and Glassdoor do not publish a keyless feed, so this agent does not scrape them. The live boards are Remotive, Jobicy, Remote OK, Himalayas, and Working Nomads. Each live card links back to the original posting. Results are cached for six hours.

Sample board and local HTML board listings are fictional. Do not apply to the example.com links.
