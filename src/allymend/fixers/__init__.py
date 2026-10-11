from allymend.fixers.alt_text import check_alt_text, fix_image_alt
from allymend.fixers.edits import apply_edits, unified_diff
from allymend.fixers.html_has_lang import check_language_tag, fix_html_has_lang
from allymend.fixers.names import check_name, check_name_tag, fix_name
from allymend.fixers.plan import TEXT_RULES, FixOptions, plan_fixes
from allymend.fixers.values import ValueSource

__all__ = [
    "TEXT_RULES",
    "FixOptions",
    "ValueSource",
    "apply_edits",
    "check_alt_text",
    "check_language_tag",
    "check_name",
    "check_name_tag",
    "fix_html_has_lang",
    "fix_image_alt",
    "fix_name",
    "plan_fixes",
    "unified_diff",
]
