import argparse
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def synthetic_pdf(text='Synthetic food inventory procedure. Verify food inventory daily. Consume lots with earliest expiration first. Check shelf life before use. Coordinate replenishment with mission control. This is a synthetic test fixture, not NASA operational guidance.'):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    commands = ['BT /F1 11 Tf 40 740 Td']
    words = text.split()
    for start in range(0, len(words), 10):
        line = ' '.join(words[start:start + 10]).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        commands.extend([f'({line}) Tj', '0 -16 Td'])
    commands.append('ET')
    stream.set_data('\n'.join(commands).encode('latin-1'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    arguments.output.write_bytes(synthetic_pdf())
