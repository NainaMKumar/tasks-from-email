from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os

import base64
import email
from bs4 import BeautifulSoup
import html
import quopri
import re
from email_reply_parser import EmailReplyParser

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()
OpenAI.api_key = os.getenv("OPENAI_API_KEY")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def generate_tasks_from_email(combined_text):
    
    # Call OpenAI API to generate tasks
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
        {"role": "system", "content": "You are a helpful assistant that analyzes email content and extracts tasks."},
        {"role": "user", "content": f"Analyze the following email content and links, and extract a list of numbered tasks that I need to do. Please reference the links provided. \n\n{combined_text}\n\nTasks:"}
        ]
    )
    
    # Extract the generated text
    tasks = completion.choices[0].message
    return tasks


def get_latest_email_subject():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # If there are no valid credentials, ask user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=8080)
        
        # Save the credentials for next use
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Connect to Gmail API
    service = build("gmail", "v1", credentials=creds)

    # Get the latest email
    results = service.users().messages().list(userId="me", labelIds = ["INBOX"], maxResults=5).execute()
    messages = results.get("messages", [])

    # if not messages:
    #     print("No emails found.")
        
    combined_text = ""
    for msg in messages: 
        msg_id = msg["id"]
        full_msg = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
        mime_msg = email.message_from_bytes(base64.urlsafe_b64decode(full_msg['raw']))
        
        sender_email = mime_msg["From"]
        email_address = re.search(r"<(.*?)>", sender_email).group(1)
        # print(email_address)

        #check for blocked domains and patterns
        blocked_domains = ["Linkedin.com", "Substack.com", "beehiiv.com"]
        blocked_patterns = ["noreply@", "newsletter@", "updates@", "info@", "no-reply@"]

        if any(domain.lower() in email_address.lower() for domain in blocked_domains) or any(email_address.lower().startswith(p.lower()) for p in blocked_patterns):
            continue
        
        raw_text = ''
        message_main_type = mime_msg.get_content_maintype()
        if message_main_type == 'multipart':
            for part in mime_msg.get_payload():
                if part.get_content_maintype() == 'text':
                    raw_text = part.get_payload()
            
        elif message_main_type == 'text':
            raw_text = mime_msg.get_payload()

        decoded_html = quopri.decodestring(raw_text).decode("utf-8")

        soup = BeautifulSoup(decoded_html, 'html.parser')
        text = soup.get_text(separator = '')
        cleaned_text = html.unescape(text).strip()
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        parsed_text = EmailReplyParser.parse_reply(cleaned_text)
        

        links = [a_tag['href'] for a_tag in soup.find_all('a', href = True)]

        # Print the links found in the email
        # if links:
        #     print(*links, sep = "\n")
        # else:
        #     print("\nNo links found.")
            
        combined_text += f"Here’s the email content:\n\n{parsed_text}\n\nLinks mentioned:\n" + "\n".join(links)

    if combined_text: 
        tasks = generate_tasks_from_email(combined_text)
        formatted_text = re.sub(r"(\d+\.)", r"\n\1", tasks.content)
        print(formatted_text)
    else: 
        print("No relevant emails to process.")
        

    

if __name__ == "__main__":
    get_latest_email_subject()
