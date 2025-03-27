import fitz  # PyMuPDF
import pdfplumber
import base64
from PIL import Image
from io import BytesIO
import re
import sys
import time
import json

def get_image_base64(pdf_path, page_number, img_index):
    """
    Retrieves an image from the PDF on the specified page and converts it to Base64 format.
    """
    doc = fitz.open(pdf_path)

    # Extract images from each page
    img_list = doc.get_page_images(page_number)
    img = img_list[img_index]
    base = fitz.Pixmap(doc, img[0])

    if img[1]:  # If there is a mask
        mask = fitz.Pixmap(doc, img[1])
        pix = fitz.Pixmap(base, mask)
    else:
        pix = base

    # Convert Pixmap to image
    image_data = BytesIO(pix.tobytes("png"))
    img_pil = Image.open(image_data)

    # Convert image to Base64
    buffered = BytesIO()
    img_pil.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return img_base64

def get_image_position(pdf_path, page_number, img_index):
    """
    Retrieves the position (coordinates) of an image on the specified page.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number]
        images = page.images
        img = images[img_index]
        
        # Image coordinates
        pdf_x0, pdf_y0, pdf_x1, pdf_y1 = img["x0"], img["top"], img["x1"], img["bottom"]
        img_width = abs(pdf_x1 - pdf_x0)
        img_height = abs(pdf_y1 - pdf_y0)

        return round(pdf_x0, 2), round(pdf_y0, 2), round(img_width, 2), round(img_height, 2)

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

def generate_json(pdf_path, images_data, text_data, metadata, page_count):
    pages_data = []
    for page_data in text_data:
        page_number = page_data['page']
        page_images = [img for img in images_data if img['page'] == page_number]
        
        page_info = {
            "size": {
                "width": page_data['width'],
                "height": page_data['height']
            },
            "images": [],
            "text": page_data['text']
        }
        
        for img_data in page_images:
            img_base64 = img_data['base64']
            pdf_x0, pdf_y0, img_width, img_height = img_data['position'].values()
            page_info["images"].append({
                "base64": img_base64,
                "position": {
                    "x0": pdf_x0,
                    "y0": pdf_y0,
                    "width": img_width,
                    "height": img_height
                }
            })

        pages_data.append(page_info)

    result = {
        "pdf_name": pdf_path.split("/")[-1],
        "metadata": metadata,  # Add the metadata here
        "page_count": page_count,  # Add overall page count
        "pages": pages_data
    }
    
    return result

def process_pdf(pdf_path):
    images_data = []
    text_data = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages):
            page_html = extract_text_from_page(page)

            images_on_page = page.images
            page_width, page_height = get_page_dimensions(pdf_path)

            for img_index, img in enumerate(images_on_page):
                img_base64 = get_image_base64(pdf_path, page_number, img_index)
                pdf_x0, pdf_y0, img_width, img_height = get_image_position(pdf_path, page_number, img_index)
                images_data.append({
                    "page": page_number,
                    "base64": img_base64,
                    "position": {
                        "x0": pdf_x0,
                        "y0": pdf_y0,
                        "width": img_width,
                        "height": img_height
                    }
                })

            text_data.append({
                "page": page_number,
                "width": page_width,
                "height": page_height,
                "text": page_html
            })

    metadata = get_pdf_metadata(pdf_path)
    page_count = len(pdf.pages)
    return images_data, text_data, metadata, page_count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_json.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()
    pdf_path = sys.argv[1]

    images_data, text_data, metadata, page_count = process_pdf(pdf_path)
    json_data = generate_json(pdf_path, images_data, text_data, metadata, page_count)

    with open("output.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json_data, indent=4))

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ Done processing! File saved as output.json")
    print(f"Execution time: {execution_time} seconds")
