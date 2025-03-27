import fitz  # PyMuPDF
from PIL import Image
from io import BytesIO
import base64
import pdfplumber
import sys
import time
import re

# Функция для извлечения изображения из PDF в формате Base64
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

# Функция для получения координат изображения
def get_image_coordinates(pdf_path, page_number, img_index):
    """
    Retrieves the coordinates of an image on the specified page.
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


# Функция для получения размеров страниц PDF
def get_page_dimensions(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]  # Получаем размеры первой страницы (если все страницы одинаковые)
        return round(page.width, 2), round(page.height, 2)

def generate_html(pdf_path, images_data, text_data):
    # Получаем размеры страницы
    page_width, page_height = get_page_dimensions(pdf_path)
    
    # HTML шаблон
    html_template = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            .page {{ position: relative; width: {page_width}px; height: {page_height}px; border: 1px solid #ddd; margin-bottom: 20px; }}
            img {{ position: absolute; }}
            span {{ position: absolute; white-space: pre; }}
        </style>
    </head>
    <body>
    {content}
    </body>
    </html>"""

    html_content = ""
    for page_data in text_data:
        page_number = page_data['page']
        page_html = f'<div class="page" style="width:{page_width}px; height:{page_height}px;">\n'

        # Добавление изображений для этой страницы
        for img_data in [img for img in images_data if img['page'] == page_number]:
            img_base64 = img_data['base64']
            pdf_x0, pdf_y0, img_width, img_height = img_data['coordinates'].values()
            page_html += f'<img src="data:image/png;base64,{img_base64}" style="width:{img_width}px; height:{img_height}px; left:{pdf_x0}px; top:{pdf_y0}px;" />\n'

        # Добавление текста для этой страницы
        for word_data in page_data['text']:
            page_html += (
                f'<span style="font-size:{word_data["font_size"]}px; font-family:{word_data["font_name"]}; '
                f'font-weight:{word_data["font_weight"]}; font-style:{word_data["font_style"]}; color:{word_data["color"]}; '
                f'left:{word_data["x"]}px; top:{word_data["y"]}px;">{word_data["word"]}</span>\n'
            )

        page_html += "</div>\n"
        html_content += page_html

    return html_template.format(page_width=page_width, page_height=page_height, content=html_content)

# Основная функция для обработки PDF и генерации данных
def process_pdf(pdf_path):
    images_data = []
    text_data = []

    # Обработка изображений и текста
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages):
            page_html = extract_text_from_page(page)

            images_on_page = page.images
            for img_index, img in enumerate(images_on_page):
                img_base64 = get_image_base64(pdf_path, page_number, img_index)
                pdf_x0, pdf_y0, img_width, img_height = get_image_coordinates(pdf_path, page_number, img_index)
                images_data.append({
                    "page": page_number,
                    "base64": img_base64,
                    "coordinates": {
                        "x0": pdf_x0,
                        "y0": pdf_y0,
                        "width": img_width,
                        "height": img_height
                    }
                })

            text_data.append({
                "page": page_number,
                "text": page_html
            })

    return images_data, text_data

# Основная точка входа
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_html.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()
    pdf_path = sys.argv[1]

    images_data, text_data = process_pdf(pdf_path)
    html_content = generate_html(pdf_path, images_data, text_data)

    with open("output.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ Done processing! File saved as output.html")
    print(f"Execution time: {execution_time} seconds")
