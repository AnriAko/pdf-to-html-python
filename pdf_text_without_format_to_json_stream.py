import pdfplumber
import sys
from pymongo import MongoClient
from io import BytesIO
import time

def extract_text_from_stream(pdf_bytes, pdf_name="stdin.pdf"):
    pages = []
    pdf_buffer = BytesIO(pdf_bytes)
    with pdfplumber.open(pdf_buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            pages.append({"t": text})
    return {
        "b": pdf_name,
        "p_count": len(pages),
        "p": pages
    }

def save_to_mongodb(data, user_id, mongo_uri, db_name="ol_pdf_to_json", collection_name="pdf_to_json_books"):
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
    if len(sys.argv) < 3:
        print("Usage: cat file.pdf | python script.py <userId> <mongo_uri>")
        sys.exit(1)

    user_id = sys.argv[1]
    mongo_uri = sys.argv[2]

    pdf_bytes = sys.stdin.buffer.read()

    start = time.time()
    data = extract_text_from_stream(pdf_bytes)
    save_to_mongodb(data, user_id, mongo_uri)
    print(f"Done in {round(time.time() - start, 2)} seconds")
