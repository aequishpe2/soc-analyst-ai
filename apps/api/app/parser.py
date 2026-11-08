"""Bounded untrusted-file parser. Runs in a killable child process, never in the web loop."""

import csv
import hashlib
import json
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

from defusedxml.ElementTree import iterparse
from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_CELL = 32 * 1024
MAX_EXPANDED = 200 * 1024 * 1024
MAX_PARSED = 200 * 1024 * 1024
PREVIEW_ROWS = 10


class InvalidSource(ValueError):
    pass


def cell_text(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value)
    if "\x00" in text:
        raise InvalidSource("El archivo contiene bytes nulos no admitidos.")
    if len(text.encode("utf-8")) > MAX_CELL:
        raise InvalidSource("Una celda supera 32 KiB. No se ha truncado el archivo.")
    return text


def csv_rows(path, config, resolved):
    with path.open("rb") as source:
        prefix = source.read(4)
    encoding = config["encoding"]
    if encoding == "auto":
        encoding = "utf-16" if prefix.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    delimiter = config["delimiter"]
    csv.field_size_limit(MAX_CELL)
    with path.open(encoding=encoding, newline="") as source:
        sample = source.read(65536)
        source.seek(0)
        if delimiter == "auto":
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        resolved.update(encoding=encoding, delimiter=delimiter)
        reader = csv.reader(source, delimiter=delimiter, strict=True)
        previous = 0
        for values in reader:
            start = previous + 1
            previous = reader.line_num
            yield "CSV", start, previous, [cell_text(v) for v in values], []


def validate_zip(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(i.file_size for i in entries) > MAX_EXPANDED:
            raise InvalidSource("El Excel supera el límite de expansión (200 MiB o 1000 partes).")
        names = [i.filename for i in entries]
        if len(set(names)) != len(names):
            raise InvalidSource("Excel con entradas ZIP duplicadas.")
        if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
            raise InvalidSource("El archivo no es un libro XLSX válido.")
        for entry in entries:
            name = entry.filename
            if entry.flag_bits & 1 or ".." in name.split("/") or name.startswith("/"):
                raise InvalidSource("Excel cifrado o estructura ZIP insegura.")
            if name.lower().endswith(".bin") or "externallinks/" in name.lower():
                raise InvalidSource("No se admiten macros, objetos binarios ni enlaces externos.")
            if not name.endswith((".xml", ".rels")):
                continue
            with archive.open(entry) as part:
                for _, element in iterparse(part, forbid_dtd=True, forbid_entities=True):
                    tag = element.tag.rsplit("}", 1)[-1]
                    if element.attrib.get("TargetMode", "").lower() == "external":
                        raise InvalidSource("El libro contiene relaciones externas no admitidas.")
                    if "macroenabled" in element.attrib.get("ContentType", "").lower():
                        raise InvalidSource("No se admiten macros.")
                    if tag == "c":
                        coordinate = re.fullmatch(r"([A-Z]+)(\d+)", element.attrib.get("r", ""))
                        if coordinate and (
                            column_index_from_string(coordinate[1]) > MAX_COLUMNS
                            or int(coordinate[2]) > MAX_ROWS + 1
                        ):
                            raise InvalidSource("Excel fuera de los límites de filas o columnas.")
                    element.clear()


def excel_rows(path):
    validate_zip(path)
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        if len(workbook.worksheets) > 20:
            raise InvalidSource("Se admiten hasta 20 hojas por archivo.")
        for sheet in workbook.worksheets:
            sheet.reset_dimensions()  # Do not trust producer-supplied dimensions.
            for number, cells in enumerate(sheet.iter_rows(), 1):
                formulas = [index for index, cell in enumerate(cells) if cell.data_type == "f"]
                yield sheet.title, number, number, [cell_text(c.value) for c in cells], formulas
    finally:
        workbook.close()


def parse_source(path: Path, output: Path, config: dict):
    if path.stat().st_size > MAX_BYTES or path.stat().st_size == 0:
        raise InvalidSource("Archivo vacío o superior a 20 MiB.")
    resolved = {}
    rows = csv_rows(path, config, resolved) if path.suffix == ".csv" else excel_rows(path)
    sheets = {}
    inspected = 0
    total = 0
    blanks = 0
    parsed_bytes = 0
    with (output / "rows.jsonl").open("w", encoding="utf-8", newline="\n") as sink:
        for sheet, number, end, values, formulas in rows:
            inspected += 1
            if inspected > MAX_ROWS + 20:
                raise InvalidSource("El archivo supera 100 000 filas (incluidas filas vacías).")
            if len(values) > MAX_COLUMNS:
                raise InvalidSource("El archivo supera 200 columnas.")
            if not any(v is not None and v != "" for v in values):
                blanks += 1
                continue
            if sheet not in sheets:
                if formulas:
                    raise InvalidSource("No se admiten fórmulas en la cabecera.")
                if any(v is not None and len(v.encode("utf-8")) > 512 for v in values):
                    raise InvalidSource("Una cabecera supera 512 bytes. Revisa la fila de títulos.")
                sheets[sheet] = {
                    "name": sheet,
                    "header_row": number,
                    "columns": [
                        {
                            "id": f"c{i}",
                            "label": (v or f"Columna {i + 1}")[:200],
                            "original_label": v,
                        }
                        for i, v in enumerate(values)
                    ],
                    "rows": 0,
                    "preview": [],
                    "formula_rows": 0,
                }
                continue
            meta = sheets[sheet]
            error = None
            if path.suffix == ".csv" and len(values) != len(meta["columns"]):
                error = "La cantidad de celdas no coincide con la cabecera."
            if path.suffix == ".xlsx" and len(values) > len(meta["columns"]):
                raise InvalidSource("Hay columnas fuera de la cabecera. Corrige el libro.")
            values += [None] * (len(meta["columns"]) - len(values))
            row = {
                "sheet": sheet,
                "row": number,
                "line_end": end,
                "values": values,
                "formulas": formulas,
                "error": error,
            }
            serialized = json.dumps(row, ensure_ascii=False) + "\n"
            parsed_bytes += len(serialized.encode("utf-8"))
            if parsed_bytes > MAX_PARSED:
                raise InvalidSource("La lectura de celdas supera 200 MiB. No se truncó el archivo.")
            sink.write(serialized)
            meta["rows"] += 1
            meta["formula_rows"] += bool(formulas)
            total += 1
            if total > MAX_ROWS:
                raise InvalidSource("El archivo supera 100 000 registros.")
            if len(meta["preview"]) < PREVIEW_ROWS:
                meta["preview"].append({**row, "values": [v[:200] if v else v for v in values]})
    if not total:
        raise InvalidSource("El archivo no contiene registros debajo de una cabecera.")
    return {
        "sheets": list(sheets.values()),
        "total_rows": total,
        "blank_rows": blanks,
        "parsed_bytes": parsed_bytes,
        "parser_version": "1",
        "csv_options": resolved if path.suffix == ".csv" else None,
        "preview_note": "Muestra de 10 filas por hoja; cada celda se muestra hasta 200 caracteres.",
    }


def main():
    path, output, config = Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3])
    try:
        manifest = parse_source(path, output, config)
        with (output / "rows.jsonl").open("rb") as rows:
            digest = hashlib.file_digest(rows, "sha256").hexdigest()
        result = {"manifest": manifest, "rows_hash": digest}
    except InvalidSource as exc:
        result = {"error": str(exc)}
    except (UnicodeError, csv.Error):
        result = {
            "error": "CSV inválido. Revisa codificación, delimitador, comillas y tamaño de celdas."
        }
    except Exception:
        result = {"error": "Excel inválido, cifrado o contenido XML no admitido."}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
