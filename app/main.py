import asyncio
import os
import logging
import uvicorn
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from app.config import settings
from app.llm import generate_summary, generate_flashcards, generate_quiz_question, evaluate_quiz_answer
from app.document_parser import parse_document
from app.database import SessionLocal, User, DocumentMetadata, Notification
from app.vector_db import search_documents, clear_user_documents, get_random_document_chunk
from app.rag import answer_question_from_context
from app.email_parser import check_for_new_materials

# Setup logging
import sys
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def send_long_message(update: Update, text: str, **kwargs) -> None:
    """Helper function to split and send messages that exceed Telegram's 4096 character limit."""
    MAX_LENGTH = 4000
    if len(text) <= MAX_LENGTH:
        try:
            await update.message.reply_text(text, **kwargs)
        except BadRequest as e:
            if "parse entities" in str(e).lower():
                safe_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                await update.message.reply_text(text, **safe_kwargs)
            else:
                raise e
        return
        
    # If the text is chunked, we strip markdown explicitly by removing parse_mode
    # because splitting a message mid-markdown string (like **bold**) will crash Telegram.
    safe_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
    
    parts = [text[i:i+MAX_LENGTH] for i in range(0, len(text), MAX_LENGTH)]
    for part in parts:
        await update.message.reply_text(part, **safe_kwargs)

async def send_long_message_context(context: ContextTypes.DEFAULT_TYPE, chat_id: str, text: str, **kwargs) -> None:
    """Helper function to split and send messages via context.bot for background jobs."""
    MAX_LENGTH = 4000
    if len(text) <= MAX_LENGTH:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except BadRequest as e:
            if "parse entities" in str(e).lower():
                safe_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                await context.bot.send_message(chat_id=chat_id, text=text, **safe_kwargs)
            else:
                raise e
        return
        
    safe_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
        
    parts = [text[i:i+MAX_LENGTH] for i in range(0, len(text), MAX_LENGTH)]
    for part in parts:
        await context.bot.send_message(chat_id=chat_id, text=part, **safe_kwargs)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    
    # Save user to DB if not exists
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == str(user.id)).first()
        if not db_user:
            new_user = User(telegram_id=str(user.id), username=user.username)
            db.add(new_user)
            db.commit()
    finally:
        db.close()
        
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I am your AI Study Agent. Send me some text to summarize!",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Help! Here is what I can do:\n"
        "- Send me any text to get a summary.\n"
        "- Upload a PDF, Word doc, or TXT file to get a summary. I will save it to my memory.\n"
        "- Use /subject <topic> to change the current subject folder your documents save to.\n"
        "- Use /flashcards <topic> to generate study flashcards on a topic.\n"
        "- Use /quiz to instantly get a random pop-quiz question based on your notes.\n"
        "- Use /ask <question> to ask a question based on your uploaded documents.\n"
        "- Use /clear to delete all your uploaded documents from my memory.\n"
        "- Use /notifications to manually check your email for new study materials.\n"
        "- Use /notification_history to view a list of recent material uploads.\n"
        "- Use /commands to see this list again.\n"
    )
    await update.message.reply_text(help_text)

async def handle_flashcards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /flashcards command."""
    if not context.args:
        await update.message.reply_text("Please provide a topic. Example: /flashcards Photosynthesis")
        return
        
    topic = " ".join(context.args)
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text(f"📇 Generating flashcards for: {topic}...")
    
    flashcards = await generate_flashcards(f"Topic: {topic}")
    await send_long_message(update, f"**📇 Flashcards:**\n\n{flashcards}", parse_mode="Markdown")

async def handle_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /subject command to switch study contexts."""
    if not context.args:
        await update.message.reply_text("Please provide a subject name. Example: `/subject Mathematics`", parse_mode="Markdown")
        return
        
    subject_name = " ".join(context.args).title()
    user_id = str(update.effective_user.id)
    
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == user_id).first()
        if db_user:
            db_user.active_subject = subject_name
            db.commit()
            await update.message.reply_text(f"📁 Active subject changed to: **{subject_name}**\n\nAll new documents and questions will be saved and searched under this folder.", parse_mode="Markdown")
        else:
            await update.message.reply_text("Please send /start first to register your account.")
    except Exception as e:
        logger.error(f"Error changing subject: {e}")
        await update.message.reply_text("Sorry, there was an error updating your subject.")
    finally:
        db.close()

async def handle_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /ask command by searching the vector DB and generating an answer."""
    if not context.args:
        await update.message.reply_text("Please provide a question. Example: /ask What is mitochondria?")
        return
        
    question = " ".join(context.args)
    user_id = str(update.effective_user.id)
    
    # Get active subject
    db = SessionLocal()
    active_subject = "General"
    try:
        db_user = db.query(User).filter(User.telegram_id == user_id).first()
        if db_user:
            active_subject = db_user.active_subject
    finally:
        db.close()
    
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text(f"🔍 Searching your study materials in **{active_subject}**...", parse_mode="Markdown")
    
    # Search vector DB
    results = await asyncio.to_thread(search_documents, user_id, question, subject=active_subject, n_results=3)
    
    if not results:
        await update.message.reply_text("You haven't uploaded any documents yet, or I couldn't find any relevant information.")
        return
        
    # Combine the top results into context
    context_text = "\n\n---\n\n".join(results)
    
    # Generate the answer using RAG
    answer = await answer_question_from_context(question, context_text)
    
    await send_long_message(update, f"**💡 Answer:**\n\n{answer}", parse_mode="Markdown")

async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all user documents from the vector database."""
    user_id = str(update.effective_user.id)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        deleted_count = await asyncio.to_thread(clear_user_documents, user_id)
        
        # Also delete from SQLite metadata DB
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.telegram_id == user_id).first()
            if db_user:
                db.query(DocumentMetadata).filter(DocumentMetadata.user_id == db_user.id).delete()
                db.commit()
        finally:
            db.close()
            
        if deleted_count > 0:
            await update.message.reply_text(f"🗑️ Successfully deleted {deleted_count} document(s) from my memory.")
        else:
            await update.message.reply_text("Your memory is already empty. I don't have any saved documents for you.")
    except Exception as e:
        logger.error(f"Failed to clear documents: {e}")
        await update.message.reply_text("An error occurred while trying to clear your memory.")

async def handle_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger the email checking job."""
    await update.message.reply_text("🔄 Checking your email for new study materials...")
    await check_email_job(context)

async def handle_notification_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's notification history."""
    user_id = str(update.effective_user.id)
    
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == user_id).first()
        if not db_user:
            await update.message.reply_text("Please send /start first to register your account.")
            return
            
        notifications = db.query(Notification).filter(Notification.user_id == db_user.id).order_by(Notification.created_at.desc()).limit(10).all()
        
        if not notifications:
            await update.message.reply_text("📭 You don't have any recent notifications.")
            return
            
        history_text = "**🔔 Recent Notifications:**\n\n"
        for i, notif in enumerate(notifications):
            date_str = notif.created_at.strftime("%b %d, %H:%M")
            history_text += f"> {i+1}. [{date_str}] {notif.message}\n"
            
        await send_long_message(update, history_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error fetching notification history: {e}")
        await update.message.reply_text("Sorry, there was an error retrieving your notification history.")
    finally:
        db.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages by summarizing them or grading quiz answers."""
    text = update.message.text
    if not text:
        return
        
    # Check if the user is replying to a pop quiz
    if update.message.reply_to_message and update.message.reply_to_message.text:
        replied_text = update.message.reply_to_message.text
        if "Pop Quiz!" in replied_text:
            await update.message.chat.send_action(action="typing")
            # Evaluate the quiz answer
            evaluation = await evaluate_quiz_answer(replied_text, text)
            await send_long_message(update, f"**👨‍🏫 Professor's Feedback:**\n\n{evaluation}", parse_mode="Markdown")
            return
            
    # If it's not a quiz reply, send a typing action and summarize the text
    await update.message.chat.send_action(action="typing")
    
    # Generate the summary
    summary = await generate_summary(text)
    
    # Send the summary back to the user
    await update.message.reply_text(f"**📝 Summary:**\n\n{summary}", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming documents by extracting text and summarizing."""
    document = update.message.document
    if not document:
        return
        
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text("📥 Downloading file...")
    
    # Get the file from Telegram servers
    try:
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{document.file_name}"
        _, file_ext = os.path.splitext(document.file_name)
        await file.download_to_drive(file_path)
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        await update.message.reply_text("There was an error downloading your file. Please try again.")
        return
    
    await update.message.reply_text("🔍 Extracting text and summarizing...")
    
    # Parse document
    extracted_text = parse_document(file_path)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    if not extracted_text.strip():
        await update.message.reply_text("Sorry, I could not extract any text from this document. It might be corrupted or an unsupported format.")
        return
        
    # Truncate text if it's extremely long for the prompt (safety net)
    process_text = extracted_text
    if len(process_text) > 20000:
        process_text = process_text[:20000] + "... [truncated]"
        
    summary = await generate_summary(process_text)
    
    # Save document metadata to DB and get active subject
    user_id = update.effective_user.id
    db = SessionLocal()
    active_subject = "General"
    try:
        db_user = db.query(User).filter(User.telegram_id == str(user_id)).first()
        if db_user:
            active_subject = db_user.active_subject
            doc_meta = DocumentMetadata(
                user_id=db_user.id,
                filename=document.file_name,
                file_type=file_ext,
                subject=active_subject,
                summary=summary
            )
            db.add(doc_meta)
            
            notif = Notification(
                user_id=db_user.id,
                message=f"📥 Uploaded document: {document.file_name} (Subject: {active_subject})"
            )
            db.add(notif)
            
            db.commit()
    except Exception as e:
        logger.error(f"Failed to save document metadata: {e}")
    finally:
        db.close()
        
    # Store text chunks in the vector DB for future semantic search
    try:
        from app.vector_db import add_document_to_vector_db
        await asyncio.to_thread(add_document_to_vector_db, str(user_id), document.file_name, process_text, subject=active_subject)
        logger.info(f"Successfully added {document.file_name} to vector DB for user {user_id} in subject {active_subject}")
    except Exception as e:
        logger.error(f"Failed to add document to vector DB: {e}")
        
    await send_long_message(update, f"**📝 Document Summary:**\n\n{summary}\n\n*Document indexed for semantic search!*", parse_mode="Markdown")

async def check_email_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job to check for new emails and send summaries to the user."""
    logger.info("Running background email check...")
    
    db = SessionLocal()
    try:
        # For a single-tenant bot, just get the first registered user
        user = db.query(User).first()
        if not user:
            logger.info("No registered users found to send email summaries to.")
            return
        telegram_id = str(user.telegram_id)
    except Exception as e:
        logger.error(f"Error fetching user for email job: {e}")
        return
    finally:
        db.close()
        
    summaries = await check_for_new_materials(telegram_id)
    for summary in summaries:
        await send_long_message_context(context, telegram_id, summary, parse_mode="Markdown")

async def send_daily_quiz(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job to send a spaced-repetition pop quiz to the user."""
    logger.info("Running daily quiz job...")
    
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            return
        telegram_id = str(user.telegram_id)
        active_subject = user.active_subject or "General"
    except Exception as e:
        logger.error(f"Error fetching user for quiz job: {e}")
        return
    finally:
        db.close()
        
    random_chunk = get_random_document_chunk(telegram_id, subject=active_subject)
    if not random_chunk:
        logger.info("No documents found to generate a quiz from.")
        return
        
    question = await generate_quiz_question(random_chunk)
    await send_long_message_context(context, telegram_id, f"**🧠 Daily Pop Quiz!**\n\n{question}", parse_mode="Markdown")

async def handle_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger a pop-quiz."""
    user_id = str(update.effective_user.id)
    
    # Get active subject
    db = SessionLocal()
    active_subject = "General"
    try:
        db_user = db.query(User).filter(User.telegram_id == user_id).first()
        if db_user:
            active_subject = db_user.active_subject
    finally:
        db.close()
        
    await update.message.chat.send_action(action="typing")
    
    random_chunk = await asyncio.to_thread(get_random_document_chunk, user_id, subject=active_subject)
    if not random_chunk:
        await update.message.reply_text("You haven't uploaded any study materials yet! Upload a document first so I can quiz you on it.")
        return
        
    await update.message.reply_text("🤔 Generating a pop-quiz question from your notes...")
    question = await generate_quiz_question(random_chunk)
    await send_long_message(update, f"**🧠 Pop Quiz!**\n\n{question}", parse_mode="Markdown")

def setup_application():
    """Start the bot and register handlers."""
    if not settings.telegram_bot_token:
        logger.error("No TELEGRAM_BOT_TOKEN provided in .env!")
        return None

    # Create the Application and pass it your bot's token.
    telegram_app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Create handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("commands", help_command))
    telegram_app.add_handler(CommandHandler("subject", handle_subject))
    telegram_app.add_handler(CommandHandler("flashcards", handle_flashcards))
    telegram_app.add_handler(CommandHandler("quiz", handle_quiz))
    telegram_app.add_handler(CommandHandler("ask", handle_ask))
    telegram_app.add_handler(CommandHandler("clear", handle_clear))
    telegram_app.add_handler(CommandHandler("fetch", handle_fetch))
    telegram_app.add_handler(CommandHandler("notifications", handle_fetch))
    telegram_app.add_handler(CommandHandler("notification_history", handle_notification_history))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Add background jobs
    job_queue = telegram_app.job_queue
    if job_queue:
        # Check email every 15 minutes
        job_queue.run_repeating(check_email_job, interval=900, first=10)
        # Send a daily quiz every 24 hours (86400 seconds)
        job_queue.run_repeating(send_daily_quiz, interval=86400, first=60)
        logger.info("Background jobs scheduled.")
    else:
        logger.warning("JobQueue is not initialized. Background tasks won't run. Make sure 'python-telegram-bot[job-queue]' is installed.")
    
    return telegram_app

# We need a custom FastAPI app to serve the webhook because Render 
# expects a proper external Web Server process to bind to the port.
telegram_app = setup_application()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only set up webhooks if we have an external URL provided by Render
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    webhook_url = f"https://{render_hostname}/{settings.telegram_bot_token}"
    
    if render_hostname:
        logger.info(f"Setting webhook to {webhook_url}")
        await telegram_app.bot.set_webhook(url=webhook_url)
    
    # Initialize and start tg application manually
    await telegram_app.initialize()
    await telegram_app.start()
    yield
    # Stop tg application manually
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post(f"/{settings.telegram_bot_token}")
async def telegram_webhook(request: Request):
    """Endpoint for Telegram to send updates to via Webhooks."""
    update = Update.de_json(await request.json(), telegram_app.bot)
    
    # Process the update in the background so we can instantly return 200 OK
    # and prevent Telegram from infinitely retrying a timeout.
    import asyncio
    asyncio.create_task(telegram_app.process_update(update))
    
    return Response(status_code=200)

@app.get("/")
async def health_check():
    """Render checks for open ports. This proves the ASGI server is alive."""
    return {"status": "ok", "message": "AI Study Agent Webhook Server is running."}

if __name__ == "__main__":
    # Running locally: Use Polling instead of ASGI Webhooks
    logger.info("Starting bot locally with Polling...")
    if telegram_app:
        telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)
    else:
        logger.error("Failed to initialize Telegram application.")
