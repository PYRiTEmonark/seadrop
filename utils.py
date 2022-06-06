from flask import escape

def format_bytes(size):
    power = 2**10
    n = 0
    labels = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + labels[n]

def sanitize(text):
    return escape(text)