
import re
from typing import Optional, Tuple

# Zu berücksichtigende Jahreszahlen:
MIN_YEAR = 1970
MAX_YEAR = 2025

# Default-Jahr (muss innerhalb MIN_YEAR und MAX_YEAR liegen):
DEFAULT_YEAR = 1970  # <- anpassen

# Trenner, nach denen "nur die erste Nummer" genommen wird (beseitigt mehrere Eingangsnummern in einer Zeile)
MULTI_SPLIT_RE = re.compile(r"[+;,|]")


def clean_and_take_first(raw: str) -> str:
    """Trimmen, Leerzeichen entfernen, nach '.' abschneiden, nur ersten Eintrag vor + ; , | behalten."""
    s = raw.strip().replace(" ", "")
    if "." in s:
        s = s.split(".", 1)[0]
    if not s:
        return ""
    # Falls mehrere Nummern in einer Zeile: nur die erste
    s = MULTI_SPLIT_RE.split(s, 1)[0]
    return s


def normalize_separators(s: str) -> str:
    """Alle relevanten Separatoren auf '/' vereinheitlichen."""
    return s.replace("\\", "/").replace("-", "/")


def validate_default_year(default_year: Optional[int]) -> Optional[int]:
    if default_year is None:
        return None
    if not (MIN_YEAR <= default_year <= MAX_YEAR):
        raise ValueError(f"DEFAULT_YEAR muss zwischen {MIN_YEAR} und {MAX_YEAR} liegen.")
    return default_year


def year_to_int(token: str) -> Optional[int]:
    """
    Token als Jahr interpretieren, wenn es in 1970..20__ liegt.
    Akzeptiert:
      - 4-stellig: 2021
      - 2-stellig: 19 -> 2019, 90 -> 1990, 05 -> 2005
    """
    if not token or not token.isdigit():
        return None

    if len(token) == 4:
        y = int(token)
        return y if MIN_YEAR <= y <= MAX_YEAR else None

    # 2-stellig oder mehr: wir nehmen die ersten 2 Ziffern
    if len(token) >= 2:
        yy = int(token[:2])
        y = 1900 + yy if yy >= 70 else 2000 + yy
        return y if MIN_YEAR <= y <= MAX_YEAR else None

    return None


def split_prefix(part: str) -> Tuple[str, str]:
    """
    Aus einem Teil wie 'E11111' oder '11111' Nummernkreis und Nummer ableiten.
    Falls kein Buchstabe vorne -> Nummernkreis 'E'.
    """
    if not part:
        raise ValueError("Leerer Präfixteil")
    if part[0].isdigit():
        return "E", part
    return part[0], part[1:]


def choose_year_and_num(a: str, b: str) -> Tuple[int, str]:
    """
    Entscheidet, ob a oder b das Jahr ist – basierend auf Plausibilität (1970..20__)
    und Heuristiken für Tauschfälle (z. B. E/3652/19).
    """
    ya = year_to_int(a)
    yb = year_to_int(b)

    # Eindeutig
    if ya is not None and yb is None:
        return ya, b
    if yb is not None and ya is None:
        return yb, a

    # Beide plausible Jahre → Heuristik
    if ya is not None and yb is not None:
        # 4-stellig gewinnt gegen nicht-4-stellig
        if len(a) == 4 and len(b) != 4:
            return ya, b
        if len(b) == 4 and len(a) != 4:
            return yb, a
        # 2-stellig als Jahr, wenn das andere deutlich länger ist (laufende Nummer)
        if len(a) == 2 and len(b) > 2:
            return ya, b
        if len(b) == 2 and len(a) > 2:
            return yb, a
        # Fallback: "zweites Segment ist Jahr"
        return yb, a

    # Keins plausibel
    raise ValueError(f"Kein gültiges Jahr (1970..20__) in: {a!r}, {b!r}")


def parse_number(raw: str, default_year: Optional[int] = DEFAULT_YEAR) -> Optional[str]:
    """
    Liefert das Zielformat 'X/YYYY/NNNNNN' oder None für leere Zeilen.
    Wenn kein Jahr erkannt wird, wird default_year verwendet (falls gesetzt).
    """
    default_year = validate_default_year(default_year)

    s = clean_and_take_first(raw)
    if not s:
        return None

    s = normalize_separators(s)
    parts = [p for p in s.split("/") if p != ""]

    numkreis: Optional[str] = None
    year: Optional[int] = None
    num: Optional[str] = None

    # Sonderfall: 'E21/8126' (Nummernkreis + 2-stelliges Jahr in einem Token)
    if len(parts) == 2 and re.fullmatch(r"[A-Za-z]\d{2}", parts[0]):
        numkreis = parts[0][0]
        year = year_to_int(parts[0][1:])
        num = parts[1]

    elif len(parts) == 3:
        # z. B. E/19090/18 oder E/2020/16301 oder G/2021/1688
        numkreis = parts[0]
        year, num = choose_year_and_num(parts[1], parts[2])

    elif len(parts) == 2:
        left, right = parts

        # Fall: 'E/8126' → Jahr fehlt → default_year
        if re.fullmatch(r"[A-Za-z]", left) and right.isdigit():
            if default_year is None:
                raise ValueError(f"Kein Jahr gefunden in: {s!r}")
            numkreis, num, year = left, right, default_year

        else:
            # Fall: 'E11111/05' oder '11111/05'
            if re.fullmatch(r"[A-Za-z]", left):
                # 'E/18' ist unvollständig oder 'E/05' → wir behandeln als "Jahr fehlt / unklar"
                if default_year is None:
                    raise ValueError(f"Unvollständige Nummer: {s!r}")
                # interpretieren: numkreis=left, num=right, year=default_year
                numkreis, num, year = left, right, default_year
            else:
                numkreis, num_candidate = split_prefix(left)
                y = year_to_int(right)

                if y is not None:
                    year, num = y, num_candidate
                else:
                    # keine Jahresinfo in right → prüfen, ob left evtl. Jahr enthält
                    y2 = year_to_int(num_candidate)
                    if y2 is not None:
                        year, num = y2, right
                    else:
                        # wirklich kein Jahr erkannt → default_year verwenden (falls gesetzt)
                        if default_year is None:
                            raise ValueError(f"Kein gültiges Jahr (1970..20__) in: {s!r}")
                        year, num = default_year, num_candidate

    elif len(parts) == 1:
        # z. B. 'E11111' oder '11111' → Jahr fehlt → default_year
        if default_year is None:
            raise ValueError(f"Kein Jahr gefunden in: {parts[0]!r}")
        numkreis, num = split_prefix(parts[0])
        numlength = len(num)
        if numlength == 8:
            year = year_to_int(str(num[0:2]))
            num = num[2:]
        elif numlength == 10:
            year = num[0:4]
            num = num[4:]
        elif numlength <= 6:
            year = default_year

    else:
        raise ValueError(f"Unbekanntes Format: {s!r}")

    # Validierung und Ausgabeformat
    if not numkreis or year is None:
        raise ValueError(f"Parsefehler: {s!r}")

    num = (num or "").strip()
    if not num.isdigit():
        raise ValueError(f"Laufende Nummer enthält Nicht-Ziffern: {num!r}")

    return f"{numkreis}/{year:04d}/{num.zfill(6)}"


def convert_file(
    in_path: str = "input.txt",
    out_path: str = "output.txt",
    default_year: Optional[int] = DEFAULT_YEAR,
    keep_original_on_error: bool = True
):
    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for raw in fin:
            try:
                converted = parse_number(raw, default_year=default_year)
                fout.write("" if converted is None else converted)
                fout.write("\n")
            except Exception:
                # Bei Fehlern: entweder Originalzeile schreiben oder leer lassen
                if keep_original_on_error:
                    fout.write(raw.rstrip("\n") + "\n")
                else:
                    fout.write("\n")


if __name__ == "__main__":
    convert_file()
