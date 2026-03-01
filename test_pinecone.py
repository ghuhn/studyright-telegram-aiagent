import asyncio
from app.vector_db import add_document_to_vector_db, search_documents, clear_user_documents

async def main():
    test_user_id = "test_user_123"
    
    print("Clearing old docs...")
    clear_user_documents(test_user_id)
    
    print("Ingesting new document...")
    doc_text = "The quick brown fox jumps over the lazy dog. Dogs are very cool animals that bark and play fetch in the park."
    add_document_to_vector_db(test_user_id, "fox_story.txt", doc_text, subject="Biology")
    
    print("Searching for 'dog'...")
    results = search_documents(test_user_id, "What sound do dogs make?", subject="Biology")
    
    print("\n--- RESULTS ---")
    if results:
        for r in results:
            print(r)
    else:
        print("No results found.")
        
    print("\nClearing test docs...")
    clear_user_documents(test_user_id)
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
