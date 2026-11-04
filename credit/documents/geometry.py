"""Matrices affines PDF [a,b,c,d,e,f] ; coordonnées continues aux bords des pixels."""


def point(matrix, x, y):
    a, b, c, d, e, f = matrix
    return [a * x + c * y + e, b * x + d * y + f]


def inverse(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    if not det:
        raise ValueError("Transformation non inversible")
    return [d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det]


def compose(first, second):
    # Appliquer first, puis second.
    a, b, c, d, e, f = first
    g, h, i, j, k, offset_y = second
    return [
        g * a + i * b,
        h * a + j * b,
        g * c + i * d,
        h * c + j * d,
        g * e + i * f + k,
        h * e + j * f + offset_y,
    ]


def rectangle(matrix, bbox):
    x0, y0, x1, y1 = bbox
    pts = [point(matrix, x, y) for x, y in [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]]
    return [
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    ]


def transform(width, height, crop, rotation, scale=1):
    x0, y0, x1, y1 = [crop[0] * width, crop[1] * height, crop[2] * width, crop[3] * height]
    w, h = x1 - x0, y1 - y0
    translate = [1, 0, 0, 1, -x0, -y0]
    rotations = {
        0: [1, 0, 0, 1, 0, 0],
        90: [0, 1, -1, 0, h, 0],
        180: [-1, 0, 0, -1, w, h],
        270: [0, -1, 1, 0, 0, w],
    }
    return compose(compose(translate, rotations[rotation]), [scale, 0, 0, scale, 0, 0])
