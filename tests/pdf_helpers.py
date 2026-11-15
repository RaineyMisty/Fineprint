"""Tiny selectable-text PDF fixtures, generated in memory with the optional pypdf dependency."""

import io


def pdf_bytes(*page_texts, password=None):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in page_texts:
        page = writer.add_blank_page(width=1600, height=1000)
        if text is None:
            continue
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        commands = [b"BT /F1 8 Tf 10 980 Td 12 TL"]
        for line in text.splitlines():
            commands.append(b"<" + line.encode("cp1252").hex().encode("ascii") + b"> Tj T*")
        stream.set_data(b"\n".join(commands + [b"ET"]))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password is not None:
        writer.encrypt(password, owner_password="owner-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
