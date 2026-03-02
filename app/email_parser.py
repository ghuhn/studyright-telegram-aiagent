import imaplib
import email
from email.header import decode_header
import os
import logging
import asyncio
from typing import List, Optional
from pydantic import BaseModel

from app.config import settings
from app.document_parser import parse_document
from app.llm import generate_summary
from app.vector_db import add_document_to_vector_db
from app.database import SessionLocal, User, Notification

logger = logging.getLogger(__name__)

class EmailDocument(BaseModel):
    filename: str
    filepath: str
    subject: str
    sender: str

async def check_for_new_materials(user_id: str) -> List[str]:
    """Check the configured email inbox for new unread materials and process them."""
    if not settings.email_address or not settings.email_app_password:
        return []

    processed_summaries = []
    
    try:
        logger.info(f"Connecting to IMAP server {settings.email_imap_server}...")
        # Connect to the IMAP server (with 15 second timeout to prevent hanging on Render)
        mail = await asyncio.to_thread(imaplib.IMAP4_SSL, settings.email_imap_server, timeout=15)
        
        logger.info("Logging into IMAP...")
        await asyncio.to_thread(mail.login, settings.email_address, settings.email_app_password)
        
        logger.info("Selecting inbox...")
        await asyncio.to_thread(mail.select, "inbox")
        
        logger.info("Searching for unseen messages...")
        # Search for all unread emails
        status, messages = await asyncio.to_thread(mail.search, None, "UNSEEN")
        if status != "OK" or not messages[0]:
            logger.info("No unread emails found.")
            await asyncio.to_thread(mail.logout)
            return []
            
        email_ids = messages[0].split()
        
        for e_id in email_ids:
            logger.info(f"Fetching email ID {e_id}...")
            # Fetch the email by ID
            res, msg_data = await asyncio.to_thread(mail.fetch, e_id, "(RFC822)")
            if res != "OK":
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    # Parse the email content
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Decode the subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                        
                    sender = msg.get("From")
                    logger.info(f"Processing new email from {sender}: {subject}")
                    
                    # Process attachments
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_maintype() == "multipart":
                                continue
                            if part.get("Content-Disposition") is None:
                                continue
                                
                            filename = part.get_filename()
                            if filename:
                                # Decode filename if necessary
                                decoded_filename, encoding = decode_header(filename)[0]
                                if isinstance(decoded_filename, bytes):
                                    filename = decoded_filename.decode(encoding if encoding else "utf-8")
                                    
                                file_ext = os.path.splitext(filename)[1].lower()
                                
                                # Only process PDFs, Word docs, and TXT files
                                if file_ext in [".pdf", ".docx", ".txt"]:
                                    # Save attachment temporarily
                                    filepath = f"temp_email_{filename}"
                                    with open(filepath, "wb") as f:
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            f.write(payload)
                                        
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
                                            
        logger.info("Logging out of IMAP...")
        await asyncio.to_thread(mail.logout)
        return processed_summaries
    except Exception as e:
        logger.exception(f"Error checking emails: {e}")
        return []
