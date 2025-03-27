import pdfplumber
import re
import sys
import time
import json
import fitz  # PyMuPDF

def clean_font_name(font_name):
    font_name = font_name.split('+')[-1]
    font_name = re.sub(r'MT$', '', font_name)
    font_name = re.sub(r'(-?(Bold|Italic|Oblique|Light|Regular|SemiBold|Medium|Black|ExtraBold|Condensed|Extended|Thin))+$', '', font_name)
    font_name = re.sub(r'-$', '', font_name)
    return font_name.strip()

def append_word(words_data, word, font_size, font_name, font_weight, font_style, color_str, x, y, is_superscript=False, is_subscript=False):
    words_data.append({
        "word": word,
        "font_size": round(font_size, 2),
        "font_name": font_name,
        "font_weight": font_weight,
        "font_style": font_style,
        "color": color_str,
        "x": round(x, 2),
        "y": round(y, 2),
        "is_superscript": is_superscript,
        "is_subscript": is_subscript
    })

def extract_text_from_page(page):
    words_data = []
    word = ""
    first_char = None
    char_list = page.chars
    prev_font_size = prev_font_name = prev_font_weight = prev_font_style = None

    for i, char in enumerate(char_list):
        text = char["text"]
        font_size = char["size"]
        font_name = char["fontname"]
        left = char["x0"]
        top = char["top"]
        color = char.get("non_stroking_color", (0, 0, 0))

        color_str = f"rgb({color[0] * 255}, {color[1] * 255}, {color[2] * 255})" if len(color) == 3 else f"rgb({color[0] * 255}, {color[0] * 255}, {color[0] * 255})"
        
        normalized_font_name = clean_font_name(font_name)
        font_weight = "bold" if "Bold" in font_name else "normal"
        font_style = "italic" if "Italic" in font_name or "Oblique" in font_name else "normal"

        if not word or (prev_font_size != font_size or prev_font_name != normalized_font_name or prev_font_weight != font_weight or prev_font_style != font_style):
            if word:
                append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
            word = ""
            first_char = char

        is_superscript = False
        is_subscript = False
        if i > 0:
            prev_char = char_list[i - 1]
            if (top < prev_char["top"] - 2) and (font_size < prev_char["size"] * 0.9):
                is_superscript = True
            if (top > prev_char["top"] + 2) and (font_size < prev_char["size"] * 0.9):
                is_subscript = True

        if is_superscript or is_subscript:
            if word:
                append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
                word = ""
            append_word(words_data, text, font_size, normalized_font_name, font_weight, font_style, color_str, left, top, is_superscript, is_subscript)
        elif text.isalnum():
            word += text
        else:
            if word:
                append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
                word = ""
            append_word(words_data, text, font_size, normalized_font_name, font_weight, font_style, color_str, left, top)

        prev_font_size = font_size
        prev_font_name = normalized_font_name
        prev_font_weight = font_weight
        prev_font_style = font_style

        if i + 1 < len(char_list):
            next_char = char_list[i + 1]
            if abs(next_char["top"] - top) > font_size * 0.5:
                if word:
                    append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
                    word = ""
                first_char = next_char

    if word:
        append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
    
    return words_data

def get_pdf_metadata(pdf_path):
    doc = fitz.open(pdf_path)
    metadata = doc.metadata
    return metadata

def get_page_dimensions(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        return round(page.width, 2), round(page.height, 2)

def generate_json(pdf_path, text_data, metadata, page_count):
    pages_data = []
    for page_data in text_data:
        page_info = {
            "size": {
                "width": page_data['width'],
                "height": page_data['height']
            },
            "text": page_data['text']
        }

        pages_data.append(page_info)

    result = {
        "pdf_name": pdf_path.split("/")[-1],
        "metadata": metadata,  # Add the metadata here
        "overall_page_count": page_count,  # Add overall page count
        "pages": pages_data
    }
    
    return result

def process_pdf(pdf_path):
    text_data = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages):
            page_html = extract_text_from_page(page)
            page_width, page_height = get_page_dimensions(pdf_path)

            text_data.append({
                "page": page_number,
                "width": page_width,
                "height": page_height,
                "text": page_html
            })

    metadata = get_pdf_metadata(pdf_path)
    page_count = len(pdf.pages)
    return text_data, metadata, page_count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_json.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()
    pdf_path = sys.argv[1]

    text_data, metadata, page_count = process_pdf(pdf_path)
    json_data = generate_json(pdf_path, text_data, metadata, page_count)

    with open("output.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json_data, indent=4))

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ Done processing! File saved as output.json")
    print(f"Execution time: {execution_time} seconds")
