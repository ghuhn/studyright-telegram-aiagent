from groq import AsyncGroq
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize the Groq client
client = AsyncGroq(api_key=settings.groq_api_key)

# We will use llama-3.1-8b-instant as the default model, since it's fast and free. 
# Another option is mixtral-8x7b-32768 or llama-3.3-70b-versatile
DEFAULT_MODEL = "llama-3.1-8b-instant"

async def generate_summary(text: str) -> str:
    """Generate a summary of the provided text using Groq."""
    if not text.strip():
        return "No text provided to summarize."
        
    prompt = (
        "You are an expert study assistant. Please provide a clear, concise, "
        "and well-structured summary of the following text. Highlight the "
        "key concepts, main arguments, and any important vocabulary.\n\n"
        f"Text to summarize:\n{text}"
    )
    
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful study assistant that creates excellent summaries."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=DEFAULT_MODEL,
            temperature=0.3,
            max_tokens=2048,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error generating summary: {e}")
        return "Sorry, I encountered an error while summarizing the text."

async def generate_flashcards(text: str) -> str:
    """Generate study flashcards from the provided text."""
    if not text.strip():
        return "No text provided."
        
    prompt = (
        "You are an expert study assistant. Create 5-10 flashcards based on the key "
        "concepts in the following text. Format your response strictly as:\n"
        "Q: [Question]\nA: [Answer]\n\n"
        f"Text:\n{text}"
    )
    
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful study assistant that generates flashcards."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=DEFAULT_MODEL,
            temperature=0.3,
            max_tokens=2048,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error generating flashcards: {e}")
        return "Sorry, I encountered an error while generating flashcards."

async def generate_quiz_question(context_text: str) -> str:
    """Generate a single thought-provoking pop quiz question based on a random text chunk."""
    if not context_text.strip():
        return "I tried to generate a quiz question for you today, but couldn't read your notes! We'll try again tomorrow."
        
    prompt = (
        "You are a demanding but helpful professor creating a daily 'spaced repetition' pop-quiz for a student.\n"
        "Based on the provided excerpt from the student's notes, generate exactly ONE thought-provoking question that tests their understanding of the core concept in the text.\n"
        "Do NOT provide the answer. ONLY ask the question. Keep it challenging but concise.\n\n"
        f"Notes excerpt:\n{context_text}"
    )
    
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a demanding but helpful professor. You only ask questions and never provide the answer."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=DEFAULT_MODEL,
            temperature=0.7,  # Slightly higher temperature for more varied questions
            max_tokens=256,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error generating quiz question: {e}")
        return "I tried to generate a quiz question for you today, but my brain short-circuited! We'll try again tomorrow."

async def evaluate_quiz_answer(question: str, user_answer: str) -> str:
    """Evaluate the user's answer to a pop-quiz question."""
    if not user_answer.strip():
        return "I didn't catch your answer!"
        
    prompt = (
        "You are a supportive but accurate professor. A student has answered a pop-quiz question. "
        "Evaluate their answer.\n\n"
        f"Question:\n{question}\n\n"
        f"Student's Answer:\n{user_answer}\n\n"
        "Tell the student if they are correct, partially correct, or incorrect. Then explain the complete correct answer concisely."
    )
    
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful and encouraging professor grading a student's answer."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=DEFAULT_MODEL,
            temperature=0.5,
            max_tokens=512,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error evaluating quiz answer: {e}")
        return "Sorry, I couldn't grade your answer right now. But keep up the good studying!"

