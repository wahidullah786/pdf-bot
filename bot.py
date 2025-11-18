import os
import logging
import tempfile

from telegram import ChatAction
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

from PIL import Image
import fitz  # PyMuPDF
from fpdf import FPDF

# =============== تنظیمات ===============

TOKEN = "8465808953:AAGoKuN2bVYV9sJCPrAmvdcGCaw4P4VyrSA"  # توکن بات خود را این‌جا بگذار
WATERMARK_FILE = "watermark.png"  # فایل لوگوی شما

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =============== توابع کمکی ===============

def cleanup_temp_dir(temp_dir):
    if not temp_dir:
        return
    try:
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for f in files:
                try: os.remove(os.path.join(root, f))
                except: pass
            for d in dirs:
                try: os.rmdir(os.path.join(root, d))
                except: pass
        os.rmdir(temp_dir)
    except:
        pass


def add_watermark(input_img_path, output_img_path, scale=0.05, margin=15):
    if not os.path.exists(WATERMARK_FILE):
        import shutil
        shutil.copy(input_img_path, output_img_path)
        return

    base = Image.open(input_img_path).convert("RGBA")
    mark = Image.open(WATERMARK_FILE).convert("RGBA")

    bw, bh = base.size
    mw, mh = mark.size

    target_w = int(bw * scale)
    target_h = int(mh * target_w / mw)
    mark = mark.resize((target_w, target_h), Image.LANCZOS)

    x = bw - mark.width - margin
    y = bh - mark.height - margin

    base.paste(mark, (x, y), mark)
    base.save(output_img_path)


# =============== هندلرها ===============

def start(update, context):
    update.message.reply_text(
        "سلام ✋\n\n"
        "من می‌تونم:\n"
        "📷 عکس → PDF (کیفیت اوریجینل + واترمارک)\n"
        "📄 PDF → عکس (۴۰۰ DPI + واترمارک)\n"
        "🧩 SVG → PNG\n\n"
        "بهترین کیفیت = Send as File 😊"
    )


def image_to_pdf(update, context):
    msg = update.message
    temp = tempfile.mkdtemp()

    try:
        msg.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)

        if msg.photo:
            tf = msg.photo[-1].get_file()
            img_path = os.path.join(temp, "raw.jpg")
        elif msg.document and msg.document.mime_type.startswith("image/"):
            filename = msg.document.file_name.lower()
            if filename.endswith(".svg"):
                msg.reply_text("SVG را جداگانه برای تبدیل بفرستید 🙂")
                return
            tf = msg.document.get_file()
            _, ext = os.path.splitext(filename)
            img_path = os.path.join(temp, "raw" + (ext or ".jpg"))
        else:
            msg.reply_text("لطفاً یک عکس بفرستید 🙂")
            return

        tf.download(img_path)

        wm_img = os.path.join(temp, "wm.png")
        add_watermark(img_path, wm_img)

        img = Image.open(wm_img)
        if img.mode in ("P", "RGBA"):
            img = img.convert("RGB")

        w, h = img.size
        pw, ph = w * 0.75, h * 0.75

        pdf_path = os.path.join(temp, "output.pdf")
        pdf = FPDF(unit="pt", format=[pw, ph])
        pdf.add_page()
        pdf.image(wm_img, x=0, y=0, w=pw, h=ph)
        pdf.output(pdf_path)

        with open(pdf_path, "rb") as f:
            msg.reply_document(f, filename="converted.pdf", caption="تمام شد 😄")

    except Exception as e:
        logger.error(e)
        msg.reply_text("❌ خطا در تبدیل عکس به PDF")
    finally:
        cleanup_temp_dir(temp)


def pdf_to_images(update, context):
    msg = update.message
    doc = msg.document
    temp = tempfile.mkdtemp()

    if not doc.file_name.lower().endswith(".pdf"):
        msg.reply_text("فقط PDF بفرستید 🙏")
        return

    try:
        msg.reply_chat_action(ChatAction.UPLOAD_PHOTO)

        pdf_path = os.path.join(temp, "input.pdf")
        doc.get_file().download(pdf_path)

        pdf = fitz.open(pdf_path)
        pages = min(10, pdf.page_count)

        msg.reply_text(f"📄 تبدیل {pages} صفحه با کیفیت ۴۰۰ DPI...")

        for i in range(pages):
            page = pdf.load_page(i)
            pix = page.get_pixmap(dpi=400)
            raw_path = os.path.join(temp, f"raw_{i+1}.png")
            out_path = os.path.join(temp, f"page_{i+1}.png")
            pix.save(raw_path)

            add_watermark(raw_path, out_path)

            with open(out_path, "rb") as f:
                msg.reply_photo(f, caption=f"صفحه {i+1}")

        pdf.close()

    except Exception as e:
        logger.error(e)
        msg.reply_text("❌ خطا در تبدیل PDF")
    finally:
        cleanup_temp_dir(temp)


def svg_to_png(update, context):
    msg = update.message
    doc = msg.document
    temp = tempfile.mkdtemp()

    if not doc.file_name.lower().endswith(".svg"):
        msg.reply_text("SVG بفرستید 🙂")
        return

    try:
        msg.reply_chat_action(ChatAction.UPLOAD_PHOTO)

        svg_path = os.path.join(temp, "input.svg")
        png_path = os.path.join(temp, "output.png")
        doc.get_file().download(svg_path)

        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM

        drawing = svg2rlg(svg_path)
        renderPM.drawToFile(drawing, png_path, fmt="PNG")

        with open(png_path, "rb") as f:
            msg.reply_document(f, filename="converted.png", caption="تمام شد 😄")

    except Exception as e:
        logger.error(e)
        msg.reply_text("❌ خطا در تبدیل SVG")
    finally:
        cleanup_temp_dir(temp)


def unknown(update, context):
    update.message.reply_text("😊 لطفاً عکس، PDF یا SVG بفرستید")


# =============== اجرا ===============

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document.file_extension("svg"), svg_to_png))
    dp.add_handler(MessageHandler(Filters.photo | Filters.document.image, image_to_pdf))
    dp.add_handler(MessageHandler(Filters.document.pdf, pdf_to_images))
    dp.add_handler(MessageHandler(Filters.all, unknown))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
