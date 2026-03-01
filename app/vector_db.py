import os
import uuid
import random
from typing import List
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from app.config import settings

# Initialize Pinecone client
# Ensure your API key is correct and valid
pc = Pinecone(api_key=settings.pinecone_api_key)
index = pc.Index(settings.pinecone_index_name)

# Initialize the exact same embedding model used by Chroma's default
# This ensures a 384-dimensional vector, matching what Pinecone expects
encoder = SentenceTransformer('all-MiniLM-L6-v2')

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Break a long text into smaller chunks for vectorization."""
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
        
    return chunks

def add_document_to_vector_db(telegram_id: str, filename: str, text: str, subject: str = "General"):
    """Chunk the document text, generate vectors, and store in Pinecone."""
    chunks = chunk_text(text)
    if not chunks:
        return
        
    # Generate vectors using SentenceTransformers manually
    embeddings = encoder.encode(chunks).tolist()
    
    vectors_to_upsert = []
    for i, chunk in enumerate(chunks):
        vector_id = f"{telegram_id}_{filename}_{i}_{uuid.uuid4().hex[:8]}"
        metadata = {
            "telegram_id": telegram_id, 
            "filename": filename, 
            "chunk_index": i, 
            "subject": subject,
            "text": chunk  # We must explicitly store the text chunks in Pinecone metadata
        }
        
        vectors_to_upsert.append(
            {"id": vector_id, "values": embeddings[i], "metadata": metadata}
        )
        
    # Upsert in batches to avoid payload limits
    batch_size = 100
    for i in range(0, len(vectors_to_upsert), batch_size):
        batch = vectors_to_upsert[i:i + batch_size]
        index.upsert(vectors=batch)

def search_documents(telegram_id: str, query: str, subject: str = "General", n_results: int = 3) -> List[str]:
    """Search the user's documents for the query within a specific subject via Pinecone."""
    query_vector = encoder.encode(query).tolist()
    
    results = index.query(
        vector=query_vector,
        top_k=n_results,
        include_metadata=True,
        filter={
            "telegram_id": {"$eq": telegram_id},
            "subject": {"$eq": subject}
        }
    )
    
    if not results or not results.matches:
        return []
        
    # Extract the original text stored in metadata
    return [match.metadata['text'] for match in results.matches if 'text' in match.metadata]

def clear_user_documents(telegram_id: str) -> int:
    """Delete all documents belonging to a user from the vector DB."""
    # Note: Pinecone free tier doesn't fully support 'delete by metadata filter' easily
    # without a paid plan, but we can query to find all IDs, then delete those IDs.
    
    # Query for up to 10,000 matches for this telegram_id
    # Since we can't query without a vector, we pass a dummy 384-d zero vector
    dummy_vector = [0.0] * 384 
    results = index.query(
        vector=dummy_vector,
        top_k=10000,
        include_metadata=True,
        filter={
            "telegram_id": {"$eq": telegram_id}
        }
    )
    
    if not results or not results.matches:
        return 0
        
    ids_to_delete = [match.id for match in results.matches]
    
    # Batch delete
    batch_size = 1000
    for i in range(0, len(ids_to_delete), batch_size):
        index.delete(ids=ids_to_delete[i:i + batch_size])
        
    # Count unique filenames deleted
    filenames = set(match.metadata.get("filename") for match in results.matches if 'metadata' in match and 'filename' in match.metadata)
    
    return len(filenames)

def get_random_document_chunk(telegram_id: str, subject: str = "General") -> str | None:
    """Retrieve a random document chunk belonging to the user for a specific subject."""
    dummy_vector = [0.0] * 384 
    results = index.query(
        vector=dummy_vector,
        top_k=100, # Only pull 100 potential chunks to save bandwidth
        include_metadata=True,
        filter={
            "telegram_id": {"$eq": telegram_id},
            "subject": {"$eq": subject}
        }
    )
    
    if not results or not results.matches:
        return None
        
    random_match = random.choice(results.matches)
    if 'metadata' in random_match and 'text' in random_match.metadata:
        return random_match.metadata['text']
        
    return None
