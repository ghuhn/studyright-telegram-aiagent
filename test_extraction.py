from app.document_parser import parse_document
import docx

# Create a dummy docx
doc = docx.Document()
doc.add_paragraph("This is a test document to see if Python-docx crashes on extraction.")
doc.save("test_dummy.docx")

print("Extracting from DOCX...")
print(parse_document("test_dummy.docx"))

import fitz
pdf = fitz.open()
page = pdf.new_page()
page.insert_text(fitz.Point(50, 50), "This is a test PDF to check extraction.")
pdf.save("test_dummy.pdf")

print("Extracting from PDF...")
print(parse_document("test_dummy.pdf"))
