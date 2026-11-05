"""Plain text for local speech, parsed with the same CommonMark rules as the UI."""
import re
from markdown_it import MarkdownIt

PARSER=MarkdownIt('commonmark',{'html':False})

def markdown_to_speech(text):
    def inline(tokens):
        pieces=[]
        for token in tokens:
            if token.type in ('text','code_inline'):pieces.append(token.content)
            elif token.type in ('softbreak','hardbreak'):pieces.append(' ')
            elif token.type=='image':pieces.append(inline(token.children or []) or token.content)
        return ''.join(pieces)
    blocks=[]
    for token in PARSER.parse(str(text)):
        if token.type=='inline':blocks.append(inline(token.children or []))
        elif token.type in ('fence','code_block'):blocks.append(token.content)
    return re.sub(r'\s+',' ',' '.join(blocks)).strip()
