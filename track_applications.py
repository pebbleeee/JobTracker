#!/usr/bin/env python3
"""
track_applications.py
Manual-run Gmail job-application tracker -> CSV
Requirements:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib beautifulsoup4 python-dateutil
Put credentials.json (OAuth client) in same folder. token.json will be created on first run.
"""

from __future__ import print_function
import os
import base64
import csv
import argparse
import re
from email.utils import parseaddr, parsedate_to_datetime
from dateutil import tz
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_CSV = "applications.csv"

# Heuristic status patterns (lowercase)
STATUS_PATTERNS = {
    "Offer": [r"\boffer\b", r"congratulations.*offer", r"\boffer letter\b"],
    "Interview": [r"\binterview\b", r"\bschedule.*interview\b", r"\bphone screen\b", r"\btechnical interview\b"],
    "Rejected": [r"\bnot selected\b", r"\bwe regret\b", r"\bunfortunately\b", r"\brejected\b"],
    "Submitted": [r"\bapplication received\b", r"\bthank you for applying\b", r"\bapplication submitted\b"],
    "Assessment": [r"\bassess(ment|ment link)\b", r"\bcode challenge\b", r"\bonline test\b"],
}

def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError("credentials.json not found. Place OAuth client file here.")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def search_message_ids(service, query, max_results=500):
    ids = []
    req = service.users().messages().list(userId="me", q=query, maxResults=500)
    while req:
        res = req.execute()
        msgs = res.get("messages", [])
        if not msgs:
            break
        ids.extend([m["id"] for m in msgs])
        page_token = res.get("nextPageToken")
        if page_token:
            req = service.users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=500)
        else:
            break
        if len(ids) >= max_results:
            break
    return ids[:max_results]

def get_message(service, msg_id):
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

def extract_text_from_payload(payload):
    """
    Walk payload parts to get preferably text/plain; fall back to text/html.
    """
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            text = base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8", errors="replace")
            return text
    if mime == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            html = base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8", errors="replace")
            return BeautifulSoup(html, "html.parser").get_text(separator="\n")
    # If multipart, recurse
    for part in payload.get("parts", []) or []:
        text = extract_text_from_payload(part)
        if text:
            return text
    # fallback to snippet
    return None

def header_value(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

def detect_status(text):
    if not text:
        return "Unknown"
    t = text.lower()
    for status, patterns in STATUS_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                return status
    return "Unknown"

def guess_company_from_from(header_from):
    name, email = parseaddr(header_from or "")
    if name and name.strip():
        # sometimes the sender name is the company
        return name.strip()
    if email and "@" in email:
        domain = email.split("@")[-1].lower()
        # remove common subdomains like mail, jobs
        domain = re.sub(r'^(mail|no-reply|noreply|jobs|careers)\.', '', domain)
        # remove tld
        name_part = domain.split(".")[0]
        return name_part.capitalize()
    return ""

def guess_jobtitle_from_subject(subject):
    if not subject:
        return ""
    # try "Application for X", "Applied to X - Role", "Your application: Software Engineer"
    m = re.search(r"(application for|applied for|applied to|your application[:\-]\s*)(.+)", subject, flags=re.I)
    if m:
        # take part to the right, clean
        return m.group(2).strip().strip(" -:")
    # try "Position: Title" or "Role: Title"
    m2 = re.search(r"(position|role|title)[:\-]\s*(.+)", subject, flags=re.I)
    if m2:
        return m2.group(2).strip()
    # fallback: return whole subject if short
    return subject.strip() if len(subject or "") < 120 else subject.strip()[:120]

def parse_message(service, msg_id):
    raw = get_message(service, msg_id)
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])
    subject = header_value(headers, "Subject") or raw.get("snippet", "") or ""
    header_from = header_value(headers, "From") or ""
    header_date = header_value(headers, "Date")
    # convert date to ISO if possible
    try:
        date_dt = parsedate_to_datetime(header_date) if header_date else None
        # normalize to local timezone
        if date_dt and date_dt.tzinfo is None:
            date_dt = date_dt.replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())
        date_iso = date_dt.isoformat() if date_dt else ""
    except Exception:
        date_iso = header_date or ""
    body = extract_text_from_payload(payload) or raw.get("snippet", "")
    preview = (body or "")[:1000].replace("\n", " ").strip()
    status = detect_status((subject or "") + "\n" + (body or ""))
    company = guess_company_from_from(header_from) or ""
    job_title = guess_jobtitle_from_subject(subject)
    # parse sender email
    sender_name, sender_email = parseaddr(header_from or "")
    return {
        "message_id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "date": date_iso,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "company_guess": company,
        "job_title_guess": job_title,
        "status": status,
        "preview": preview,
    }

def write_csv(path, rows, append=False):
    headers = ["message_id","thread_id","date","sender_name","sender_email","subject","company_guess","job_title_guess","status","preview"]
    mode = "a" if append else "w"
    write_header = not (append and os.path.exists(path))
    with open(path, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)

def load_existing_ids(path):
    if not os.path.exists(path):
        return set()
    ids = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("message_id"):
                ids.add(row["message_id"])
    return ids

def main():
    parser = argparse.ArgumentParser(description="Manual-run Gmail job applications tracker")
    parser.add_argument("--query", type=str,
                        default='subject:(application OR "application received" OR applied OR "we received your application" OR interview OR offer OR rejected) OR (from:linkedin.com OR from:indeed.com OR from:jobs@)',
                        help="Gmail query (Gmail search language).")
    parser.add_argument("--max", type=int, default=500, help="Max messages to fetch")
    parser.add_argument("--out", type=str, default=DEFAULT_CSV, help="CSV output file")
    parser.add_argument("--append", action="store_true", help="Append to existing CSV and skip existing message_ids")
    args = parser.parse_args()

    svc = get_gmail_service()
    print("Searching Gmail with query:", args.query)
    ids = search_message_ids(svc, args.query, max_results=args.max)
    print(f"Found {len(ids)} message ids (limited by max={args.max}).")

    existing_ids = load_existing_ids(args.out) if args.append else set()
    to_process = [i for i in ids if i not in existing_ids]
    print(f"{len(to_process)} new messages to process (skipping {len(ids)-len(to_process)} already in CSV).")
    rows = []
    for i, mid in enumerate(to_process, start=1):
        try:
            parsed = parse_message(svc, mid)
            rows.append(parsed)
            if i % 25 == 0:
                print(f"Processed {i}/{len(to_process)}...")
        except Exception as e:
            print(f"Error parsing message {mid}: {e}")

    if rows:
        write_csv(args.out, rows, append=args.append)
        print(f"Wrote {len(rows)} rows to {args.out}.")
    else:
        print("No new rows to write.")

if __name__ == "__main__":
    main()
