import os
import base64
import logging
import asyncio
from typing import List
from pydantic import BaseModel

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from app.document_parser import parse_document
from app.llm import generate_summary
from app.vector_db import add_document_to_vector_db
from app.database import SessionLocal, User, Notification

logger = logging.getLogger(__name__)

# Scopes required to read Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class EmailDocument(BaseModel):
    filename: str
    filepath: str
    subject: str
    sender: str

def get_gmail_service():
    """Authenticate and return the Gmail API service."""
    creds = None
    # token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, we cannot proceed in background worker
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google Gmail token...")
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        else:
            logger.error("No valid token.json found. You must run setup_google_auth.py locally first.")
            return None
            
    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        return None

async def check_for_new_materials(user_id: str) -> List[str]:
    """Check Gmail inbox via API for new unread materials and process them."""
    processed_summaries = []
    
    try:
        logger.info("Connecting to Gmail API...")
        # API calls can block, wrap the service build in a thread
        service = await asyncio.to_thread(get_gmail_service)
        
        if not service:
            return []

        logger.info("Searching for unseen messages...")
        # Search for unread emails only
        results = await asyncio.to_thread(
            lambda: service.users().messages().list(userId='me', q="is:unread").execute()
        )
        
        messages = results.get('messages', [])
        
        if not messages:
            logger.info("No unread emails found.")
            return []

        for msg_stub in messages:
            msg_id = msg_stub['id']
            logger.info(f"Fetching email ID {msg_id}...")
            
            # Fetch the full email metadata and payload
            msg_data = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id).execute()
            )
            
            payload = msg_data.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = "No Subject"
            sender = "Unknown Sender"
            
            for header in headers:
                name = header.get('name')
                if name == 'Subject':
                    subject = header.get('value')
                elif name == 'From':
                    sender = header.get('value')
                    
            logger.info(f"Processing new email from {sender}: {subject}")
            
            # Parts contain the attachments
            parts = payload.get('parts', [])
            
            for part in parts:
                filename = part.get('filename')
                mimeType = part.get('mimeType')
                body = part.get('body', {})
                
                # Check if it is an attachment with an actual filename
                if filename and body and 'attachmentId' in body:
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    # Only process PDFs, Word docs, and TXT files
                    if file_ext in [".pdf", ".docx", ".txt"]:
                        # Fetch the actual attachment binary data
                        att_id = body['attachmentId']
                        att = await asyncio.to_thread(
                            lambda: service.users().messages().attachments().get(
                                userId='me', messageId=msg_id, id=att_id).execute()
                        )
                        
                        file_data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
                        
                        # Save attachment temporarily
                        filepath = f"temp_email_{filename}"
                        with open(filepath, "wb") as f:
                            f.write(file_data)
                            
                        try:
                            # Parse document
                            extracted_text = parse_document(filepath)
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                
                            if extracted_text.strip():
                                # Truncate text if it's extremely long for the prompt
                                process_text = extracted_text
                                if len(process_text) > 20000:
                                    process_text = process_text[:20000] + "... [truncated]"
                                    
                                # Generate summary
                                summary = await generate_summary(process_text)
                                
                                # Add to vector DB
                                add_document_to_vector_db(user_id, filename, process_text)
                                
                                # Log Notification
                                db = SessionLocal()
                                try:
                                    db_user = db.query(User).filter(User.telegram_id == user_id).first()
                                    if db_user:
                                        notif = Notification(
                                            user_id=db_user.id,
                                            message=f"📧 Received document from email: {filename} (Sender: {sender})"
                                        )
                                        db.add(notif)
                                        db.commit()
                                except Exception as e:
                                    logger.error(f"Error saving email notification: {e}")
                                finally:
                                    db.close()
                                
                                result = f"📥 **New document received via Email:** {filename}\n*From: {sender}*\n\n**📝 Summary:**\n{summary}"
                                processed_summaries.append(result)
                                logger.info(f"Successfully processed email attachment: {filename}")
                        except Exception as e:
                            logger.error(f"Error processing email attachment {filename}: {e}")
                            if os.path.exists(filepath):
                                os.remove(filepath)
            
            # Finally, mark the email as READ by removing the UNREAD label
            try:
                await asyncio.to_thread(
                    lambda: service.users().messages().modify(
                        userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                )
                logger.info(f"Marked email {msg_id} as read.")
            except Exception as mark_e:
                logger.error(f"Failed to mark email as read: {mark_e}")
                                
        return processed_summaries
    except Exception as e:
        logger.exception(f"Error checking emails via Gmail API: {e}")
        return []

