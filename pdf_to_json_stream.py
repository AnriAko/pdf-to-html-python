import fitz  # PyMuPDF
import pdfplumber
import base64
from PIL import Image
from io import BytesIO
import re
import sys
import time
from pymongo import MongoClient

def get_image_base64(doc, page_number, img_index):
    img_list = doc[page_number].get_images()
    img = img_list[img_index]
    base = fitz.Pixmap(doc, img[0])
    if img[1]:
        mask = fitz.Pixmap(doc, img[1])
        pix = fitz.Pixmap(base, mask)
    else:
        pix = base

    image_data = BytesIO(pix.tobytes("png"))
    img_pil = Image.open(image_data)
    buffered = BytesIO()
    img_pil.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def get_image_position(page, img_index):
    img = page.images[img_index]
    return round(img["x0"], 2), round(img["top"], 2), round(img["x1"] - img["x0"], 2), round(img["bottom"] - img["top"], 2)

def clean_font_name(font_name):
    font_name = font_name.split('+')[-1]
    font_name = re.sub(r'MT$', '', font_name)
    font_name = re.sub(r'(-?(Bold|Italic|Oblique|Light|Regular|SemiBold|Medium|Black|ExtraBold|Condensed|Extended|Thin))+$', '', font_name)
    return font_name.strip("-")

def append_word(words_data, word, font_size, font_name, font_weight, font_style, color_str, x, y, is_superscript=False, is_subscript=False):
    words_data.append({
        "w": word,
        "fs": round(font_size, 2),
        "fn": font_name,
        "fw": font_weight,
        "fst": font_style,
        "c": color_str,
        "x": round(x, 2),
        "y": round(y, 2),
        "sup": is_superscript,
        "sub": is_subscript
    })

def extract_text_from_page(page):
    words_data, word, first_char = [], "", None
    char_list = page.chars
    prev_font_size = prev_font_name = prev_font_weight = prev_font_style = None

    for i, char in enumerate(char_list):
        text = char["text"]
        font_size, font_name = char["size"], char["fontname"]
        left, top = char["x0"], char["top"]
        color = char.get("non_stroking_color", (0, 0, 0))
        color_str = f"rgb({color[0]*255}, {color[1]*255}, {color[2]*255})" if len(color) == 3 else f"rgb({color[0]*255}, {color[0]*255}, {color[0]*255})"

        normalized_font_name = clean_font_name(font_name)
        font_weight = "bold" if "Bold" in font_name else "normal"
        font_style = "italic" if "Italic" in font_name or "Oblique" in font_name else "normal"

        if not word or (prev_font_size != font_size or prev_font_name != normalized_font_name or prev_font_weight != font_weight or prev_font_style != font_style):
            if word:
                append_word(words_data, word, prev_font_size, prev_font_name, prev_font_weight, prev_font_style, color_str, first_char["x0"], first_char["top"])
            word = ""
            first_char = char

        is_superscript = is_subscript = False
        if i > 0:
            prev_char = char_list[i - 1]
            if top < prev_char["top"] - 2 and font_size < prev_char["size"] * 0.9:
                is_superscript = True
            if top > prev_char["top"] + 2 and font_size < prev_char["size"] * 0.9:
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

        prev_font_size, prev_font_name = font_size, normalized_font_name
        prev_font_weight, prev_font_style = font_weight, font_style

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

def generate_json(images_data, text_data, metadata, page_count, user_id, pdf_name):
    pages_data = []
    for page_data in text_data:
        page_number = page_data['page']
        page_images = [img for img in images_data if img['page'] == page_number]

        page_info = {
            "s": {
                "w": page_data['width'],
                "h": page_data['height']
            },
            "imgs": [],
            "txt": page_data['text']
        }

        for img_data in page_images:
            x0, y0, width, height = img_data['position'].values()
            page_info["imgs"].append({
                "b64": img_data['base64'],
                "pos": {"x": x0, "y": y0, "w": width, "h": height}
            })

        pages_data.append(page_info)

    return {
        "pdf": pdf_name,
        "meta": metadata,
        "p_count": page_count,
        "p": pages_data,
        "uid": user_id
    }

def save_to_mongodb(data, user_id, mongo_uri, db_name="ol_pdf_to_json", collection_name="pdf_to_json_books"):
    client = MongoClient(mongo_uri)
    try:
        db = client[db_name]
        collection = db[collection_name]
        result = collection.insert_one(data)
        print(f"Saved to MongoDB with _id: {result.inserted_id}")
    finally:
        client.close()

def process_pdf_from_stream(pdf_bytes):
    images_data, text_data = [], []

    pdf_buffer = BytesIO(pdf_bytes)
    doc = fitz.open(stream=pdf_buffer, filetype="pdf")

    pdf_buffer.seek(0)
    with pdfplumber.open(pdf_buffer) as pdf:
        for page_number, page in enumerate(pdf.pages):
            words = extract_text_from_page(page)
            for img_index, _ in enumerate(page.images):
                base64_img = get_image_base64(doc, page_number, img_index)
                pos = get_image_position(page, img_index)
                images_data.append({
                    "page": page_number,
                    "base64": base64_img,
                    "position": {
                        "x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]
                    }
                })
            text_data.append({
                "page": page_number,
                "width": round(page.width, 2),
                "height": round(page.height, 2),
                "text": words
            })

    metadata = doc.metadata
    return images_data, text_data, metadata, len(doc)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: cat file.pdf | python script.py <userId> <mongo_uri>")
        sys.exit(1)

    user_id = sys.argv[1]
    mongo_uri = sys.argv[2]
    pdf_bytes = sys.stdin.buffer.read()

    start = time.time()
    images_data, text_data, metadata, page_count = process_pdf_from_stream(pdf_bytes)
    json_data = generate_json(images_data, text_data, metadata, page_count, user_id, "stdin.pdf")

    save_to_mongodb(json_data, user_id, mongo_uri)

    print(f"Done in {round(time.time() - start, 2)} seconds")


# Short Name     Full Name        Description
# w              word             Text of the word or symbol
# fs             font_size        Font size
# fn             font_name        Font name
# fw             font_weight      Weight (bold/normal)
# fst            font_style       Style (italic/normal)
# c              color            Text color in rgb format
# x              x                X coordinate of the word or symbol
# y              y                Y coordinate of the word or symbol
# sup            is_superscript   Superscript symbol (true/false)
# sub            is_subscript     Subscript symbol (true/false)

# s              size             Page size (object)
# w (in size)    width            Page width
# h (in size)    height           Page height

# imgs           images           Array of page images
# b64            base64           Image in base64 format
# pos            position         Image position (object)
# x (in pos)     x0               X coordinate of top-left corner
# y (in pos)     y0               Y coordinate of top-left corner
# w (in pos)     width            Image width
# h (in pos)     height           Image height

# txt            text             Page text (array of words)
# pdf            pdf_name         PDF file name
# meta           metadata         PDF metadata
# p_count        page_count       Number of pages
# p              pages            Array of pages
# uid            userId           User ID
