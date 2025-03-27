import pdfplumber
import sys
import time
import json

def extract_text(pdf_path):
    """
    Extracts the plain text from a PDF file without page division.
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def generate_json(pdf_path, full_text):
    result = {
        "pdf_name": pdf_path.split("/")[-1],
        "text": full_text
    }
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_pure_text_to_json.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()
    pdf_path = sys.argv[1]

    full_text = extract_text(pdf_path)
    json_data = generate_json(pdf_path, full_text)

    with open("output.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json_data, indent=4))

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ Done processing! File saved as output.json")
    print(f"Execution time: {execution_time} seconds")
