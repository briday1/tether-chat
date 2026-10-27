"""Render model Markdown as a deliberately restricted HTML subset."""
from markdown_it import MarkdownIt
import nh3

_parser = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table")
_ALLOWED = {"p", "br", "strong", "em", "s", "blockquote", "ul", "ol", "li",
            "h1", "h2", "h3", "h4", "hr", "pre", "code", "a",
            "table", "thead", "tbody", "tr", "th", "td"}
_ATTRIBUTES = {"a": {"href", "title"}}
_SCHEMES = {"https", "http", "mailto"}

def render(text: str) -> str:
    raw = _parser.render(text or "")
    return nh3.clean(raw, tags=_ALLOWED, attributes=_ATTRIBUTES,
                     url_schemes=_SCHEMES, link_rel="noopener noreferrer")
