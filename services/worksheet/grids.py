"""Grid builders for word search and crossword task mechanics."""

import random

CYRILLIC = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ"


def build_word_search_grid(words: list[str], grid_size: int = 8) -> list[list[str]]:
    """Place words horizontally or vertically into a grid, fill rest with random Cyrillic."""
    grid = [["" for _ in range(grid_size)] for _ in range(grid_size)]

    for word in words:
        upper = word.upper().replace("\u0401", "\u0415").replace("\u0419", "\u0418")
        placed = False
        for _ in range(200):
            direction = random.choice(["H", "V"])
            if direction == "H":
                row = random.randint(0, grid_size - 1)
                max_col = grid_size - len(upper)
                if max_col < 0:
                    continue
                col = random.randint(0, max_col)
                if all(grid[row][col + i] in ("", upper[i]) for i in range(len(upper))):
                    for i, ch in enumerate(upper):
                        grid[row][col + i] = ch
                    placed = True
                    break
            else:
                max_row = grid_size - len(upper)
                if max_row < 0:
                    continue
                row = random.randint(0, max_row)
                col = random.randint(0, grid_size - 1)
                if all(grid[row + i][col] in ("", upper[i]) for i in range(len(upper))):
                    for i, ch in enumerate(upper):
                        grid[row + i][col] = ch
                    placed = True
                    break

        if not placed:
            for r in range(grid_size):
                max_c = grid_size - len(upper)
                if max_c < 0:
                    break
                for c in range(max_c + 1):
                    if all(grid[r][c + i] in ("", upper[i]) for i in range(len(upper))):
                        for i, ch in enumerate(upper):
                            grid[r][c + i] = ch
                        placed = True
                        break
                if placed:
                    break

    for r in range(grid_size):
        for c in range(grid_size):
            if grid[r][c] == "":
                grid[r][c] = random.choice(CYRILLIC)

    return grid


def build_crossword_grid(words: list[str], clues: list[str]) -> dict:
    """Build a crossword with intersections between horizontal and vertical words."""
    words_upper = [w.upper() for w in words]
    cells: dict[tuple[int, int], str] = {}
    placements: list[dict] = []

    def can_place(word, row, col, direction):
        for i, ch in enumerate(word):
            r = row + (i if direction == "down" else 0)
            c = col + (i if direction == "across" else 0)
            if (r, c) in cells and cells[(r, c)] != ch:
                return False
        return True

    def do_place(word, clue, word_idx, row, col, direction):
        for i, ch in enumerate(word):
            r = row + (i if direction == "down" else 0)
            c = col + (i if direction == "across" else 0)
            cells[(r, c)] = ch
        placements.append({
            "word": word, "clue": clue, "word_idx": word_idx,
            "row": row, "col": col, "direction": direction,
        })

    def find_crossing(new_word, direction):
        opposite = "across" if direction == "down" else "down"
        for p in placements:
            if p["direction"] != opposite:
                continue
            existing = p["word"]
            for ni, nch in enumerate(new_word):
                for ei, ech in enumerate(existing):
                    if nch != ech:
                        continue
                    if direction == "down":
                        nr = p["row"] - ni
                        nc = p["col"] + ei
                    else:
                        nr = p["row"] + ei
                        nc = p["col"] - ni
                    if can_place(new_word, nr, nc, direction):
                        return nr, nc
        return None

    do_place(words_upper[0], clues[0], 0, 0, 0, "across")

    for idx in range(1, len(words_upper)):
        w = words_upper[idx]
        c = clues[idx] if idx < len(clues) else ""
        preferred = "down" if idx % 2 == 1 else "across"
        fallback = "across" if preferred == "down" else "down"

        pos = find_crossing(w, preferred)
        if pos:
            do_place(w, c, idx, pos[0], pos[1], preferred)
            continue
        pos = find_crossing(w, fallback)
        if pos:
            do_place(w, c, idx, pos[0], pos[1], fallback)
            continue
        max_r = max(r for r, _ in cells) + 2 if cells else 0
        do_place(w, c, idx, max_r, 0, "across")

    if not cells:
        return {"grid": [], "across": [], "down": [], "grid_rows": 0, "grid_cols": 0}

    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    for p in placements:
        p["row"] -= min_r
        p["col"] -= min_c
    norm = {(r - min_r, c - min_c): ch for (r, c), ch in cells.items()}
    rows = max(r for r, _ in norm) + 1
    cols = max(c for _, c in norm) + 1

    numbered: dict[tuple[int, int], int] = {}
    num = 1
    for p in sorted(placements, key=lambda p: (p["row"], p["col"])):
        start = (p["row"], p["col"])
        if start not in numbered:
            numbered[start] = num
            num += 1
        p["number"] = numbered[start]

    out_grid = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if (r, c) in norm:
                row.append({"letter": norm[(r, c)], "number": numbered.get((r, c)), "empty": False})
            else:
                row.append({"empty": True})
        out_grid.append(row)

    across = [{"number": p["number"], "clue": p["clue"], "length": len(p["word"])}
              for p in placements if p["direction"] == "across"]
    down = [{"number": p["number"], "clue": p["clue"], "length": len(p["word"])}
            for p in placements if p["direction"] == "down"]

    return {"grid": out_grid, "across": across, "down": down, "grid_rows": rows, "grid_cols": cols}
