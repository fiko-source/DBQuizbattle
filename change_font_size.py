from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject


PDF_PATH = Path("DS_Project_Report_Form.pdf")
FONT_SIZE = 6


def change_text_field_font_size(pdf_path, font_size):
    reader = PdfReader(pdf_path)
    writer = PdfWriter(clone_from=reader)

    for page in writer.pages:
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()

            if annot.get("/FT") == "/Tx":
                annot[NameObject("/DA")] = TextStringObject(
                    f"/Helvetica {font_size} Tf 0 g"
                )

    acroform = writer.root_object.get("/AcroForm")
    if acroform:
        acroform = acroform.get_object()
        acroform[NameObject("/NeedAppearances")] = BooleanObject(True)

    output_path = pdf_path.with_name(f"{pdf_path.stem}_font_{font_size}.pdf")
    with output_path.open("wb") as file:
        writer.write(file)

    print(f"Saved: {output_path}")


if __name__ == "__main__":
    change_text_field_font_size(PDF_PATH, FONT_SIZE)