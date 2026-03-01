from app.llm import client, DEFAULT_MODEL
import logging

logger = logging.getLogger(__name__)

async def answer_question_from_context(question: str, context: str) -> str:
    """Use Groq to answer a question based strictly on the provided context."""
    if not context.strip():
        return "I don't have enough information in your saved notes to answer this question."
        
    prompt = (
        "You are an expert study assistant. Answer the student's question based strictly on "
        "the context provided below. If the answer is not contained in the context, say "
        "'I cannot find the answer to this in your uploaded study materials.'\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )
    
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful study assistant that answers questions accurately based on provided notes."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=DEFAULT_MODEL,
            temperature=0.1,
            max_tokens=2048,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error generating answer: {e}")
        return "Sorry, I encountered an error while trying to answer your question."
