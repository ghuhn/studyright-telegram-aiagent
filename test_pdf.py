import fitz

def test_pdf_extraction():
    try:
        doc = fitz.open()
        print("Fitz imported and opened successfully")
    except Exception as e:
        print(f"Error: {e}")

test_pdf_extraction()
