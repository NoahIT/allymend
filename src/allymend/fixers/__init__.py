from allymend.fixers.alt_text import check_alt_text, fix_image_alt
from allymend.fixers.edits import apply_edits, unified_diff
from allymend.fixers.html_has_lang import check_language_tag, fix_html_has_lang
from allymend.fixers.link_name import check_link_name, check_link_tag, fix_link_name
from allymend.fixers.plan import FixOptions, plan_fixes
from allymend.fixers.values import ValueSource

__all__ = [
    "FixOptions",
    "ValueSource",
    "apply_edits",
    "check_alt_text",
    "check_language_tag",
    "check_link_name",
    "check_link_tag",
    "fix_html_has_lang",
    "fix_image_alt",
    "fix_link_name",
    "plan_fixes",
    "unified_diff",
]
