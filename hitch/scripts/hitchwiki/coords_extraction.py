import re
import urllib.parse


def heading_to_fragment(heading, num_same_heading_above:int):
    # 1. Trim whitespace
    heading = heading.strip()
    # 2. Remove wiki markup (e.g., '', ''', etc.)
    heading = re.sub(r"''+", "", heading)
    # 3. Normalize spaces to single underscores
    heading = re.sub(r"\s+", "_", heading)
    # Remove [ and ] characters
    heading = heading.replace("[", "").replace("]", "")
    # 4. Capitalize the first character
    if heading:
        heading = heading[0].upper() + heading[1:]
    # 5. Percent-encode non-ASCII or special characters
    # fragment = urllib.parse.quote(heading, safe='_')
    if num_same_heading_above > 0:
        heading += f"_{num_same_heading_above + 1}"
    return heading


def extract_coords_and_headings(text):
    # Find all headings with their positions
    heading_pattern = re.compile(r"^(=+)\s*(.*?)\s*\1$", re.MULTILINE)
    headings = [(m.start(), m.group(2)) for m in heading_pattern.finditer(text)]

    # Find all {{Coords|...}} tags with their positions
    coords_pattern = re.compile(r"{{Coords\|[^}]+}}")
    coords = [(m.start(), m.group(0)) for m in coords_pattern.finditer(text)]

    results = []
    for coord_pos, coord_tag in coords:
        # Find the closest preceding heading
        heading = None
        same_heading_count = 0
        for h_pos, h_text in reversed(headings):
            if heading and h_text == heading:
                same_heading_count += 1

            if h_pos < coord_pos and heading is None:
                heading = h_text

        results.append(
            {
                "heading": heading,
                "coords": coord_tag,
                "same_heading_count": same_heading_count,
            }
        )
    return results


def find_coords_and_headings(raw_wiki_page:str, title:str, base_url:str = "https://hitchwiki.org/en/") -> list[dict]:
    results = []
    for item in extract_coords_and_headings(raw_wiki_page):
        if item["heading"]:
            fragment = heading_to_fragment(item["heading"], item["same_heading_count"])
            link = base_url + title + "#" + urllib.parse.quote(fragment)
        else:
            link = base_url + title

        item["link"] = link
        results.append(item)

    return results