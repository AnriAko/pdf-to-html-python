import pdfplumber
import fitz  # PyMuPDF
import sys
from pymongo import MongoClient
from io import BytesIO
import time

def extract_text_from_stream(pdf_bytes):
    pages = []
    pdf_buffer = BytesIO(pdf_bytes)
    
    with pdfplumber.open(pdf_buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            pages.append({"t": text})

    pdf_buffer.seek(0)
    doc = fitz.open(stream=pdf_buffer, filetype="pdf")
    pdf_title = doc.metadata.get("title") or "Untitled.pdf"

    return {
        "b": pdf_title,
        "p_count": len(pages),
        "p": pages
    }

def save_to_mongodb(data, user_id, mongo_uri, db_name, collection_name):
    client = MongoClient(mongo_uri)
    try:
        db = client[db_name]
        collection = db[collection_name]
        data["userId"] = user_id
        result = collection.insert_one(data)
        print(f"Data saved to MongoDB with _id: {result.inserted_id}")
    finally:
        client.close()
        print("MongoDB connection closed")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: cat file.pdf | python script.py <userId> <mongo_uri> <db_name> <collection_name>")
        sys.exit(1)

    user_id = sys.argv[1]
    mongo_uri = sys.argv[2]
    db_name = sys.argv[3]
    collection_name = sys.argv[4]

    pdf_bytes = sys.stdin.buffer.read()

    start = time.time()
    data = extract_text_from_stream(pdf_bytes)
    save_to_mongodb(data, user_id, mongo_uri, db_name, collection_name)
    print(f"Done in {round(time.time() - start, 2)} seconds")
