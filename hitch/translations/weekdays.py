"""Localized weekday names, for the weekday we prepend to every displayed ride date.

Why a baked-in table rather than a runtime library: the only stdlib option is the
`locale` module, which needs the OS locales generated (the app's slim container has
none), and Babel is not in requirements.txt. The strings below are CLDR's, dumped
once with Babel (`format_date(d, "EEE"/"EEEE")` / `Locale.days["stand-alone"]["wide"]`)
for exactly the languages in SUPPORTED_LANGUAGES -- regenerate the same way if the
language list grows.

Both tables are indexed by `datetime.date.weekday()`, i.e. Monday is 0. The JS side
gets the same lists injected as window.__WEEKDAYS__ (see client_weekdays_json() in
hitch/__init__.py) rather than calling toLocaleDateString(): server-rendered and
client-rendered ride cards sit next to each other on the same page, and a browser
whose ICU data lacks e.g. Georgian would otherwise print a different weekday than
the card above it.
"""

import datetime
import re

# Abbreviated form (CLDR "EEE") -- what gets prepended to a date.
WEEKDAY_ABBR = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "de": ("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."),
    "fr": ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
    "pt": ("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom."),
    "ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
    "pl": ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."),
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    "it": ("lun", "mar", "mer", "gio", "ven", "sab", "dom"),
    "hr": ("pon", "uto", "sri", "čet", "pet", "sub", "ned"),
    "cs": ("po", "út", "st", "čt", "pá", "so", "ne"),
    "et": ("E", "T", "K", "N", "R", "L", "P"),
    "hu": ("H", "K", "Sze", "Cs", "P", "Szo", "V"),
    "zh": ("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
    "ja": ("月", "火", "水", "木", "金", "土", "日"),
    "ro": ("lun.", "mar.", "mie.", "joi", "vin.", "sâm.", "dum."),
    "bg": ("пн", "вт", "ср", "чт", "пт", "сб", "нд"),
    "da": ("man.", "tir.", "ons.", "tor.", "fre.", "lør.", "søn."),
    "el": ("Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"),
    "fi": ("ma", "ti", "ke", "to", "pe", "la", "su"),
    "ka": ("ორშ", "სამ", "ოთხ", "ხუთ", "პარ", "შაბ", "კვი"),
    "lt": ("pr", "an", "tr", "kt", "pn", "št", "sk"),
    "lv": ("pirmd.", "otrd.", "trešd.", "ceturtd.", "piektd.", "sestd.", "svētd."),
    "mn": ("Да", "Мя", "Лх", "Пү", "Ба", "Бя", "Ня"),
    "nl": ("ma", "di", "wo", "do", "vr", "za", "zo"),
    "no": ("man.", "tir.", "ons.", "tor.", "fre.", "lør.", "søn."),
    "sk": ("po", "ut", "st", "št", "pi", "so", "ne"),
    "sl": ("pon.", "tor.", "sre.", "čet.", "pet.", "sob.", "ned."),
    "sr": ("пон", "уто", "сре", "чет", "пет", "суб", "нед"),
    "sv": ("mån", "tis", "ons", "tors", "fre", "lör", "sön"),
    "tr": ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"),
    "uk": ("пн", "вт", "ср", "чт", "пт", "сб", "нд"),
}

# Full stand-alone form -- for the weekday filter's dropdown, where an option label
# has room and "E" (Estonian's abbreviation) would name nothing.
WEEKDAY_NAMES = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "pt": ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"),
    "ru": ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
    "pl": ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "it": ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
    "hr": ("ponedjeljak", "utorak", "srijeda", "četvrtak", "petak", "subota", "nedjelja"),
    "cs": ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"),
    "et": ("Esmaspäev", "Teisipäev", "Kolmapäev", "Neljapäev", "Reede", "Laupäev", "Pühapäev"),
    "hu": ("hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
    "ja": ("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
    "ro": ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"),
    "bg": ("понеделник", "вторник", "сряда", "четвъртък", "петък", "събота", "неделя"),
    "da": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "el": ("Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"),
    "fi": ("maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"),
    "ka": ("ორშაბათი", "სამშაბათი", "ოთხშაბათი", "ხუთშაბათი", "პარასკევი", "შაბათი", "კვირა"),
    "lt": ("pirmadienis", "antradienis", "trečiadienis", "ketvirtadienis", "penktadienis", "šeštadienis", "sekmadienis"),
    "lv": ("Pirmdiena", "Otrdiena", "Trešdiena", "Ceturtdiena", "Piektdiena", "Sestdiena", "Svētdiena"),
    "mn": ("Даваа", "Мягмар", "Лхагва", "Пүрэв", "Баасан", "Бямба", "Ням"),
    "nl": ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
    "no": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "sk": ("pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"),
    "sl": ("ponedeljek", "torek", "sreda", "četrtek", "petek", "sobota", "nedelja"),
    "sr": ("понедељак", "уторак", "среда", "четвртак", "петак", "субота", "недеља"),
    "sv": ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"),
    "tr": ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"),
    "uk": ("понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"),
}

# The stamps we get handed are either "2026-08-01 11:32" (the ride-card `when`) or a
# full RFC 9557 string ("2026-08-01T11:32:00+02:00[Europe/Berlin]"). Only the leading
# date is read: it is already the ride's own local wall-clock day, and re-parsing the
# offset would move a late-evening ride onto the next/previous weekday.
_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")


def weekday_index(value):
    """Monday-is-0 weekday of a date/datetime or a "YYYY-MM-DD…" string, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.weekday()
    m = _DATE_RE.match(str(value))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).weekday()
    except ValueError:
        return None


def _lang(lang):
    if lang is None:
        # Imported lazily: this module is also imported by templates rendered outside a
        # request (nothing to do with flask.g), and current_lang() already defaults to "en".
        from hitch.translations import current_lang

        lang = current_lang()
    return lang if lang in WEEKDAY_ABBR else "en"


def weekday_abbrs(lang=None):
    return WEEKDAY_ABBR[_lang(lang)]


def weekday_names(lang=None):
    return WEEKDAY_NAMES[_lang(lang)]


def weekday_abbr(value, lang=None):
    """The day `value` falls on, abbreviated (Fri / Fr. / пт); "" when it has no date."""
    idx = weekday_index(value)
    return "" if idx is None else WEEKDAY_ABBR[_lang(lang)][idx]


def with_weekday(stamp, lang=None):
    """A displayed ride stamp with its weekday in front: "Fri 2026-08-01 11:32".

    Returns the stamp untouched when no date can be read out of it, so a caller can
    wrap any date-ish field without first checking whether it has one.
    """
    abbr = weekday_abbr(stamp, lang)
    return f"{abbr} {stamp}" if abbr else (stamp or "")
