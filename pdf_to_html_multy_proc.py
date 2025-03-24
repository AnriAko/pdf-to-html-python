import fitz  # PyMuPDF
from PIL import Image
from io import BytesIO
import base64
import pdfplumber
import sys
import multiprocessing
import time


def get_image_base64(pdf_path, page_number, img_index):
    """
    Retrieves an image from the PDF on the specified page and converts it to Base64 format.
    """
    doc = fitz.open(pdf_path)
    img_list = doc.get_page_images(page_number)
    img = img_list[img_index]
    base = fitz.Pixmap(doc, img[0])

    if img[1]:  # If there is a mask
        mask = fitz.Pixmap(doc, img[1])
        pix = fitz.Pixmap(base, mask)
    else:
        pix = base

    image_data = BytesIO(pix.tobytes("png"))
    img_pil = Image.open(image_data)

    # Convert image to Base64
    buffered = BytesIO()
    img_pil.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return img_base64

def get_image_coordinates(pdf_path, page_number, img_index):
    """
    Retrieves the coordinates of an image on the specified page.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number]
        images = page.images
        img = images[img_index]
        
        pdf_x0, pdf_y0, pdf_x1, pdf_y1 = img["x0"], img["top"], img["x1"], img["bottom"]
        img_width = abs(pdf_x1 - pdf_x0)
        img_height = abs(pdf_y1 - pdf_y0)

        return pdf_x0, pdf_y0, img_width, img_height

def extract_text_from_page(page):
    """
    Extracts text with coordinates and fonts from the specified page.
    """
    html_content = ""
    word = ""  
    last_char = None  
    char_list = page.chars  

    for i, char in enumerate(char_list):  
        text = char["text"]
        font_size = char["size"]
        font_name = char["fontname"]
        left = char["x0"]
        top = char["top"]

        is_bold = "Bold" in font_name
        font_weight = "bold" if is_bold else "normal"

        if not word:
            first_char = char

        if text.isalnum():
            word += text
            last_char = char
        elif text in [' ', '.', ',', ';', ':', '!', '?', '-', '(', ')', '\n']:
            if word:
                html_content += (
                    f'<span style="font-size:{font_size}px; font-family:{last_char["fontname"]}; '
                    f'font-weight:{font_weight}; left:{first_char["x0"]}px; top:{first_char["top"]}px;">{word}</span>\n'
                )
                word = ""
            html_content += (
                f'<span style="font-size:{font_size}px; font-family:{font_name}; font-weight:{font_weight}; '
                f'left:{left}px; top:{top}px;">{text}</span>\n'
            )

        if i + 1 < len(char_list):
            next_char = char_list[i + 1]
            next_top = next_char["top"]

            if abs(next_top - top) > 5:
                if word:
                    html_content += (
                        f'<span style="font-size:{font_size}px; font-family:{last_char["fontname"]}; '
                        f'font-weight:{font_weight}; left:{first_char["x0"]}px; top:{first_char["top"]}px;">{word}</span>\n'
                    )
                    word = ""
                first_char = next_char

    if word:
        html_content += (
            f'<span style="font-size:{font_size}px; font-family:{last_char["fontname"]}; '
            f'font-weight:{font_weight}; left:{first_char["x0"]}px; top:{first_char["top"]}px;">{word}</span>\n'
        )

    return html_content

def process_page(args):
    pdf_path, page_number = args
    page_html = ""
    fonts = set()  

    try:
        with pdfplumber.open(pdf_path) as pdf:
            doc = fitz.open(pdf_path)
            page = pdf.pages[page_number]
            width, height = page.width, page.height
            page_html += f'<div class="page" style="width:{width}px; height:{height}px;">\n'
            
            images = page.images  
            for img_index, img in enumerate(images):
                try:
                    img_base64 = get_image_base64(pdf_path, page_number, img_index)
                    pdf_x0, pdf_y0, img_width, img_height = get_image_coordinates(pdf_path, page_number, img_index)
                    page_html += f'<img src="data:image/png;base64,{img_base64}" style="width:{img_width}px; height:{img_height}px; left:{pdf_x0}px; top:{pdf_y0}px;" />\n'
                except Exception as e:
                    print(f"⚠️ Error processing image {img_index + 1} on page {page_number + 1}: {e}")
            
            page_text = extract_text_from_page(page)
            page_html += f'<div>{page_text}</div>\n'

            fonts.update({char["fontname"] for char in page.chars})
            page_html += "</div>\n"

    except Exception as e:
        print(f"❌ Error processing page{page_number + 1}: {e}")
        return "", set()  

    return page_html, fonts

def generate_html(pdf_path):
    """
    Generates an HTML document that includes images and their coordinates, as well as text from the PDF.
    Uses multiprocessing to speed up processing.
    """
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)

    pool = multiprocessing.Pool(processes=(multiprocessing.cpu_count()-2))
    
    try:
        results = pool.map(process_page, [(pdf_path, i) for i in range(num_pages)])
    finally:
        pool.close()
        pool.join()

    html_pages = "".join([result[0] for result in results if result[0]])
    fonts_list = [result[1] for result in results if result[1]]

    # Generate CSS for fonts
    css_content = """<style>
    body {
        font-family: 'Arial', sans-serif;
    }
    """
    for font in set().union(*fonts_list):  
        css_content += f"@font-face {{\n"
        css_content += f"    font-family: '{font}';\n"
        css_content += f"    src: local('{font}');\n"
        css_content += f"}}\n"

    css_content += "</style>"

    html_template = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            .page {{ position: relative; border: 1px solid #ddd; margin-bottom: 20px; }}
            img {{ position: absolute; }}
            span {{ position: absolute; white-space: pre; }}
        </style>
        {css}
    </head>
    <body>
    {content}
    </body>
    </html>"""

    html_content = html_template.format(css=css_content, content=html_pages)

    # Save the HTML file
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("✅ Done processing! File saved as output.html")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_html.py <pdf_file>")
        sys.exit(1)

    start_time = time.time()

    pdf_path = sys.argv[1]
    generate_html(pdf_path)

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time} seconds")