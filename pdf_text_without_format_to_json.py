import pdfplumber
import sys
import time
import json

def extract_text_from_page(page):
    """
    Extracts the plain text from a PDF page.
    """
    return page.extract_text()

def get_page_dimensions(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        return round(page.width, 2), round(page.height, 2)

def generate_json(pdf_path, text_data, page_count):
    pages_data = []
    for page_data in text_data:
        page_info = {
            "text": page_data['text']
        }

        pages_data.append(page_info)

    result = {
        "pdf_name": pdf_path.split("/")[-1],
        "overall_page_count": page_count,  # Add overall page count
        "pages": pages_data
    }
    
    return result

def process_pdf(pdf_path):
    text_data = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages):
            page_text = extract_text_from_page(page)
            page_width, page_height = get_page_dimensions(pdf_path)

            text_data.append({
                "page": page_number,
                "width": page_width,
                "height": page_height,
                "text": page_text
            })

    page_count = len(pdf.pages)
    return text_data, page_count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_text_without_format_to_json.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()
    pdf_path = sys.argv[1]

    text_data, page_count = process_pdf(pdf_path)
    json_data = generate_json(pdf_path, text_data, page_count)

    with open("output.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json_data, indent=4))

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ Done processing! File saved as output.json")
    print(f"Execution time: {execution_time} seconds")
