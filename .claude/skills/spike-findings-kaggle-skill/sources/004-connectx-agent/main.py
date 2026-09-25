"""Spike 004 ConnectX agent: win-if-possible, else block, else prefer the centre. Stdlib only.

Kaggle simulation submissions are a single file exposing the LAST function defined as the agent.
"""


def agent(observation, configuration):
    rows, cols, inarow = configuration.rows, configuration.columns, configuration.inarow
    me = observation.mark
    opp = 3 - me
    board = list(observation.board)

    def valid(col):
        return board[col] == 0

    def drop(b, col, mark):
        nb = list(b)
        for r in range(rows - 1, -1, -1):
            if nb[r * cols + col] == 0:
                nb[r * cols + col] = mark
                return nb
        return None

    def wins(b, mark):
        for r in range(rows):
            for c in range(cols):
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    ok = True
                    for k in range(inarow):
                        rr, cc = r + dr * k, c + dc * k
                        if not (0 <= rr < rows and 0 <= cc < cols) or b[rr * cols + cc] != mark:
                            ok = False
                            break
                    if ok:
                        return True
        return False

    moves = [c for c in range(cols) if valid(c)]
    for c in moves:  # 1) win now
        if wins(drop(board, c, me), me):
            return c
    for c in moves:  # 2) block the opponent's immediate win
        if wins(drop(board, c, opp), opp):
            return c
    centre = cols // 2  # 3) avoid handing the opponent a win on top of our move; prefer centre
    safe = [c for c in moves if not any(wins(drop(drop(board, c, me), c2, opp), opp)
                                        for c2 in range(cols) if drop(board, c, me)[c2] == 0)]
    pool = safe or moves
    return min(pool, key=lambda c: abs(c - centre))
